"""Deterministic session policy. Evaluation has no device side effects."""
from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .engine import DecisionEngine, clamp
from .models import Context, OverrideLease


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def absolute_humidity(temp, rh):
    if temp is None or rh is None or not -50 <= temp <= 60 or not 0 <= rh <= 100:
        return None
    return 216.7 * (rh / 100 * 6.112 * math.exp(17.67 * temp / (temp + 243.5))) / (273.15 + temp)


def stamp(value):
    return datetime.fromisoformat(value) if value else None


class DynamicEngine(DecisionEngine):
    def __init__(self, entity_ids, clock=None):
        super().__init__(entity_ids)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.runtime = {"session_id": None, "started_at": None, "initial_co2": None,
                        "manual_session": False, "target_since": None, "high_since": None,
                        "emergency": False, "last_switch_at": None, "last_adjust_at": None,
                        "auto_resume_at": None, "lock_recalculated_at": None,
                        "lock_released": False, "repeated_veto": False}
        self.history = deque(maxlen=180)
        self.known_contexts = {}
        self.forecast = {}
        self.solar = {}

    def restore(self, data):
        if data:
            self.runtime.update(data)
        # Never count unobserved downtime as continuous threshold evidence.
        self.runtime["target_since"] = self.runtime["high_since"] = None

    def number(self, key, default=None):
        value = number(self.states[key].state) if key in self.states else None
        return default if value is None else value

    def classify_actor(self, state):
        now = self.clock()
        self.known_contexts = {k: v for k, v in self.known_contexts.items() if v > now}
        if any(state.context.get(k) in self.known_contexts for k in ("id", "parent_id")):
            return "ha_automation"
        return "human_ha" if state.context.get("user_id") else "manual_assumed"

    def update(self, state, initial=False):
        key = next((k for k, v in self.entity_ids.items() if v == state.entity_id), None)
        old = self.states.get(key)
        if initial or state.state in {"unknown", "unavailable"} or (old and old.state in {"unknown", "unavailable"}):
            self.states[key] = state
            if key == "fan":
                self.last_fan_state = state.state
                self.last_fan_preset = state.attributes.get("preset_mode")
            if key == "fan_level":
                self.last_fan_level = state.state
            return None
        return super().update(state)

    def expire_overrides(self, now):
        # Concentration does not release the session before minimum runtime + dwell.
        for domain, lease in list(self.manual.overrides.items()):
            if lease.expires_at and not lease.active(now):
                del self.manual.overrides[domain]
                if lease.reason == "manual_off":
                    self.runtime["lock_released"] = True

    def build_context(self, now):
        context = super().build_context(now)
        for key, seconds in self.freshness.items():
            state = self.states.get(key)
            if state and state.last_reported and timedelta(0) <= now-state.last_reported <= timedelta(seconds=seconds):
                if key in context.stale:
                    context.stale.remove(key)
        for key in ("co2", "indoor_pm25", "indoor_temperature", "indoor_humidity"):
            if self.number(key) is None and key not in context.stale:
                context.stale.append(key)
        for key in context.stale:
            if key in context.values:
                context.values[key] = None
        if "weather" in context.stale:
            for key in list(context.values):
                if key.startswith("outdoor_") or key in {"wind_speed", "precipitation", "cloud", "weather_condition"}:
                    context.values[key] = None
        for key in ("outdoor_temperature", "outdoor_humidity", "outdoor_pm25", "outdoor_pm10", "wind_speed", "precipitation"):
            context.values[key] = number(context.values.get(key))
        for key in ("outdoor_pm25", "outdoor_pm10"):
            if context.values.get(key) is None:
                context.stale.append(key)
        v = context.values
        v["indoor_absolute_humidity"] = absolute_humidity(v.get("indoor_temperature"), v.get("indoor_humidity"))
        v["outdoor_absolute_humidity"] = absolute_humidity(v.get("outdoor_temperature"), v.get("outdoor_humidity"))
        v["ble_location"] = "新风机前；不等同全屋平均温湿度"
        forecast_at = stamp(self.forecast.get("updated_at"))
        v["forecast"] = self.forecast if forecast_at and now - forecast_at < timedelta(minutes=90) else {"available": False}
        v["solar"] = self.solar
        context.quality = "degraded" if context.stale else "good"
        return context

    def handle_fan_transition(self, previous, current, actor):
        now = self.clock()
        manual = actor != "ha_automation"
        self.runtime["last_switch_at"] = now.isoformat()
        self.runtime["target_since"] = None
        self.manual.actor = actor
        self.manual.overrides.pop("power", None)
        self.manual.minimum_run_until = self.manual.lockout_until = None
        if current == "on":
            co2 = self.number("co2")
            self.runtime.update(session_id=str(uuid4()), started_at=now.isoformat(), initial_co2=co2,
                                manual_session=manual, lock_released=True)
            self.manual.minimum_run_until = now + timedelta(minutes=10)
            self.manual.state = "manual_run" if manual else "automatic"
            if manual:
                self.manual.overrides["power"] = OverrideLease("power", actor, now, reason="manual_on")
            else:
                self.runtime["auto_resume_at"] = now.isoformat()
        else:
            self.runtime["manual_session"] = False
            self.manual.overrides.clear()
            if manual:
                resumed = stamp(self.runtime["auto_resume_at"])
                self.runtime["repeated_veto"] = bool(resumed and timedelta(0) <= now-resumed < timedelta(minutes=30))
                self.runtime["lock_released"] = False
                self.manual.last_manual_off = now
                minutes = self.lockout_minutes(self.build_context(now), self.runtime["repeated_veto"])
                self.manual.lockout_until = now + timedelta(minutes=minutes)
                self.runtime["lock_recalculated_at"] = now.isoformat()
                self.manual.overrides["power"] = OverrideLease("power", actor, now, self.manual.lockout_until, reason="manual_off")
                self.manual.state = "manual_off_lockout"
            else:
                self.manual.state = "idle"
        return {"event": "manual_" + current if manual else "automatic_" + current,
                "actor": actor, "session_id": self.runtime["session_id"], "state": current}

    def handle_setting_transition(self, domain, previous, current, actor):
        now = self.clock()
        manual = actor != "ha_automation"
        if manual:
            self.manual.overrides[domain] = OverrideLease(domain, actor, now, now + timedelta(minutes=30), reason=f"manual_{domain}")
        else:
            self.runtime["last_adjust_at"] = now.isoformat()
        return {"event": domain + "_change", "actor": actor, "previous": previous, "current": current, "manual_lease": manual}

    def slope(self, key, now):
        rows = [(t, v[key]) for t, v in self.history if key in v and v[key] is not None and now-t <= timedelta(minutes=10)]
        if len(rows) < 6 or (rows[-1][0]-rows[0][0]).total_seconds() < 300:
            return None
        xs = [(t-rows[0][0]).total_seconds()/60 for t, _ in rows]
        ys = [y for _, y in rows]
        mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
        den = sum((x-mx)**2 for x in xs)
        return sum((x-mx)*(y-my) for x, y in zip(xs, ys))/den if den else None

    def lockout_minutes(self, context, repeated=False):
        v, now = context.values, context.timestamp
        co2 = v.get("co2")
        minutes = 120 if co2 is None else 240 if co2 < 600 else 180 if co2 < 750 else 90 if co2 < 900 else 30
        trend = self.slope("co2", now)
        if trend is not None:
            minutes += -30 if trend >= 2 else 30 if trend <= -2 else 0
        pm, pm10 = v.get("outdoor_pm25"), v.get("outdoor_pm10")
        if (pm is not None and pm > 35) or (pm10 is not None and pm10 >= 150) or any(w in str(v.get("weather_condition")) for w in ("沙", "尘")):
            minutes += 60
        correction = 0
        ti, to = v.get("indoor_temperature"), v.get("outdoor_temperature")
        if ti is not None and to is not None and abs(ti-to) >= 15:
            correction += 60
        ai, ao = v.get("indoor_absolute_humidity"), v.get("outdoor_absolute_humidity")
        if ai is not None and ao is not None:
            correction += 15 if abs(ai-ao) > 5 else -15 if abs(ai-ao) < 2 else 0
        # Forecast contributes only a bounded thermal correction, never starts fan.
        for row in v.get("forecast", {}).get("hours", {}).values():
            ft = number(row.get("temperature"))
            if ft is not None and ti is not None and abs(ti-ft) >= 15:
                correction += 15
                break
        minutes += clamp(correction, -0.2*minutes, 0.2*minutes)
        if repeated:
            minutes = max(minutes, 240)
        return int(clamp(minutes, 30, 480))

    def recommend(self, context):
        now, v = context.timestamp, context.values
        co2, pm = v.get("co2"), v.get("indoor_pm25")
        critical = co2 is None or pm is None or any(k in context.stale for k in ("co2", "indoor_pm25", "fan", "fan_level"))
        # Parent supplies the existing flow score. Optional missing inputs remain
        # null in the published snapshot; their adjustments are explicitly disabled.
        result = super().recommend(context)
        self.history.append((now, {"co2": co2, "indoor_pm25": pm}))
        pmout, pm10 = v.get("outdoor_pm25"), v.get("outdoor_pm10")
        ti, to = v.get("indoor_temperature"), v.get("outdoor_temperature")
        delta = abs(ti-to) if ti is not None and to is not None else None
        dust = (pm10 is not None and pm10 >= 150) or any(w in str(v.get("weather_condition")) for w in ("沙", "尘"))
        # Energy-aware ventilation: when outdoor air is clean and there is no
        # severe weather penalty, use the largest supported flow to shorten the
        # fan duty cycle. This keeps the IAQ targets unchanged.
        outdoor_aqi = number(v.get("outdoor_aqi"))
        clean_outdoor = outdoor_aqi is not None and outdoor_aqi <= 100 and pm10 is not None and pm10 < 150 and not dust
        severe_weather = delta is not None and delta >= 15
        high_flow_clean = clean_outdoor and not severe_weather and v.get("wind_speed") is not None and v.get("precipitation") in (0, None)
        if high_flow_clean:
            result.flow = 300
        # AQI still constrains flow, but does not authorize an earlier stop.
        # Only the existing dust / large-temperature-difference exceptions
        # may relax the IAQ floor until pollutant-specific rules are validated.
        adverse_weather = dust or severe_weather
        target = 800 if adverse_weather else 650 if pmout is not None and pmout <= 35 and delta is not None and delta <= 5 else 700
        if self.runtime["manual_session"] and self.runtime["initial_co2"] is not None and self.runtime["initial_co2"] <= 700:
            target = 600
        result.target_co2, result.target_pm25 = target, 15 if pmout is not None and pmout <= 15 else 21
        result.start_co2 = max(result.target_co2 + 100, min(1100, result.target_co2 + (200 if dust else 150 if pmout is not None and pmout > 35 else 200)))
        result.start_pm25 = max(result.target_pm25 + 5, min(32, result.target_pm25 + (5 if dust or (pmout is not None and pmout > 35) else 10)))
        # Legacy IAQ rules are the minimum protection in ordinary weather.
        # Missing weather is not evidence permitting relaxed thresholds.
        if not adverse_weather:
            target = result.target_co2 = min(result.target_co2, 700)
            result.target_pm25 = min(result.target_pm25, 21)
            result.start_co2 = min(result.start_co2, 900)
            result.start_pm25 = min(result.start_pm25, 26)
        if self.manual.lockout_until and not self.runtime["lock_released"] and not critical:
            last = stamp(self.runtime["lock_recalculated_at"])
            if not last or now-last >= timedelta(minutes=5):
                self.manual.lockout_until = self.manual.last_manual_off + timedelta(minutes=self.lockout_minutes(context, self.runtime["repeated_veto"]))
                self.runtime["lock_recalculated_at"] = now.isoformat()
                if "power" in self.manual.overrides:
                    self.manual.overrides["power"].expires_at = self.manual.lockout_until
        locked = bool(self.manual.lockout_until and now < self.manual.lockout_until and not self.runtime["lock_released"])
        if critical or co2 < 1500:
            self.runtime["high_since"] = None
        else:
            self.runtime["high_since"] = self.runtime["high_since"] or now.isoformat()
            if now-stamp(self.runtime["high_since"]) >= timedelta(minutes=10):
                self.runtime["emergency"] = True
                self.runtime["lock_released"] = True
                self.manual.overrides.pop("power", None)
                locked = False
        if not critical and co2 <= 1000:
            self.runtime["emergency"] = False
        fan_on = v.get("fan") == "on"
        minimum = self.manual.minimum_run_until
        switch_at = stamp(self.runtime["last_switch_at"])
        # Initial running snapshot gets a conservative startup dwell, not a manual event.
        if fan_on and not switch_at:
            self.runtime["last_switch_at"] = now.isoformat()
            switch_at = now
            self.manual.minimum_run_until = minimum = now + timedelta(minutes=10)
        ready = not minimum or now >= minimum
        met = not critical and co2 < target and pm < result.target_pm25
        self.runtime["target_since"] = (self.runtime["target_since"] or now.isoformat()) if met and fan_on else None
        dwell = self.runtime["target_since"] and now-stamp(self.runtime["target_since"]) >= timedelta(minutes=2)
        action = "no_action"
        if not critical:
            if fan_on and ready and dwell:
                action = "air_off"
            elif not fan_on and not locked and (co2 >= result.start_co2 or pm > result.start_pm25 or self.runtime["emergency"]):
                if self.runtime["emergency"] or not switch_at or now-switch_at >= timedelta(minutes=10):
                    action = "air_normal"
            elif fan_on and not any(k in self.manual.overrides for k in ("flow", "mode")):
                adjusted = stamp(self.runtime["last_adjust_at"]) or switch_at
                actual = v.get("fan_level")
                if actual is not None and abs(result.flow-actual) >= 40 and (not adjusted or now-adjusted >= timedelta(minutes=10)):
                    action = "air_normal"
        result.action = action
        result.authority = "fault_guard" if critical else "emergency_co2" if self.runtime["emergency"] else "manual_off" if locked else "manual_run" if self.runtime["manual_session"] else "baseline_iaq"
        result.priority = 1 if critical else 2 if self.runtime["emergency"] else 3 if locked or self.runtime["manual_session"] else 6
        estimates = []
        for key, value, goal in (("co2", co2, target), ("indoor_pm25", pm, result.target_pm25)):
            slope = self.slope(key, now)
            estimates.append(0 if value is not None and value < goal else (value-goal)/-slope if value is not None and slope is not None and slope < -0.1 else None)
        if fan_on and not critical and all(x is not None for x in estimates):
            remaining_min = max(0, (minimum-now).total_seconds()/60) if minimum else 0
            estimate = max(*estimates, remaining_min, 2)
            result.estimated_remaining_minutes = math.ceil(estimate) if estimate <= 120 else None
        result.minimum_run_until = minimum.isoformat() if minimum else None
        result.lockout_until = self.manual.lockout_until.isoformat() if locked else None
        hold = self.manual.overrides.get("flow")
        result.flow_hold_until = hold.expires_at.isoformat() if hold else None
        result.decision_id, result.session_id = str(uuid4()), self.runtime["session_id"]
        mode = self.states.get("control_level")
        result.execution_mode = mode.state if mode and mode.state in {"observe", "recommend", "bounded_auto"} else "observe"
        result.reason_code = "critical_input_invalid" if critical else "manual_lockout" if locked else "targets_met" if action == "air_off" else "dynamic_session"
        result.reason = (f"启动CO₂≥{result.start_co2}/停止<{target} ppm；启动PM2.5>{result.start_pm25}/停止<{result.target_pm25}；"
                         f"当前CO₂ {co2}；当前PM2.5 {pm}；"
                         f"建议风量{result.flow}；{result.reason_code}；"
                         f"节气:{self.solar.get('current_term', '不可用')}；"
                         f"数据:{context.quality}" + ("（" + ",".join(context.stale) + "）" if context.stale else "") +
                         ("；室外沙尘限小风量" if dust else ""))
        if outdoor_aqi is not None and outdoor_aqi > 100:
            result.reason += f"；室外AQI={outdoor_aqi:g}，保留污染等级限流，AQI本身不放宽启停底线"
        if adverse_weather and target == 800:
            exceptions = []
            if dust:
                exceptions.append('PM10≥150或天气含沙/尘')
            if severe_weather:
                exceptions.append('室内外温差≥15℃')
            result.reason += '；CO₂停止目标800例外：' + '、'.join(exceptions)
        if delta is not None and delta >= 15:
            result.reason += f"；室内外温差{delta:.1f}℃，减少冷热交换"
        if self.runtime['manual_session'] and target == 600:
            result.reason += '；低CO₂手动会话保留600目标及至少10分钟运行'
        if locked:
            result.reason += f"；关机锁定至{result.lockout_until}，截止以原关机时间为锚点"
        if result.flow_hold_until:
            result.reason += '；手动档位保护中，仅展示风量建议'
        if high_flow_clean:
            result.reason += '；室外空气清洁且无严重温差，采用最大风量300以缩短运行时间'
        if not adverse_weather:
            result.reason += '；无沙尘/大温差例外，执行原规则空气质量底线：启动不晚于900/26，停止必须同时低于700/21；手动与启停保护优先'
        return result

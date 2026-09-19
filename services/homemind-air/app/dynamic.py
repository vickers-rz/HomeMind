"""Deterministic session policy. Evaluation has no device side effects."""
from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .engine import DecisionEngine, clamp, nearest_flow
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


def seasonal_mode(solar):
    """Low-weight seasonal prior for Xi'an's cold-region monsoon climate."""
    lon = number((solar or {}).get("longitude"))
    if lon is None:
        return "unknown"
    lon %= 360
    if 75 <= lon < 165:
        return "hot_humid"
    if 165 <= lon < 225:
        return "autumn_humid"
    if 225 <= lon < 315:
        return "cold_dry"
    return "spring_transition"


class DynamicEngine(DecisionEngine):
    def __init__(self, entity_ids, clock=None, climate_profile="xian_cold_monsoon"):
        super().__init__(entity_ids)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.climate_profile = climate_profile
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
            if key == "heater":
                self.last_heater_state = state.state
            if key == "heat_level":
                self.last_heat_level = state.state
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
        # Temperature and humidity come from the same local Xiaomi BLE packet.
        # Home Assistant may only advance one entity timestamp when just one
        # measured value changes. Treat either recent report as proof that the
        # shared nearby-device sample is alive, while keeping a conservative
        # 30-minute ceiling because these are optional comfort inputs.
        temp_state = self.states.get("indoor_temperature")
        humidity_state = self.states.get("indoor_humidity")
        climate_reports = [
            state.last_reported or state.last_updated
            for state in (temp_state, humidity_state)
            if state is not None and (state.last_reported or state.last_updated)
        ]
        if climate_reports:
            latest_climate_report = max(climate_reports)
            climate_age = now - latest_climate_report
            if (
                timedelta(0) <= climate_age <= timedelta(minutes=30)
                and self.number("indoor_temperature") is not None
                and self.number("indoor_humidity") is not None
            ):
                for key in ("indoor_temperature", "indoor_humidity"):
                    if key in context.stale:
                        context.stale.remove(key)
        for key in ("co2", "indoor_pm25", "indoor_temperature", "indoor_humidity"):
            if self.number(key) is None and key not in context.stale:
                context.stale.append(key)
        for key in context.stale:
            if key in context.values:
                context.values[key] = None
        if "weather" in context.stale:
            for key in (
                "outdoor_humidity", "outdoor_aqi", "outdoor_pm25", "outdoor_pm10",
                "outdoor_temperature_weather", "wind_speed", "precipitation",
                "cloud", "weather_condition",
            ):
                if key in context.values:
                    context.values[key] = None
            if context.values.get("outdoor_temperature_source") == "qweather":
                context.values["outdoor_temperature"] = None
                context.values["outdoor_temperature_source"] = None
        for key in ("outdoor_temperature", "outdoor_humidity", "outdoor_pm25", "outdoor_pm10", "wind_speed", "precipitation"):
            context.values[key] = number(context.values.get(key))
        for key in ("outdoor_pm25", "outdoor_pm10"):
            if context.values.get(key) is None:
                context.stale.append(key)
        v = context.values
        v["indoor_absolute_humidity"] = absolute_humidity(v.get("indoor_temperature"), v.get("indoor_humidity"))
        # Humidity must be paired with the weather-service temperature measured
        # at the same outdoor source. The fresh-air intake has no local RH sensor,
        # so mixing intake temperature with remote RH would create a false AH.
        v["outdoor_absolute_humidity"] = absolute_humidity(v.get("outdoor_temperature_weather"), v.get("outdoor_humidity"))
        v["ble_location"] = "新风机旁；代表设备附近室内热湿环境，不等同全屋平均"
        forecast_at = stamp(self.forecast.get("updated_at"))
        v["forecast"] = self.forecast if forecast_at and now - forecast_at < timedelta(minutes=90) else {"available": False}
        v["solar"] = self.solar
        v["seasonal_mode"] = seasonal_mode(self.solar)
        v["climate_profile"] = self.climate_profile
        context.quality = "degraded" if context.stale else "good"
        return context

    def climate_exchange(self, values):
        """Return a bounded thermal/moisture opportunity factor.

        Real measurements drive the result. The site climate profile and solar
        season only modulate how strongly moisture import/loss is penalized.
        Forecasts may prefer a better near-term window, but never suppress the
        hard IAQ start thresholds.
        """
        v = values
        mode = v.get("seasonal_mode") or seasonal_mode(v.get("solar"))
        ti = number(v.get("indoor_temperature"))
        rh_i = number(v.get("indoor_humidity"))
        intake_t = number(v.get("outdoor_temperature"))
        weather_t = number(v.get("outdoor_temperature_weather"))
        rh_o = number(v.get("outdoor_humidity"))
        indoor_ah = absolute_humidity(ti, rh_i)
        outdoor_ah = absolute_humidity(weather_t, rh_o)
        factor = 1.0
        humidity_strategy = "neutral"
        temperature_strategy = "neutral"
        forecast_strategy = "current_window"

        # Direction-aware temperature opportunity. Absolute temperature-delta
        # cost is already represented by the base thermal_factor.
        if ti is not None and intake_t is not None:
            if ti >= 26.5 and intake_t <= ti - 2:
                factor *= 1.08
                temperature_strategy = "cooling_help"
            elif ti >= 26.5 and intake_t >= ti + 2:
                factor *= 0.88
                temperature_strategy = "adds_heat"
            elif ti <= 19 and intake_t >= ti + 2:
                factor *= 1.08
                temperature_strategy = "warming_help"
            elif ti <= 19 and intake_t <= ti - 2:
                factor *= 0.82
                temperature_strategy = "adds_cold"

        # Direction-aware humidity exchange. Xi'an's monsoon profile increases
        # the penalty for moisture import in the warm/autumn wet seasons and for
        # moisture loss in the cold-dry season. It never changes IAQ hard floors.
        ah_gap = None
        if indoor_ah is not None and outdoor_ah is not None and rh_i is not None:
            ah_gap = outdoor_ah - indoor_ah
            wet_weight = 0.78 if mode in {"hot_humid", "autumn_humid"} else 0.86
            dry_weight = 0.72 if mode == "cold_dry" else 0.84
            if rh_i >= 60:
                if ah_gap >= 1.5:
                    factor *= wet_weight
                    humidity_strategy = "avoid_moisture_import"
                elif ah_gap <= -1.5:
                    factor *= 1.08
                    humidity_strategy = "drying_help"
            elif rh_i <= 40:
                if ah_gap <= -1.5:
                    factor *= dry_weight
                    humidity_strategy = "avoid_overdrying"
                elif ah_gap >= 1.5:
                    factor *= 1.08
                    humidity_strategy = "humidifying_help"
            elif abs(ah_gap) >= 5:
                factor *= 0.90
                humidity_strategy = "protect_comfort_band"

        # Compare the current intake thermal/moisture burden with the 1/3/6 h
        # forecast. Deferral is only a preferred-flow hint when IAQ is nonurgent.
        forecast = v.get("forecast", {})
        rows = forecast.get("hours", {}) if isinstance(forecast, dict) else {}
        current_temp_delta = abs(ti - intake_t) if ti is not None and intake_t is not None else None
        future_temp_deltas = []
        future_moisture_burdens = []
        current_moisture_burden = None
        if indoor_ah is not None and outdoor_ah is not None and rh_i is not None:
            if rh_i >= 60:
                current_moisture_burden = max(0.0, outdoor_ah - indoor_ah)
            elif rh_i <= 40:
                current_moisture_burden = max(0.0, indoor_ah - outdoor_ah)
            else:
                current_moisture_burden = max(0.0, abs(outdoor_ah - indoor_ah) - 4)

        for row in rows.values():
            ft = number(row.get("temperature"))
            frh = number(row.get("humidity"))
            if ti is not None and ft is not None:
                future_temp_deltas.append(abs(ti - ft))
            fah = absolute_humidity(ft, frh)
            if indoor_ah is not None and fah is not None and rh_i is not None:
                if rh_i >= 60:
                    future_moisture_burdens.append(max(0.0, fah - indoor_ah))
                elif rh_i <= 40:
                    future_moisture_burdens.append(max(0.0, indoor_ah - fah))
                else:
                    future_moisture_burdens.append(max(0.0, abs(fah - indoor_ah) - 4))

        urgent = (number(v.get("co2")) or 0) >= 900 or (number(v.get("indoor_pm25")) or 0) > 26
        temp_improvement = (
            current_temp_delta - min(future_temp_deltas)
            if current_temp_delta is not None and future_temp_deltas else 0
        )
        moisture_improvement = (
            current_moisture_burden - min(future_moisture_burdens)
            if current_moisture_burden is not None and future_moisture_burdens else 0
        )
        temp_worsening = (
            min(future_temp_deltas) - current_temp_delta
            if current_temp_delta is not None and future_temp_deltas else 0
        )
        moisture_worsening = (
            min(future_moisture_burdens) - current_moisture_burden
            if current_moisture_burden is not None and future_moisture_burdens else 0
        )
        if not urgent and (temp_improvement >= 4 or moisture_improvement >= 2):
            factor *= 0.82
            forecast_strategy = "wait_better_window"
        elif not urgent and current_temp_delta is not None and current_temp_delta <= 5 and (
            temp_worsening >= 4 or moisture_worsening >= 2
        ):
            factor *= 1.05
            forecast_strategy = "use_current_window"

        return {
            "profile": self.climate_profile,
            "seasonal_mode": mode,
            "factor": round(clamp(factor, 0.55, 1.15), 3),
            "indoor_ah": indoor_ah,
            "outdoor_ah": outdoor_ah,
            "ah_gap": ah_gap,
            "humidity_strategy": humidity_strategy,
            "temperature_strategy": temperature_strategy,
            "forecast_strategy": forecast_strategy,
            "current_temp_delta": current_temp_delta,
        }

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
            self.manual.overrides[domain] = OverrideLease(domain, actor, now, now + timedelta(minutes=15), reason=f"manual_{domain}")
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
        climate = self.climate_exchange(v)
        ai, ao = climate["indoor_ah"], climate["outdoor_ah"]
        rh_i = number(v.get("indoor_humidity"))
        gap = climate["ah_gap"]
        if ai is not None and ao is not None and rh_i is not None and gap is not None:
            if rh_i >= 60:
                if gap >= 1.5:
                    correction += 30 if climate["seasonal_mode"] in {"hot_humid", "autumn_humid"} else 20
                elif gap <= -1.5:
                    correction -= 15
            elif rh_i <= 40:
                if gap <= -1.5:
                    correction += 30 if climate["seasonal_mode"] == "cold_dry" else 20
                elif gap >= 1.5:
                    correction -= 15
        if climate["forecast_strategy"] == "wait_better_window":
            correction += 15
        elif climate["forecast_strategy"] == "use_current_window":
            correction -= 10
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
        climate = self.climate_exchange(v)
        result.climate_profile = climate["profile"]
        result.seasonal_mode = climate["seasonal_mode"]
        result.climate_exchange_factor = climate["factor"]
        result.humidity_strategy = climate["humidity_strategy"]
        result.temperature_strategy = climate["temperature_strategy"]
        result.forecast_strategy = climate["forecast_strategy"]
        result.indoor_absolute_humidity = round(climate["indoor_ah"], 3) if climate["indoor_ah"] is not None else None
        result.outdoor_absolute_humidity = round(climate["outdoor_ah"], 3) if climate["outdoor_ah"] is not None else None

        # Thermal/moisture opportunity only tunes preferred flow. It never
        # suppresses the IAQ hard-start conditions below.
        outdoor_aqi = number(v.get("outdoor_aqi"))
        wind_speed = number(v.get("wind_speed"))
        precipitation = number(v.get("precipitation"))
        clean_outdoor = (
            outdoor_aqi is not None and outdoor_aqi <= 100
            and pmout is not None and pmout <= 35
            and pm10 is not None and pm10 < 150
            and not dust
        )
        severe_weather = delta is not None and delta >= 15
        if climate["factor"] < 0.999:
            result.flow = nearest_flow(max(60, result.flow * climate["factor"]))
        elif climate["factor"] > 1 and clean_outdoor:
            result.flow = nearest_flow(min(300, result.flow * climate["factor"]))

        # Maximum-flow shortcut is now stricter than AQI alone: particulate air
        # must actually be clean, wind must not be strong, and the current
        # thermal/moisture window must not be forecast to improve materially.
        high_flow_clean = (
            clean_outdoor
            and not severe_weather
            and wind_speed is not None and wind_speed <= 30
            and precipitation in (0, None)
            and climate["factor"] >= 0.95
            and climate["forecast_strategy"] != "wait_better_window"
        )
        if high_flow_clean:
            result.flow = 300

        # Re-apply the pollution cap after any climate adjustment.
        pollution_index = outdoor_aqi if outdoor_aqi is not None else number(pmout)
        cap = 300 if pollution_index is None or pollution_index <= 100 else 140 if pollution_index <= 150 else 100
        if dust:
            cap = 100
        result.flow = min(result.flow, cap)
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
        # Overall context quality may be degraded by optional inputs such as
        # humidity/weather. Only critical IAQ/device inputs gate execution.
        result.critical_input_quality = "degraded" if critical else "good"
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
        source = v.get("outdoor_temperature_source")
        if source == "fresh_air_intake":
            result.reason += f"；室外温度{v.get('outdoor_temperature')}℃来自新风机进风口"
        elif source == "qweather":
            result.reason += f"；室外温度{v.get('outdoor_temperature')}℃来自QWeather"
        if ti is not None and v.get("indoor_humidity") is not None:
            result.reason += f"；新风机旁室内{ti:.1f}℃/{float(v.get('indoor_humidity')):.0f}%RH"
        if result.indoor_absolute_humidity is not None and result.outdoor_absolute_humidity is not None:
            result.reason += (
                f"；绝对湿度室内{result.indoor_absolute_humidity:.1f}/"
                f"室外{result.outdoor_absolute_humidity:.1f}g/m³"
            )
        season_labels = {
            "hot_humid": "夏季热湿",
            "autumn_humid": "秋季湿润过渡",
            "cold_dry": "冬季冷干",
            "spring_transition": "春季过渡",
            "unknown": "未知",
        }
        result.reason += (
            f"；季节模型:{season_labels.get(result.seasonal_mode, result.seasonal_mode)}"
            f"；热湿交换因子:{result.climate_exchange_factor}"
        )
        if result.humidity_strategy not in (None, "neutral"):
            result.reason += f"；湿度策略:{result.humidity_strategy}"
        if result.temperature_strategy not in (None, "neutral"):
            result.reason += f"；温度策略:{result.temperature_strategy}"
        if result.forecast_strategy not in (None, "current_window"):
            result.reason += f"；预报策略:{result.forecast_strategy}"
        if pmout is not None and pmout > 35:
            result.reason += f"；室外PM2.5={pmout:g}，禁止300档清洁空气捷径"
        if wind_speed is not None and wind_speed > 30:
            result.reason += f"；室外风速{wind_speed:g}km/h，禁止300档捷径"
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

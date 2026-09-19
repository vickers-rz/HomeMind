from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import Context, EntityState, ManualState, OverrideLease, Recommendation

FLOWS = (60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def nearest_flow(value: float) -> int:
    return min(FLOWS, key=lambda candidate: abs(candidate - value))


class DecisionEngine:
    freshness = {
        "co2": 600,
        "indoor_pm25": 600,
        "indoor_temperature": 900,
        "indoor_humidity": 900,
        "weather": 1800,
    }

    def __init__(self, entity_ids: dict[str, str]):
        self.entity_ids = entity_ids
        self.states: dict[str, EntityState] = {}
        self.manual = ManualState()
        self.last_engine_action_at: datetime | None = None
        self.last_fan_state: str | None = None
        self.last_fan_level: str | None = None
        self.last_fan_preset: str | None = None

    def update(self, state: EntityState) -> dict[str, Any] | None:
        key = next((name for name, entity_id in self.entity_ids.items() if entity_id == state.entity_id), None)
        if key is None:
            return None
        self.states[key] = state
        if key == "fan_level":
            previous_level = self.last_fan_level
            self.last_fan_level = state.state
            if previous_level is None or previous_level == state.state:
                return None
            actor = self.classify_actor(state)
            return self.handle_setting_transition(
                "flow", previous_level, state.state, actor
            )
        if key != "fan":
            return None
        previous = self.last_fan_state
        previous_preset = self.last_fan_preset
        self.last_fan_state = state.state
        self.last_fan_preset = state.attributes.get("preset_mode")
        if previous is None:
            return None
        if previous == state.state:
            if previous_preset != self.last_fan_preset:
                actor = self.classify_actor(state)
                return self.handle_setting_transition(
                    "mode", previous_preset, self.last_fan_preset, actor
                )
            return None
        actor = self.classify_actor(state)
        return self.handle_fan_transition(previous, state.state, actor)

    @staticmethod
    def classify_actor(state: EntityState) -> str:
        context = state.context
        if context.get("user_id"):
            return "human_ha"
        if context.get("parent_id"):
            return "ha_automation"
        return "manual_assumed"

    def number(self, key: str, default: float | None = None) -> float | None:
        try:
            return float(self.states[key].state)
        except (KeyError, TypeError, ValueError):
            return default

    def build_context(self, now: datetime) -> Context:
        self.expire_overrides(now)
        stale = []
        for key, seconds in self.freshness.items():
            state = self.states.get(key)
            if not state or (now - state.last_updated.astimezone(timezone.utc)).total_seconds() > seconds:
                stale.append(key)
        for key in ("fan", "fan_level"):
            state = self.states.get(key)
            if not state or state.state in {"unknown", "unavailable"}:
                stale.append(key)
        weather = self.states.get("weather")
        attrs = weather.attributes if weather else {}
        aqi = attrs.get("aqi") if isinstance(attrs.get("aqi"), dict) else {}
        values = {
            "co2": self.number("co2"),
            "indoor_pm25": self.number("indoor_pm25"),
            "indoor_temperature": self.number("indoor_temperature"),
            "indoor_humidity": self.number("indoor_humidity"),
            "fan": self.states.get("fan").state if self.states.get("fan") else None,
            "fan_level": self.number("fan_level"),
            "outdoor_temperature": attrs.get("temperature"),
            "outdoor_humidity": attrs.get("humidity"),
            "wind_speed": attrs.get("wind_speed"),
            "precipitation": attrs.get("precip", 0),
            "cloud": attrs.get("cloud"),
            "outdoor_aqi": aqi.get("aqi"),
            "outdoor_pm25": aqi.get("pm2p5"),
            "outdoor_pm10": aqi.get("pm10"),
            "weather_condition": attrs.get("condition_cn") or (weather.state if weather else None),
        }
        quality = "good" if not stale else "degraded"
        return Context(timestamp=now, values=values, quality=quality, stale=stale)

    def recommend(self, context: Context) -> Recommendation:
        v = context.values
        co2 = float(v.get("co2") or 0)
        indoor_pm = float(v.get("indoor_pm25") or 0)
        co2_demand = clamp((co2 - 600) / 600, 0, 1)
        pm_demand = clamp((indoor_pm - 10) / 25, 0, 1)
        demand = max(co2_demand, pm_demand)

        outdoor_pm25 = float(v.get("outdoor_pm25") or 0)
        outdoor_pm10 = float(v.get("outdoor_pm10") or 0)
        outdoor_aqi = v.get("outdoor_aqi")
        pollution_index = float(outdoor_aqi) if outdoor_aqi is not None else outdoor_pm25
        if pollution_index <= 100:
            air_factor, cap = 1.0, 300
        elif pollution_index <= 150:
            air_factor, cap = 0.75, 140
        else:
            air_factor, cap = 0.25, 100
        condition = str(v.get("weather_condition") or "")
        dust = outdoor_pm10 >= 150 or any(word in condition for word in ("沙", "尘"))
        if dust:
            cap = 100

        indoor_t = float(v.get("indoor_temperature") or 25)
        outdoor_t = float(v.get("outdoor_temperature") or indoor_t)
        thermal_factor = clamp(1 - abs(indoor_t - outdoor_t) / 25, 0.35, 1)
        wind_factor = 0.7 if float(v.get("wind_speed") or 0) > 30 else 1.0
        rain_factor = 0.7 if float(v.get("precipitation") or 0) > 0 else 1.0
        weather_score = air_factor * thermal_factor * wind_factor * rain_factor

        raw_flow = 60 + 240 * demand * weather_score
        flow = min(nearest_flow(raw_flow), cap)
        if co2 >= 1200:
            duration = 60
        elif co2 >= 900 or indoor_pm > 26:
            duration = 30
        elif co2 >= 700:
            duration = 20
        else:
            duration = 10

        action = "no_action"
        if co2 > 900 or indoor_pm > 26:
            action = "air_fast" if flow >= 220 else "air_normal" if flow >= 120 else "air_low"
        reason_bits = [f"CO₂ {co2:.0f} ppm", f"室内PM2.5 {indoor_pm:.0f}"]
        if dust:
            reason_bits.append("室外沙尘/PM10限小风量")
        elif outdoor_pm25 > 35:
            reason_bits.append(f"室外PM2.5 {outdoor_pm25:.0f}限制风量")
        authority, priority = self.active_authority(context)
        if context.stale:
            reason_bits.append("数据降级:" + ",".join(context.stale))
            action = "no_action"
            authority, priority = "fault_guard", 1
        elif authority.startswith("manual_"):
            reason_bits.append(f"手动租约生效:{authority}")
            action = "no_action"
        return Recommendation(
            flow=flow,
            duration_minutes=duration,
            demand=round(demand, 3),
            weather_score=round(weather_score, 3),
            reason_code="iaq_demand" if action != "no_action" else "monitor",
            reason="；".join(reason_bits),
            input_quality=context.quality,
            action=action,
            authority=authority,
            priority=priority,
        )

    def expire_overrides(self, now: datetime) -> None:
        co2 = self.number("co2")
        expired = []
        for domain, lease in self.manual.overrides.items():
            released = (
                lease.release_condition == "co2_below_600"
                and co2 is not None
                and co2 < 600
            )
            if not lease.active(now) or released:
                expired.append(domain)
        for domain in expired:
            self.manual.overrides.pop(domain, None)
        if not self.manual.overrides and self.manual.state.startswith("manual_"):
            self.manual.state = "idle"

    def active_authority(self, context: Context) -> tuple[str, int]:
        co2 = float(context.values.get("co2") or 0)
        if co2 >= 1500:
            return "emergency_co2", 2
        if "power" in self.manual.overrides:
            lease = self.manual.overrides["power"]
            return ("manual_off" if lease.reason == "manual_off" else "manual_power", 3)
        if "flow" in self.manual.overrides:
            return "manual_flow", 4
        if "mode" in self.manual.overrides:
            return "manual_mode", 4
        return "baseline_iaq", 6

    def lockout_minutes(self, context: Context, repeated: bool = False) -> int:
        co2 = float(context.values.get("co2") or 700)
        outdoor_pm25 = float(context.values.get("outdoor_pm25") or 0)
        outdoor_pm10 = float(context.values.get("outdoor_pm10") or 0)
        if co2 < 600:
            minutes = 240
        elif co2 < 750:
            minutes = 180
        elif co2 < 900:
            minutes = 90
        else:
            minutes = 30
        if outdoor_pm25 > 75 or outdoor_pm10 > 150:
            minutes += 60
        if repeated:
            minutes = max(minutes + 120, 240)
        return int(clamp(minutes, 30, 480))

    def handle_fan_transition(self, previous: str, current: str, actor: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        co2 = self.number("co2", 700) or 700
        self.manual.actor = actor
        if current == "on" and (actor.startswith("manual") or actor == "human_ha"):
            if co2 < 500:
                self.manual.state = "manual_low_co2_minimum_run"
                self.manual.minimum_run_until = now + timedelta(minutes=10)
                self.manual.overrides["power"] = OverrideLease(
                    domain="power", actor=actor, started_at=now,
                    expires_at=self.manual.minimum_run_until,
                    reason="manual_low_co2_minimum_run",
                )
            elif co2 < 700:
                self.manual.state = "manual_run"
                self.manual.overrides["power"] = OverrideLease(
                    domain="power", actor=actor, started_at=now,
                    release_condition="co2_below_600", reason="manual_on",
                )
            else:
                self.manual.state = "manual_run"
            return {"event": "manual_on", "actor": actor, "co2": co2}
        if current == "off" and (actor.startswith("manual") or actor == "human_ha"):
            repeated = bool(self.manual.last_manual_off and now - self.manual.last_manual_off < timedelta(minutes=30))
            context = self.build_context(now)
            minutes = self.lockout_minutes(context, repeated)
            self.manual.state = "manual_off_lockout"
            self.manual.last_manual_off = now
            self.manual.lockout_until = now + timedelta(minutes=minutes)
            self.manual.repeated_off_count = self.manual.repeated_off_count + 1 if repeated else 1
            self.manual.overrides["power"] = OverrideLease(
                domain="power", actor=actor, started_at=now,
                expires_at=self.manual.lockout_until, reason="manual_off",
            )
            return {"event": "manual_off", "actor": actor, "co2": co2, "lockout_minutes": minutes}
        self.manual.state = "automatic" if current == "on" else "idle"
        return {"event": "external_transition", "actor": actor, "state": current}

    def handle_setting_transition(
        self, domain: str, previous: Any, current: Any, actor: str
    ) -> dict[str, Any]:
        manual = actor.startswith("manual") or actor == "human_ha"
        if manual:
            now = datetime.now(timezone.utc)
            self.manual.overrides[domain] = OverrideLease(
                domain=domain,
                actor=actor,
                started_at=now,
                expires_at=now + timedelta(hours=2),
                reason=f"manual_{domain}_change",
            )
            self.manual.state = f"manual_{domain}"
        return {
            "event": f"{domain}_change",
            "actor": actor,
            "previous": previous,
            "current": current,
            "manual_lease": manual,
        }

    @staticmethod
    def context_hash(context: Context) -> str:
        raw = json.dumps(context.values, sort_keys=True, ensure_ascii=False, default=str).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

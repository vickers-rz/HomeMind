from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EntityState:
    entity_id: str
    state: str
    attributes: dict[str, Any]
    last_updated: datetime
    context: dict[str, Any] = field(default_factory=dict)
    last_reported: datetime | None = None


@dataclass
class Context:
    timestamp: datetime
    values: dict[str, Any]
    quality: str
    stale: list[str]


@dataclass
class Recommendation:
    flow: int
    duration_minutes: int
    demand: float
    weather_score: float
    reason_code: str
    reason: str
    input_quality: str
    critical_input_quality: str = "good"
    outdoor_temperature: float | None = None
    outdoor_temperature_source: str | None = None
    climate_profile: str | None = None
    seasonal_mode: str | None = None
    climate_exchange_factor: float | None = None
    humidity_strategy: str | None = None
    temperature_strategy: str | None = None
    forecast_strategy: str | None = None
    indoor_absolute_humidity: float | None = None
    outdoor_absolute_humidity: float | None = None
    action: str = "no_action"
    authority: str = "baseline_iaq"
    priority: int = 6
    target_co2: int = 700
    target_pm25: int = 21
    start_co2: int = 900
    start_pm25: int = 26
    minimum_run_minutes: int = 10
    estimated_remaining_minutes: int | None = None
    lockout_until: str | None = None
    minimum_run_until: str | None = None
    flow_hold_until: str | None = None
    decision_id: str = ""
    session_id: str | None = None
    execution_mode: str = "observe"
    algorithm_version: str = "0.5.1"

    def json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OverrideLease:
    domain: str
    actor: str
    started_at: datetime
    expires_at: datetime | None = None
    release_condition: str | None = None
    reason: str = "manual_change"

    def active(self, now: datetime) -> bool:
        return self.expires_at is None or now < self.expires_at

    def json_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["started_at"] = self.started_at.isoformat()
        if self.expires_at is not None:
            result["expires_at"] = self.expires_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OverrideLease":
        data = dict(value)
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data.get("expires_at"):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)


@dataclass
class ManualState:
    state: str = "idle"
    actor: str = "unknown"
    lockout_until: datetime | None = None
    minimum_run_until: datetime | None = None
    last_manual_off: datetime | None = None
    repeated_off_count: int = 0
    overrides: dict[str, OverrideLease] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ManualState":
        if not value:
            return cls()
        data = dict(value)
        for key in ("lockout_until", "minimum_run_until", "last_manual_off"):
            raw = data.get(key)
            data[key] = datetime.fromisoformat(raw) if raw else None
        return cls(
            state=str(data.get("state", "idle")),
            actor=str(data.get("actor", "unknown")),
            lockout_until=data["lockout_until"],
            minimum_run_until=data["minimum_run_until"],
            last_manual_off=data["last_manual_off"],
            repeated_off_count=int(data.get("repeated_off_count", 0)),
            overrides={
                key: OverrideLease.from_dict(lease)
                for key, lease in data.get("overrides", {}).items()
            },
        )

    def json_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("lockout_until", "minimum_run_until", "last_manual_off"):
            if result[key] is not None:
                result[key] = result[key].isoformat()
        result["overrides"] = {
            key: lease.json_dict() for key, lease in self.overrides.items()
        }
        return result

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import HuberRegressor

DB_PATH = os.getenv("HOMEMIND_DB", "/data/homemind-air.sqlite3")
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/data/adaptive_model.json"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "30"))
INTERVAL = int(os.getenv("LEARN_INTERVAL_SECONDS", "900"))


def num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def absolute_humidity(temp_c: Any, rh: Any) -> float | None:
    t, h = num(temp_c), num(rh)
    if t is None or h is None:
        return None
    saturation = 6.112 * math.exp((17.67 * t) / (t + 243.5))
    return 2.1674 * (h / 100.0 * saturation) / (273.15 + t) * 100


def normalized(raw: dict[str, Any]) -> dict[str, Any]:
    x = dict(raw)
    weather_t = num(x.get("outdoor_temperature_weather"))
    if weather_t is None:
        weather_t = num(x.get("outdoor_temperature"))
    x["outdoor_temperature_weather"] = weather_t
    if num(x.get("indoor_absolute_humidity")) is None:
        x["indoor_absolute_humidity"] = absolute_humidity(
            x.get("indoor_temperature"), x.get("indoor_humidity")
        )
    if num(x.get("outdoor_absolute_humidity")) is None:
        x["outdoor_absolute_humidity"] = absolute_humidity(
            weather_t, x.get("outdoor_humidity")
        )
    x.setdefault("heater", "off")
    x.setdefault("heat_level", "Level1")
    return x


def signature(x: dict[str, Any]) -> tuple[bool, int, bool, str]:
    fan_on = x.get("fan") == "on"
    flow = int(round(num(x.get("fan_level")) or 0)) if fan_on else 0
    heater_on = x.get("heater") == "on" if fan_on else False
    level = str(x.get("heat_level") or "Level1") if heater_on else "off"
    return fan_on, flow, heater_on, level


@dataclass
class Window:
    start: str
    end: str
    sig: tuple[bool, int, bool, str]
    minutes: float
    co2: float | None
    co2_slope: float | None
    pm25: float | None
    pm25_slope: float | None
    indoor_temp: float | None
    temp_slope: float | None
    weather_temp: float | None
    intake_temp: float | None
    indoor_ah: float | None
    ah_slope: float | None
    outdoor_ah: float | None


def midpoint(a: dict[str, Any], b: dict[str, Any], key: str) -> float | None:
    x, y = num(a.get(key)), num(b.get(key))
    if x is not None and y is not None:
        return (x + y) / 2
    return x if x is not None else y


def slope(a: dict[str, Any], b: dict[str, Any], key: str, minutes: float) -> float | None:
    x, y = num(a.get(key)), num(b.get(key))
    return (y - x) / minutes if x is not None and y is not None else None


def make_window(t0: datetime, a: dict[str, Any], t1: datetime, b: dict[str, Any]) -> Window | None:
    minutes = (t1 - t0).total_seconds() / 60
    if not 4.0 <= minutes <= 7.5:
        return None
    return Window(
        t0.isoformat(), t1.isoformat(), signature(a), minutes,
        midpoint(a, b, "co2"), slope(a, b, "co2", minutes),
        midpoint(a, b, "indoor_pm25"), slope(a, b, "indoor_pm25", minutes),
        midpoint(a, b, "indoor_temperature"), slope(a, b, "indoor_temperature", minutes),
        midpoint(a, b, "outdoor_temperature_weather"),
        midpoint(a, b, "outdoor_temperature"),
        midpoint(a, b, "indoor_absolute_humidity"),
        slope(a, b, "indoor_absolute_humidity", minutes),
        midpoint(a, b, "outdoor_absolute_humidity"),
    )


def load_windows() -> tuple[list[Window], dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = db.execute(
        "SELECT created_at,inputs FROM decisions WHERE created_at>=? ORDER BY created_at",
        (cutoff,),
    )
    windows: list[Window] = []
    first_time = last_time = None
    anchor_t = None
    anchor_x = None
    anchor_sig = None
    rows_seen = 0
    for created, raw in rows:
        try:
            t = datetime.fromisoformat(created)
            x = normalized(json.loads(raw))
        except Exception:
            continue
        rows_seen += 1
        first_time = first_time or created
        last_time = created
        sig = signature(x)
        if anchor_t is None:
            anchor_t, anchor_x, anchor_sig = t, x, sig
            continue
        gap = (t - anchor_t).total_seconds() / 60
        if gap < 0 or sig != anchor_sig or gap > 8:
            anchor_t, anchor_x, anchor_sig = t, x, sig
            continue
        if gap >= 4.75:
            w = make_window(anchor_t, anchor_x, t, x)
            if w:
                windows.append(w)
            anchor_t, anchor_x, anchor_sig = t, x, sig
    db.close()
    return windows, {
        "rows": rows_seen,
        "windows": len(windows),
        "first": first_time,
        "last": last_time,
    }


def robust_scalar(values: list[float], low: float, high: float, min_samples: int) -> dict[str, Any]:
    vals = np.asarray([v for v in values if math.isfinite(v) and low <= v <= high], dtype=float)
    if len(vals) < min_samples:
        return {"value": None, "samples": int(len(vals)), "confidence": 0.0, "accepted": False}
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med)))
    if mad > 1e-12:
        vals = vals[np.abs(vals - med) <= 4.5 * 1.4826 * mad]
    value = float(np.median(vals))
    spread = float(np.median(np.abs(vals - value))) if len(vals) else 0.0
    confidence = min(1.0, len(vals) / max(min_samples * 2, 1))
    return {
        "value": value,
        "samples": int(len(vals)),
        "mad": spread,
        "confidence": round(confidence, 3),
        "accepted": bool(len(vals) >= min_samples and low <= value <= high),
    }


def robust_through_origin(x: list[float], y: list[float], low: float, high: float, min_samples: int) -> dict[str, Any]:
    pairs = [(a, b) for a, b in zip(x, y) if math.isfinite(a) and math.isfinite(b) and abs(a) >= 0.05]
    if len(pairs) < min_samples:
        return {"value": None, "samples": len(pairs), "confidence": 0.0, "accepted": False}
    X = np.asarray([[a] for a, _ in pairs], dtype=float)
    Y = np.asarray([b for _, b in pairs], dtype=float)
    split = max(min_samples, int(len(Y) * 0.7))
    if split >= len(Y):
        split = len(Y) - 1
    train_x, train_y = X[:split], Y[:split]
    test_x, test_y = X[split:], Y[split:]
    model = HuberRegressor(fit_intercept=False, epsilon=1.5, alpha=0.001, max_iter=500)
    model.fit(train_x, train_y)
    coef = float(model.coef_[0])
    pred = model.predict(test_x) if len(test_y) else np.array([])
    model_mae = float(np.mean(np.abs(test_y - pred))) if len(test_y) else None
    baseline_mae = float(np.mean(np.abs(test_y))) if len(test_y) else None
    improvement = (
        1 - model_mae / baseline_mae
        if model_mae is not None and baseline_mae and baseline_mae > 1e-9 else 0.0
    )
    physical = low <= coef <= high
    accepted = len(pairs) >= min_samples and physical and (len(test_y) < 3 or improvement > -0.15)
    confidence = min(1.0, len(pairs) / (min_samples * 2))
    if len(test_y) >= 3:
        confidence *= max(0.0, min(1.0, 0.5 + improvement))
    return {
        "value": coef if physical else None,
        "samples": len(pairs),
        "validation_mae": model_mae,
        "baseline_mae": baseline_mae,
        "validation_improvement": round(improvement, 3),
        "confidence": round(confidence, 3),
        "accepted": bool(accepted),
    }


def fit_model(windows: list[Window], history: dict[str, Any]) -> dict[str, Any]:
    natural_ach = []
    envelope_rates = []
    moisture_rates = []

    for w in windows:
        fan_on, _, heater_on, _ = w.sig
        if fan_on:
            continue
        if w.co2 and w.co2 > 550 and w.co2_slope is not None and w.co2_slope < 0:
            natural_ach.append(-w.co2_slope * 60 / max(100.0, w.co2 - 420))
        if None not in (w.indoor_temp, w.weather_temp, w.temp_slope):
            gap = w.weather_temp - w.indoor_temp
            if abs(gap) >= 3 and w.temp_slope * gap > 0:
                envelope_rates.append(w.temp_slope * 60 / gap)
        if None not in (w.indoor_ah, w.outdoor_ah, w.ah_slope):
            gap = w.outdoor_ah - w.indoor_ah
            if abs(gap) >= 1 and w.ah_slope * gap > 0:
                moisture_rates.append(w.ah_slope * 60 / gap)

    fan_x, fan_y = [], []
    thermal_x, thermal_y = [], []
    moisture_x, moisture_y = [], []
    pm_x, pm_y = [], []
    heater_samples: dict[str, list[float]] = {"Level1": [], "Level2": [], "Level3": []}
    transition_count = 0

    for before, after in zip(windows, windows[1:]):
        try:
            gap = (
                datetime.fromisoformat(after.start) - datetime.fromisoformat(before.end)
            ).total_seconds() / 60
        except ValueError:
            continue
        if gap > 8:
            continue
        if before.sig == after.sig:
            continue
        transition_count += 1
        b_on, b_flow, b_heat, b_level = before.sig
        a_on, a_flow, a_heat, a_level = after.sig
        df = (a_flow - b_flow) / 300.0

        c = after.co2 or before.co2
        if (
            abs(df) >= 0.05 and c is not None and c > 520
            and before.co2_slope is not None and after.co2_slope is not None
        ):
            delta_ach = -(after.co2_slope - before.co2_slope) * 60 / max(100.0, c - 420)
            fan_x.append(df)
            fan_y.append(delta_ach)

        if (
            abs(df) >= 0.05 and before.temp_slope is not None and after.temp_slope is not None
            and after.indoor_temp is not None and after.intake_temp is not None
        ):
            tg = after.intake_temp - after.indoor_temp
            if abs(tg) >= 2:
                thermal_x.append(df)
                thermal_y.append((after.temp_slope - before.temp_slope) * 60 / tg)

        if (
            abs(df) >= 0.05 and before.ah_slope is not None and after.ah_slope is not None
            and after.indoor_ah is not None and after.outdoor_ah is not None
        ):
            hg = after.outdoor_ah - after.indoor_ah
            if abs(hg) >= 1:
                moisture_x.append(df)
                moisture_y.append((after.ah_slope - before.ah_slope) * 60 / hg)

        p = after.pm25 or before.pm25
        if (
            abs(df) >= 0.05 and p is not None and p >= 3
            and before.pm25_slope is not None and after.pm25_slope is not None
        ):
            pm_x.append(df)
            pm_y.append(-(after.pm25_slope - before.pm25_slope) * 60 / max(3.0, p))

        if a_flow == b_flow and a_flow > 0 and before.temp_slope is not None and after.temp_slope is not None:
            if not b_heat and a_heat and a_level in heater_samples:
                heater_samples[a_level].append((after.temp_slope - before.temp_slope) * 60)
            elif b_heat and not a_heat and b_level in heater_samples:
                heater_samples[b_level].append((before.temp_slope - after.temp_slope) * 60)

    parameters = {
        "natural_ach": robust_scalar(natural_ach, 0.01, 3.0, 20),
        "envelope_rate_h": robust_scalar(envelope_rates, 0.005, 1.5, 20),
        "moisture_exchange_rate_h": robust_scalar(moisture_rates, 0.005, 3.0, 20),
        "fan_ach_at_300": robust_through_origin(fan_x, fan_y, 0.05, 12.0, 10),
        "fan_thermal_exchange_at_300": robust_through_origin(thermal_x, thermal_y, 0.01, 8.0, 8),
        "fan_moisture_exchange_at_300": robust_through_origin(moisture_x, moisture_y, 0.01, 8.0, 8),
        "pm_removal_rate_at_300": robust_through_origin(pm_x, pm_y, 0.01, 15.0, 8),
        "heater_gain_c_per_h": {
            level: robust_scalar(values, 0.02, 12.0, 4)
            for level, values in heater_samples.items()
        },
    }
    envelope = parameters["envelope_rate_h"]
    thermal_tau = None
    if envelope.get("accepted") and envelope.get("value"):
        thermal_tau = 1.0 / envelope["value"]

    accepted_core = [
        p for k, p in parameters.items()
        if isinstance(p, dict) and "accepted" in p and k != "envelope_rate_h"
    ]
    return {
        "schema_version": 1,
        "mode": "shadow",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "history": {**history, "transitions": transition_count},
        "parameters": parameters,
        "derived": {
            "thermal_tau_hours": thermal_tau,
        },
        "readiness": {
            "control_eligible": False,
            "reason": "shadow_validation_required",
            "accepted_parameter_count": sum(1 for p in accepted_core if p.get("accepted")),
            "heater_levels_learned": sum(
                1 for p in parameters["heater_gain_c_per_h"].values() if p.get("accepted")
            ),
        },
    }


def train_once() -> dict[str, Any]:
    windows, history = load_windows()
    model = fit_model(windows, history)
    tmp = MODEL_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(model, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(tmp, MODEL_PATH)
    print(json.dumps({
        "trained_at": model["trained_at"],
        "history": model["history"],
        "readiness": model["readiness"],
    }, ensure_ascii=False), flush=True)
    return model


def main() -> None:
    while True:
        try:
            train_once()
        except Exception as exc:
            print(json.dumps({
                "error": type(exc).__name__,
                "message": str(exc),
                "at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False), flush=True)
        if INTERVAL <= 0:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

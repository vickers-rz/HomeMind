from datetime import datetime, timedelta, timezone

from app.engine import DecisionEngine
from app.models import EntityState, ManualState


IDS = {
    "co2": "sensor.co2",
    "indoor_pm25": "sensor.pm25",
    "indoor_temperature": "sensor.temperature",
    "indoor_humidity": "sensor.humidity",
    "fan": "fan.air",
    "fan_level": "select.flow",
    "heater": "switch.heater",
    "heat_level": "select.heat_level",
    "fresh_air_info": "button.air_info",
    "weather": "weather.home",
    "sun": "sun.sun",
    "enabled": "input_boolean.enabled",
    "control_level": "input_select.level",
}


def state(entity_id, value, attributes=None, minutes_old=0, context=None):
    return EntityState(
        entity_id,
        str(value),
        attributes or {},
        datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
        context or {},
    )


def populated(co2=950, indoor_pm25=12, outdoor_pm25=20, outdoor_pm10=40):
    engine = DecisionEngine(IDS)
    for item in [
        state("sensor.co2", co2),
        state("sensor.pm25", indoor_pm25),
        state("sensor.temperature", 25),
        state("sensor.humidity", 45),
        state("fan.air", "off"),
        state("select.flow", 300),
        state("switch.heater", "off"),
        state("select.heat_level", "Level1"),
        state("weather.home", "cloudy", {
            "temperature": 28,
            "humidity": 50,
            "wind_speed": 10,
            "precip": 0,
            "condition_cn": "多云",
            "aqi": {"pm2p5": outdoor_pm25, "pm10": outdoor_pm10, "aqi": 60},
        }),
    ]:
        engine.update(item)
    return engine




def test_fresh_air_intake_temperature_is_preferred_over_qweather():
    engine = populated()
    engine.update(state("button.air_info", "unknown", {"environment.temperature": 6}))
    context = engine.build_context(datetime.now(timezone.utc))
    assert context.values["outdoor_temperature"] == 6
    assert context.values["outdoor_temperature_source"] == "fresh_air_intake"
    assert context.values["outdoor_temperature_weather"] == 28


def test_stale_fresh_air_intake_temperature_falls_back_to_qweather():
    engine = populated()
    engine.update(state("button.air_info", "unknown", {"environment.temperature": 6}, minutes_old=4))
    context = engine.build_context(datetime.now(timezone.utc))
    assert context.values["outdoor_temperature"] == 28
    assert context.values["outdoor_temperature_source"] == "qweather"


def test_heater_state_is_collected_into_context_without_changing_policy():
    engine = populated()
    engine.update(state("button.air_info", "unknown", {
        "environment.temperature": 8,
        "air_fresh.heater": True,
        "air_fresh.heat_level": 2,
    }))
    context = engine.build_context(datetime.now(timezone.utc))
    assert context.values["heater"] == "on"
    assert context.values["heat_level"] == "Level2"


def test_manual_heater_change_creates_fifteen_minute_observation_lease():
    engine = populated()
    engine.last_heater_state = "off"
    transition = engine.update(state("switch.heater", "on"))
    assert transition["event"] == "heater_change"
    assert transition["manual_lease"] is True
    lease = engine.manual.overrides["heater"]
    assert lease.expires_at - lease.started_at == timedelta(minutes=15)


def test_high_co2_recommends_action():
    engine = populated()
    result = engine.recommend(engine.build_context(datetime.now(timezone.utc)))
    assert result.action in {"air_normal", "air_fast"}
    assert result.duration_minutes == 30
    assert result.input_quality == "good"


def test_dust_caps_flow():
    engine = populated(outdoor_pm10=180)
    result = engine.recommend(engine.build_context(datetime.now(timezone.utc)))
    assert result.flow <= 100
    assert "沙尘" in result.reason


def test_stale_input_disables_action():
    engine = populated()
    engine.states["co2"] = state("sensor.co2", 1200, minutes_old=20)
    result = engine.recommend(engine.build_context(datetime.now(timezone.utc)))
    assert result.action == "no_action"
    assert result.input_quality == "degraded"
    assert result.critical_input_quality == "degraded"


def test_unchanged_fan_state_does_not_become_stale():
    engine = populated()
    engine.states["fan"] = state("fan.air", "off", minutes_old=120)
    engine.states["fan_level"] = state("select.flow", 300, minutes_old=120)
    context = engine.build_context(datetime.now(timezone.utc))
    assert context.quality == "good"
    assert "fan" not in context.stale
    assert "fan_level" not in context.stale


def test_manual_low_co2_minimum_run():
    engine = populated(co2=480)
    engine.last_fan_state = "off"
    transition = engine.update(state("fan.air", "on"))
    assert transition["event"] == "manual_on"
    assert engine.manual.state == "manual_low_co2_minimum_run"
    assert engine.manual.minimum_run_until is not None


def test_lockout_is_bounded_and_repeated_off_extends():
    engine = populated(co2=550)
    context = engine.build_context(datetime.now(timezone.utc))
    normal = engine.lockout_minutes(context, False)
    repeated = engine.lockout_minutes(context, True)
    assert 30 <= normal <= 480
    assert normal < repeated <= 480


def test_manual_state_round_trip():
    original = ManualState(
        state="manual_off_lockout",
        actor="human_ha",
        lockout_until=datetime.now(timezone.utc) + timedelta(hours=2),
        last_manual_off=datetime.now(timezone.utc),
        repeated_off_count=2,
    )
    restored = ManualState.from_dict(original.json_dict())
    assert restored == original


def test_manual_flow_change_creates_only_flow_lease():
    engine = populated()
    engine.last_fan_level = "300"
    transition = engine.update(
        state("select.flow", 100, context={"user_id": "operator"})
    )
    assert transition["manual_lease"] is True
    assert set(engine.manual.overrides) == {"flow"}
    lease = engine.manual.overrides["flow"]
    assert lease.expires_at - lease.started_at == timedelta(minutes=15)
    authority, priority = engine.active_authority(
        engine.build_context(datetime.now(timezone.utc))
    )
    assert (authority, priority) == ("manual_flow", 4)


def test_manual_power_lease_outranks_flow_lease():
    engine = populated(co2=650)
    engine.last_fan_level = "300"
    engine.update(state("select.flow", 100, context={"user_id": "operator"}))
    engine.last_fan_state = "off"
    engine.update(state("fan.air", "on", context={"user_id": "operator"}))
    authority, priority = engine.active_authority(
        engine.build_context(datetime.now(timezone.utc))
    )
    assert set(engine.manual.overrides) == {"flow", "power"}
    assert (authority, priority) == ("manual_power", 3)


def test_power_lease_releases_below_600():
    engine = populated(co2=650)
    engine.last_fan_state = "off"
    engine.update(state("fan.air", "on", context={"user_id": "operator"}))
    assert "power" in engine.manual.overrides
    engine.states["co2"] = state("sensor.co2", 590)
    engine.build_context(datetime.now(timezone.utc))
    assert "power" not in engine.manual.overrides

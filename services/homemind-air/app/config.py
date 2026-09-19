from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _read_secret(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class Settings:
    ha_ws_url: str = os.getenv("HA_WS_URL", "ws://127.0.0.1:8123/api/websocket")
    ha_token_file: str = os.getenv("HA_TOKEN_FILE", "/data/secrets/ha_token")
    mqtt_host: str = os.getenv("MQTT_HOST", "127.0.0.1")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_username: str = os.getenv("MQTT_USERNAME", "homemind")
    mqtt_password_file: str = os.getenv("MQTT_PASSWORD_FILE", "/data/secrets/mqtt_password")
    database_path: str = os.getenv("DATABASE_PATH", "/data/homemind-air.sqlite3")
    ephemeris_path: str = os.getenv("EPHEMERIS_PATH", "/data/ephemeris/de440s.bsp")
    timezone: str = os.getenv("TZ", "Asia/Shanghai")
    evaluation_seconds: int = int(os.getenv("EVALUATION_SECONDS", "30"))
    climate_profile: str = os.getenv("CLIMATE_PROFILE", "xian_cold_monsoon")
    entity_ids: dict[str, str] = field(default_factory=lambda: {
        "co2": "sensor.dmaker_t2017_ee71_co2_density",
        "indoor_pm25": "sensor.dmaker_t2017_ee71_pm25_density",
        "indoor_temperature": "sensor.temperature_humidity_sensor_d4f2_temperature",
        "indoor_humidity": "sensor.temperature_humidity_sensor_d4f2_humidity",
        "fan": "fan.dmaker_t2017_ee71_air_fresh",
        "fan_level": "select.dmaker_t2017_ee71_fan_level",
        "heater": "switch.dmaker_t2017_ee71_heater",
        "heat_level": "select.dmaker_t2017_ee71_heat_level",
        "fresh_air_info": "button.dmaker_t2017_ee71_info",
        "weather": "weather.xi_an_he_feng_tian_qi",
        "sun": "sun.sun",
        "enabled": "input_boolean.homemind_air_controller_enabled",
        "control_level": "input_select.homemind_air_control_level",
    })

    @property
    def ha_token(self) -> str:
        return _read_secret(self.ha_token_file)

    @property
    def mqtt_password(self) -> str:
        return _read_secret(self.mqtt_password_file)

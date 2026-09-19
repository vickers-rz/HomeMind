import asyncio
import json
from pathlib import Path

from app.mqtt_bus import MQTTBus


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ha-package" / "homemind_air.yaml"


def _block(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_ha_executor_consumes_engine_actions_without_reimplementing_policy():
    text = PACKAGE.read_text()
    start = _block(text, "  - id: homemind_air_dynamic_start", "  - id: homemind_air_dynamic_stop")
    stop = _block(text, "  - id: homemind_air_dynamic_stop", "  - id: homemind_air_mqtt_action_executor")

    assert "sensor.homemind_air_action" in start
    assert "to: air_normal" in start
    assert "sensor.homemind_air_start_co2" not in start
    assert "sensor.homemind_air_start_pm25" not in start
    assert "sensor.homemind_air_input_quality" not in start

    assert "sensor.homemind_air_action" in stop
    assert "to: air_off" in stop
    assert 'delay: "00:02:00"' not in stop
    assert "sensor.homemind_air_target_co2" not in stop
    assert "sensor.homemind_air_target_pm25" not in stop
    assert "sensor.homemind_air_input_quality" not in stop


def test_native_docker_build_does_not_default_s6_to_arm64():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert 'TARGETARCH:-$(apk --print-arch)' in dockerfile
    assert 'amd64|x86_64' in dockerfile
    assert 'arm64|aarch64' in dockerfile


def test_mqtt_discovery_exposes_action_and_critical_quality():
    class FakeClient:
        def __init__(self):
            self.messages = []

        async def publish(self, topic, payload, qos=0, retain=False):
            self.messages.append((topic, payload, qos, retain))

    async def scenario():
        bus = MQTTBus("127.0.0.1", 1883, "user", "password")
        bus.client = FakeClient()
        await bus.discovery()
        return bus.client.messages

    messages = asyncio.run(scenario())
    topic, payload, qos, retain = messages[-1]
    assert topic == "homeassistant/device/homemind_air/config"
    assert qos == 1 and retain is True
    discovery = json.loads(payload)
    components = discovery["components"]
    assert components["action"]["state_topic"] == "homemind/air/v1/recommendation"
    assert components["action"]["value_template"] == "{{ value_json.action }}"
    assert components["critical_input_quality"]["state_topic"] == "homemind/air/v1/recommendation"
    assert components["outdoor_temperature"]["state_topic"] == "homemind/air/v1/recommendation"
    assert components["outdoor_temperature"]["device_class"] == "temperature"
    assert components["outdoor_temperature_source"]["state_topic"] == "homemind/air/v1/recommendation"
    assert components["seasonal_mode"]["state_topic"] == "homemind/air/v1/recommendation"
    assert components["climate_exchange_factor"]["state_topic"] == "homemind/air/v1/recommendation"
    assert components["indoor_absolute_humidity"]["state_topic"] == "homemind/air/v1/recommendation"
    assert components["outdoor_absolute_humidity"]["state_topic"] == "homemind/air/v1/recommendation"

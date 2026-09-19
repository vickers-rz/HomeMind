from __future__ import annotations

import asyncio
from contextlib import suppress
import json
from typing import Any

import aiomqtt


BASE = "homemind/air/v1"


class MQTTBus:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.client: aiomqtt.Client | None = None

    async def __aenter__(self):
        self.client = aiomqtt.Client(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            identifier="homemind-air-engine",
            will=aiomqtt.Will(f"{BASE}/availability", b"offline", qos=1, retain=True),
        )
        await self.client.__aenter__()
        await self.publish("availability", "online", retain=True)
        return self

    async def __aexit__(self, *args):
        if self.client:
            with suppress(Exception):
                await asyncio.wait_for(
                    self.publish("availability", "offline", retain=True),
                    timeout=2,
                )
            with suppress(Exception):
                await asyncio.wait_for(self.client.__aexit__(*args), timeout=3)

    async def publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        assert self.client
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        await self.client.publish(f"{BASE}/{topic}", body, qos=1, retain=retain)

    async def discovery(self) -> None:
        assert self.client
        components = {
            "availability": {"platform": "binary_sensor", "device_class": "connectivity", "value_template": "{{ 'ON' if value_json.online else 'OFF' }}"},
            "status": {"platform": "sensor", "value_template": "{{ value_json.state }}"},
            "input_quality": {"platform": "sensor", "value_template": "{{ value_json.input_quality }}"},
            "recommended_flow": {"platform": "sensor", "unit_of_measurement": "m³/h", "value_template": "{{ value_json.flow }}"},
            "recommended_minutes": {"platform": "sensor", "unit_of_measurement": "min", "value_template": "{{ value_json.duration_minutes }}"},
            "weather_score": {"platform": "sensor", "value_template": "{{ value_json.weather_score }}"},
            "demand": {"platform": "sensor", "value_template": "{{ value_json.demand }}"},
            "authority": {"platform": "sensor", "value_template": "{{ value_json.authority }}"},
            "priority": {"platform": "sensor", "value_template": "{{ value_json.priority }}"},
            "manual_state": {"platform": "sensor", "value_template": "{{ value_json.state }}"},
            "manual_overrides": {"platform": "sensor", "value_template": "{{ value_json.overrides | list | join(',') if value_json.overrides else 'none' }}"},
            "solar_longitude": {"platform": "sensor", "unit_of_measurement": "°", "value_template": "{{ value_json.longitude }}"},
            "current_term": {"platform": "sensor", "value_template": "{{ value_json.current_term }}"},
            "next_term": {"platform": "sensor", "value_template": "{{ value_json.next_term }}"},
        }
        discovery = {
            "device": {
                "identifiers": ["homemind_air"],
                "name": "HomeMind Air",
                "manufacturer": "HomeMind",
                "model": "Air Decision Hub",
                "sw_version": "0.3.0",
            },
            "origin": {"name": "HomeMind Air", "sw": "0.3.0", "url": "https://github.com/vickers-rz/HomeMind"},
            "availability_topic": f"{BASE}/availability",
            "components": {},
        }
        extra = {'target_co2': 'ppm', 'target_pm25': 'µg/m³', 'start_co2': 'ppm', 'start_pm25': 'µg/m³', 'minimum_run_minutes': 'min',
                 'estimated_remaining_minutes': 'min', 'lockout_until': None, 'minimum_run_until': None,
                 'flow_hold_until': None, 'reason': None, 'control_output': None}
        for key, unit in extra.items():
            components[key] = {'platform': 'sensor', 'value_template': "{{ value_json." + key + " if value_json." + key + " is not none else 'None' }}"}
            if unit:
                components[key]['unit_of_measurement'] = unit
            if key.endswith('_until'):
                components[key]['device_class'] = 'timestamp'
        components['reason']['value_template'] = '{{ value_json.reason[:240] }}'
        for object_id, component in components.items():
            state_topic = "status"
            if object_id in extra or object_id in {"recommended_flow", "recommended_minutes", "weather_score", "demand", "input_quality", "authority", "priority"}:
                state_topic = "recommendation"
            elif object_id in {"manual_state", "manual_overrides"}:
                state_topic = "manual_state"
            elif object_id in {"solar_longitude", "current_term", "next_term"}:
                state_topic = "solar_season"
            discovery["components"][object_id] = {
                "platform": component.pop("platform"),
                "unique_id": f"homemind_air_{object_id}",
                "name": object_id.replace("_", " ").title(),
                "state_topic": f"{BASE}/{state_topic}",
                **component,
            }
            if object_id in {'reason', 'control_output'}:
                discovery['components'][object_id]['json_attributes_topic'] = f'{BASE}/recommendation'
        await self.client.publish("homeassistant/device/homemind_air/config", json.dumps(discovery), qos=1, retain=True)

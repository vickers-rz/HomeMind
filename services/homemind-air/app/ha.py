from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import aiohttp

from .models import EntityState

LOG = logging.getLogger(__name__)


class HAWebSocket:
    def __init__(self, url: str, token: str, wanted: set[str]):
        self.url = url
        self.token = token
        self.wanted = wanted
        self.last_message_monotonic = 0.0

    @staticmethod
    def _entity(raw: dict[str, Any]) -> EntityState:
        return EntityState(
            entity_id=raw["entity_id"],
            state=raw["state"],
            attributes=raw.get("attributes", {}),
            last_updated=datetime.fromisoformat(raw["last_updated"].replace("Z", "+00:00")),
            context=raw.get("context", {}),
            last_reported=datetime.fromisoformat(raw['last_reported'].replace('Z', '+00:00')) if raw.get('last_reported') else None,
        )

    async def stream(self) -> AsyncIterator[tuple[str, EntityState | list[EntityState]]]:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=90)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(self.url, heartbeat=30) as ws:
                required = await ws.receive_json()
                if required.get("type") != "auth_required":
                    raise RuntimeError("HA did not request authentication")
                await ws.send_json({"type": "auth", "access_token": self.token})
                auth = await ws.receive_json()
                if auth.get("type") != "auth_ok":
                    raise RuntimeError(f"HA authentication failed: {auth.get('message', 'unknown')}")

                await ws.send_json({"id": 2, "type": "subscribe_trigger", "trigger": {"platform": "state", "entity_id": sorted(self.wanted)}})
                subscribed = await ws.receive_json()
                if not subscribed.get("success"):
                    raise RuntimeError("HA selected state subscription failed")
                await ws.send_json({"id": 3, "type": "subscribe_events", "event_type": "automation_triggered"})
                await ws.receive_json()
                await ws.send_json({"id": 4, "type": "get_states"})
                initial = await ws.receive_json()
                while initial.get('id') != 4:
                    initial = await ws.receive_json()
                if not initial.get("success"):
                    raise RuntimeError("HA get_states failed")
                yield "initial", [self._entity(v) for v in initial["result"] if v["entity_id"] in self.wanted]

                weather = next((e for e in self.wanted if e.startswith('weather.')), None)
                if weather:
                    await ws.send_json({"id": 5, "type": "weather/subscribe_forecast", "entity_id": weather, "forecast_type": "hourly"})
                next_ping = asyncio.get_running_loop().time() + 25
                ping_id = 100
                snapshot_id = None
                snapshot_at = asyncio.get_running_loop().time()
                pending_ping = False
                while not ws.closed:
                    delay = max(0.1, next_ping-asyncio.get_running_loop().time())
                    try:
                        message = await asyncio.wait_for(ws.receive(), delay)
                    except TimeoutError:
                        if pending_ping:
                            raise RuntimeError('HA application heartbeat timed out')
                        ping_id += 1
                        await ws.send_json({'id': ping_id, 'type': 'ping'})
                        if asyncio.get_running_loop().time()-snapshot_at >= 300:
                            # Low-frequency report freshness check: equal sensor
                            # values do not emit state_changed on modern HA.
                            ping_id += 1
                            snapshot_id = ping_id
                            await ws.send_json({'id': snapshot_id, 'type': 'get_states'})
                            snapshot_at = asyncio.get_running_loop().time()
                        pending_ping = True
                        next_ping = asyncio.get_running_loop().time() + 25
                        continue
                    self.last_message_monotonic = asyncio.get_running_loop().time()
                    if message.type != aiohttp.WSMsgType.TEXT:
                        raise RuntimeError('HA WebSocket closed')
                    payload = json.loads(message.data)
                    if snapshot_id is not None and payload.get('id') == snapshot_id and payload.get('success'):
                        yield 'initial', [self._entity(v) for v in payload['result'] if v['entity_id'] in self.wanted]
                        continue
                    if payload.get('type') == 'pong':
                        pending_ping = False
                        yield 'heartbeat', []
                        continue
                    if payload.get('id') == 5:
                        if payload.get('type') == 'event':
                            yield 'forecast', payload.get('event', {})
                        continue
                    if payload.get("type") != "event":
                        continue
                    if payload.get('id') == 3:
                        yield 'automation', payload.get('event', {})
                        continue
                    trigger = payload.get('event', {}).get('variables', {}).get('trigger', {})
                    data = payload.get("event", {}).get("data", {})
                    raw = trigger.get('to_state') or data.get("new_state")
                    if raw and raw.get("entity_id") in self.wanted:
                        yield "change", self._entity(raw)

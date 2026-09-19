from __future__ import annotations

import asyncio
import json
import logging
import signal
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .astronomy import SolarCalculator
from .config import Settings
from .db import Store
from .dynamic import DynamicEngine
from .ha import HAWebSocket
from .mqtt_bus import MQTTBus
from .models import ManualState

LOG = logging.getLogger("homemind_air")


async def run() -> None:
    settings = Settings()
    store = Store(settings.database_path)
    engine = DynamicEngine(settings.entity_ids, climate_profile=settings.climate_profile)
    engine.manual = ManualState.from_dict(store.get("manual_state"))
    engine.restore(store.get("runtime"))
    # One-time correction for the automatic stop/start sequence that was
    # misclassified as manual_assumed before HA dynamic automations became the
    # authoritative execution path. The timestamps are intentionally exact so
    # genuine physical/manual actions are never generalized away.
    false_lock_at = datetime.fromisoformat("2026-09-07T08:59:08.702952+00:00")
    false_auto_on_at = datetime.fromisoformat("2026-09-07T09:03:05.570689+00:00")
    # The first live stop after changing the HA stop automation to `single`
    # completed just beyond the old two-minute context TTL. Correct only that
    # exact deployment event; the longer TTL below prevents recurrence.
    false_stop_after_dwell_at = datetime.fromisoformat("2026-09-07T09:56:01.835603+00:00")
    power_override = engine.manual.overrides.get("power")
    correction_reason = None
    previous_manual = None
    if (
        engine.manual.state == "manual_run"
        and engine.manual.actor == "manual_assumed"
        and engine.manual.last_manual_off == false_lock_at
        and power_override is not None
        and power_override.started_at == false_auto_on_at
        and engine.runtime.get("started_at") is not None
        and datetime.fromisoformat(engine.runtime["started_at"]) == false_auto_on_at
    ):
        previous_manual = engine.manual.json_dict()
        minimum_run_until = engine.manual.minimum_run_until
        engine.manual = ManualState(
            state="automatic",
            actor="ha_automation",
            minimum_run_until=minimum_run_until,
        )
        engine.runtime["manual_session"] = False
        engine.runtime["auto_resume_at"] = false_auto_on_at.isoformat()
        engine.runtime["lock_recalculated_at"] = None
        engine.runtime["lock_released"] = True
        engine.runtime["repeated_veto"] = False
        correction_reason = "automatic_stop_start_sequence_misclassified_before_executor_whitelist_fix"
    elif (
        engine.manual.state == "manual_off_lockout"
        and engine.manual.actor == "manual_assumed"
        and engine.manual.last_manual_off in {false_lock_at, false_stop_after_dwell_at}
    ):
        previous_manual = engine.manual.json_dict()
        engine.manual = ManualState(state="idle", actor="ha_automation")
        engine.runtime["manual_session"] = False
        engine.runtime["lock_recalculated_at"] = None
        engine.runtime["lock_released"] = True
        engine.runtime["repeated_veto"] = False
        correction_reason = "automatic_stop_misclassified_before_executor_whitelist_fix"
    if correction_reason:
        corrected_at = datetime.now(timezone.utc).isoformat()
        store.event(
            corrected_at,
            "policy_state_corrected",
            {
                "reason": correction_reason,
                "previous_manual_state": previous_manual,
            },
            engine.runtime.get("session_id"),
        )
        store.session(engine.runtime, engine.manual.json_dict(), corrected_at)
    solar = SolarCalculator(settings.ephemeris_path, settings.timezone)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async with MQTTBus(settings.mqtt_host, settings.mqtt_port, settings.mqtt_username, settings.mqtt_password) as bus:
        await bus.discovery()
        assert bus.client
        await bus.client.subscribe("homemind/air/v1/feedback", qos=1)
        await bus.client.subscribe("homemind/air/v1/action/result", qos=1)
        solar_data = asdict(await asyncio.to_thread(solar.season, datetime.now(timezone.utc)))
        engine.solar = solar_data
        await bus.publish("solar_season", solar_data, retain=True)
        connection = {"ha_connected": False, "last_ha_message_at": None}

        async def evaluator() -> None:
            last_cleanup = None
            solar_at = datetime.now(timezone.utc)
            previous_mode = None
            previous_manual = None
            while not stop.is_set():
                now = datetime.now(timezone.utc)
                if now-solar_at >= timedelta(minutes=15):
                    engine.solar = asdict(await asyncio.to_thread(solar.season, now))
                    await bus.publish('solar_season', engine.solar, retain=True)
                    solar_at = now
                context = engine.build_context(now)
                if not connection['ha_connected']:
                    context.stale.append('fan')
                    context.quality = 'degraded'
                recommendation = engine.recommend(context)
                recommendation_payload = recommendation.json_dict()
                recommendation_payload["context_hash"] = engine.context_hash(context)
                recommendation_payload["updated_at"] = now.isoformat()
                recommendation_payload['stale'] = context.stale
                enabled_state = engine.states.get('enabled')
                controller_enabled = bool(enabled_state and enabled_state.state == 'on')
                bounded_auto = recommendation.execution_mode == 'bounded_auto'
                automatic_control_active = controller_enabled and bounded_auto
                recommendation_payload['control_output'] = (
                    'HA动态自动控制' if automatic_control_active else '自动控制已禁用'
                )
                recommendation_payload['execution_path'] = 'ha_engine_action_executor'
                recommendation_payload['forecast_available'] = context.values.get('forecast', {}).get('available', False)
                recommendation_payload['lockout_remaining_minutes'] = max(0, int((datetime.fromisoformat(recommendation.lockout_until)-now).total_seconds()/60)) if recommendation.lockout_until else 0
                if previous_mode != recommendation.execution_mode:
                    store.event(now.isoformat(), 'mode_changed', {'previous': previous_mode, 'current': recommendation.execution_mode, 'pending_requests': 'invalidated'})
                    previous_mode = recommendation.execution_mode
                # Audit is committed BEFORE publishing anything. Device execution is
                # intentionally delegated to the two HA dynamic automations.
                store.decision(recommendation_payload, context.values)
                store.session(engine.runtime, engine.manual.json_dict(), now.isoformat())
                manual_snapshot = engine.manual.json_dict()
                if previous_manual != manual_snapshot:
                    store.event(now.isoformat(), 'policy_state_changed', manual_snapshot, recommendation.session_id)
                    previous_manual = manual_snapshot
                if last_cleanup != now.date():
                    store.cleanup(now, engine.runtime.get('session_id'))
                    last_cleanup = now.date()
                await bus.publish("recommendation", recommendation_payload, retain=True)
                await bus.publish("manual_state", engine.manual.json_dict(), retain=True)
                await bus.publish("status", {
                    "state": (
                        "HA动态自动控制" if connection['ha_connected'] and automatic_control_active
                        else "自动控制已禁用" if connection['ha_connected']
                        else "degraded"
                    ),
                    "online": True,
                    "input_quality": context.quality,
                    "stale": context.stale,
                    "last_evaluation": now.isoformat(),
                    "control_output": "ha_engine_action_executor" if automatic_control_active else "disabled_by_user",
                }, retain=True)
                health_tmp = Path("/data/health.json.tmp")
                health_tmp.write_text(json.dumps({
                    "updated_at": now.isoformat(),
                    "ha_state_count": len(engine.states),
                    "input_quality": context.quality,
                    **connection,
                }), encoding="utf-8")
                health_tmp.replace("/data/health.json")
                store.set("last_recommendation", recommendation_payload, now.isoformat())
                try:
                    await asyncio.wait_for(stop.wait(), timeout=settings.evaluation_seconds)
                except TimeoutError:
                    pass

        async def consume_ha() -> None:
            backoff = 1
            while not stop.is_set():
                try:
                    client = HAWebSocket(settings.ha_ws_url, settings.ha_token, set(settings.entity_ids.values()))
                    async for kind, item in client.stream():
                        connection["ha_connected"] = True
                        connection["last_ha_message_at"] = datetime.now(timezone.utc).isoformat()
                        backoff = 1
                        if kind == 'automation':
                            entity = item.get('data', {}).get('entity_id', '')
                            if entity in {
                                'automation.homemind_air_dong_tai_qi_dong',
                                'automation.homemind_air_dong_tai_ting_zhi',
                                'automation.homemind_air_mqttan_quan_zhi_xing_qi',
                                # Historical IDs retained for compatibility with earlier deployments.
                                'automation.gao_yu_900ppmkai_xin_feng_ji',
                                'automation.di_yu_700ppmjiu_guan_ji',
                                'automation.homemind_air_mqtt_action_executor',
                            }:
                                ctx = item.get('context', {}).get('id')
                                if ctx:
                                    # Dynamic stop deliberately waits two minutes,
                                    # then the device integration may need another
                                    # polling cycle to report the fan transition.
                                    engine.known_contexts[ctx] = datetime.now(timezone.utc) + timedelta(minutes=5)
                            continue
                        if kind == 'forecast':
                            rows = item.get('forecast', [])
                            now_dt = datetime.now(timezone.utc)
                            hours = {}
                            for hour in (1, 3, 6):
                                valid = []
                                for row in rows:
                                    try:
                                        at = datetime.fromisoformat(row['datetime'].replace('Z', '+00:00'))
                                        if at >= now_dt:
                                            valid.append((abs((at-now_dt).total_seconds()-hour*3600), row))
                                    except (KeyError, ValueError, TypeError):
                                        continue
                                if valid:
                                    distance, row = min(valid, key=lambda x: x[0])
                                    if distance <= 3600:
                                        hours[str(hour)] = {k: row.get(k) for k in ('datetime', 'temperature', 'humidity', 'condition', 'precipitation_probability', 'wind_speed')}
                            engine.forecast = {'available': bool(hours), 'updated_at': now_dt.isoformat(), 'hours': hours}
                            continue
                        items = item if isinstance(item, list) else [item]
                        for state in items:
                            transition = engine.update(state, initial=kind == 'initial')
                            if transition:
                                now = datetime.now(timezone.utc).isoformat()
                                event_kind = (
                                    "setting_transition"
                                    if str(transition.get("event", "")).endswith("_change")
                                    else "fan_transition"
                                )
                                store.event(now, event_kind, transition)
                                store.session(engine.runtime, engine.manual.json_dict(), now)
                                await bus.publish("manual_state", engine.manual.json_dict(), retain=True)
                        if stop.is_set():
                            break
                    connection['ha_connected'] = False
                    raise RuntimeError('HA stream ended')
                except sqlite3.Error:
                    raise
                except Exception as exc:
                    connection["ha_connected"] = False
                    LOG.warning("HA WebSocket disconnected: %s", exc)
                    await bus.publish("status", {"state": "degraded", "online": True, "input_quality": "unavailable", "error": type(exc).__name__}, retain=True)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)

        async def consume_mqtt() -> None:
            assert bus.client
            async for message in bus.client.messages:
                if stop.is_set():
                    break
                topic = str(message.topic)
                try:
                    payload = json.loads(bytes(message.payload).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError('Expected JSON object')
                except (UnicodeDecodeError, ValueError) as exc:
                    payload = {"invalid_payload": True, "error": str(exc)}
                now = datetime.now(timezone.utc).isoformat()
                if topic.endswith("/feedback"):
                    store.event(now, "feedback_ignored", {'reason': 'ha_dynamic_automation_authority', 'request_id': payload.get('request_id')})
                elif topic.endswith("/action/result"):
                    store.event(now, "action_result", payload, payload.get("request_id"))
                    store.result(payload)

        tasks = [
            asyncio.create_task(evaluator()),
            asyncio.create_task(consume_ha()),
            asyncio.create_task(consume_mqtt()),
        ]
        stopper = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([*tasks, stopper], return_when=asyncio.FIRST_COMPLETED)
        failure = next((t.exception() for t in done if t is not stopper and not t.cancelled() and t.exception()), None)
        if failure:
            LOG.error('Worker failed: %s', type(failure).__name__)
            await bus.publish('status', {'state': 'fault', 'online': False, 'input_quality': 'unavailable', 'error': type(failure).__name__}, retain=True)
        stopper.cancel()
        LOG.info("Shutdown requested; cancelling worker tasks")
        for task in tasks:
            task.cancel()
        _, pending = await asyncio.wait(tasks, timeout=3)
        if pending:
            LOG.warning("Shutdown deadline reached with %d worker task(s) pending", len(pending))
        if failure:
            raise failure


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()

# HomeMind Air deployment record

## Current deployment

### 0.3.0 observation delivery — 2026-09-07

Current image: `homemind-air:0.3.0`. The remaining sections below describe the
historical 0.2.0 baseline, not proof of automatic execution in 0.3.0.

- Current behavior: dynamic concentration/flow/lease recommendations, hourly
  forecasts, persistent sessions, per-evaluation SQLite audit; **observe-only**.
- Verified 39 tests; HA check_config passed; HA reload succeeded without restart.
- First live check: healthy, 10 HA inputs, input quality good, forecasts for
  1/3/6 hours present, new MQTT sensors visible; action table empty.
- HA approval helper off, notifications disabled, baseline automations on.
- A WebSocket command-ID ordering error was corrected and covered by an
  in-process protocol test before the observation period starts.
- Rollback container: `homemind-air-pre030-20260907-130157` (0.2.0).
- HA backup and complete container inspection:
  `<HA_CONFIG_DIR>/backups/homemind-air-030-20260907-130157/`.
- Consistent SQLite backup via SQLite backup API:
  `<HOMEMIND_DATA_DIR>/pre030-20260907-130157.sqlite3`.
- See [OBSERVATION-030.md](OBSERVATION-030.md) for exact policy and remaining
  execution-guard / baseline-handoff work. Seven-day stability is not yet verified.

Rollback: stop the current container, rename it for investigation, rename the
0.2.0 rollback container to `homemind-air`, then start it. The schema additions
are additive, so keep the database and its audit records. Restore the HA package
from the backup only if necessary; it reintroduces the old approval bypass, so
leave all HomeMind execution/approval helpers off. Never replace a live SQLite
database with a copied file while either engine is running.

### Historical 0.2.0 baseline

- Deployment date: 2026-09-07 (Asia/Shanghai)
- Host: N100 iStoreOS (private LAN host; address intentionally omitted)
- Container: `homemind-air`
- Image: `homemind-air:0.2.0` (`linux/amd64`)
- Home Assistant: Container `2026.8.2`
- Persistent data: `<HOMEMIND_DATA_DIR>`
- HA package: `<HA_CONFIG_DIR>/packages/homemind_air.yaml`
- HA rollback bundle: `<HA_CONFIG_DIR>/backups/homemind-air-20260906-2020`

The service is intentionally deployed in phase B/C observe-only mode. The engine
publishes status, normalized input quality, recommendations, manual state, and
solar-term data. It does not publish `action/request` messages in version `0.2.0`.

## Active safety posture

- `input_boolean.homemind_air_controller_enabled`: `off`
- `input_select.homemind_air_control_level`: `observe`
- Existing HA 900/700 ppm automations: retained and enabled
- MQTT broker listener: `127.0.0.1:1883` only
- Container: host network, non-privileged, no Docker socket, read-only root
- Capabilities: only `SETUID`, `SETGID`, and `KILL` (required by s6 to supervise UID 1000 processes)
- HA actions: only through the fixed MQTT Policy Guard and whitelist script

The HA guard package is loaded, but rejects ordinary requests while the controller
is disabled. Explicit approval support is reserved for a later rollout phase.

## Interfaces

- HA WebSocket: state snapshots, selected `state_changed` events, and context
- MQTT: Discovery, retained diagnostics/recommendations, feedback, and guarded actions
- REST: deployment diagnostics only

No external Unix socket interface is used. The Docker socket must never be mounted.

## Verified results

At deployment completion:

- HA WebSocket subscribed to the selected entities and recovered after HA restart.
- HA official MQTT integration loaded against the loopback-only broker.
- MQTT Discovery created HomeMind Air entities in HA.
- Input quality reached `good` with ten tracked HA states.
- The container health state was `healthy`.
- No `action/request` message was observed.
- The fan remained off throughout deployment.
- Both legacy IAQ automations remained enabled.
- HA configuration validation passed before restart.
- MQTT feedback and action-result messages are persisted to SQLite.
- Manual arbitration state is restored from SQLite after process restart.
- Health checks verify MQTT, HA WebSocket state, tracked state count, and SQLite writability.
- Unchanged fan state/level no longer causes false input-staleness degradation.
- Manual intervention is represented as separate power, flow, and mode leases.
- Recommendation telemetry exposes BACnet-inspired authority and priority values.
- A controlled container stop completed in 3 seconds with exit code 0 and no OOM kill.

Xiaomi Home entity-domain, invalid-slug, and `xiaomi-r24r00` humidity-range
errors were corrected with compatibility patches. Deprecated unit constants and
device-tracker APIs in Xiaomi Home and Xiaomi Miot were also corrected. After the
final HA restart, none of those warnings or errors recurred. HA's generic warning
that custom integrations are not officially tested remains expected metadata,
not a runtime fault.

Compatibility rollback bundles:

- `<HA_CONFIG_DIR>/backups/xiaomi-home-compat-20260907-074008`
- `<HA_CONFIG_DIR>/backups/ha-2027-compat-20260907-074501`

Implementation details are recorded in [COMPATIBILITY.md](COMPATIBILITY.md).

## Routine checks

```sh
docker inspect --format '{{.State.Health.Status}}' homemind-air
cat <HOMEMIND_DATA_DIR>/health.json
docker logs --since 10m homemind-air
docker exec homeassistant python -m homeassistant --script check_config --config /config
```

Expected HA values during the observation period:

```text
binary_sensor.homemind_air_availability = on
sensor.homemind_air_status = running
sensor.homemind_air_input_quality = good
input_boolean.homemind_air_controller_enabled = off
input_select.homemind_air_control_level = observe
```

## Rollback

To remove only the HA package, move `homemind_air.yaml` out of `/config/packages`,
run the HA configuration check, and restart HA. To stop the decision service, stop
`homemind-air`; the existing 900/700 ppm automations remain independent.

Do not remove the persistent directory or rollback bundle during observation.

## Promotion gates

Remain in `observe` for at least seven days. Before moving to `recommend`, verify:

1. No unexplained fan-source classifications or state transitions.
2. WebSocket/MQTT recovery after restarts without duplicate events.
3. No notification storms.
4. Weather and sensor freshness degradation behaves conservatively.
5. Manual-on/manual-off scenarios match the test matrix.

Promotion to `bounded_auto` requires a separate explicit change and a new backup.

## Ordinary-weather legacy IAQ floor — 2026-09-07 23:06 CST

User requested the original fixed automations as minimum IAQ protection when
weather is not adverse. DynamicEngine now caps start thresholds at 900 ppm CO2
and 26 ug/m3 PM2.5, and stop targets at 700 ppm and 21 ug/m3. Start remains OR;
stop requires both strict lower bounds. Existing CO2 >= comparison can start
at 900 itself, slightly earlier than the original >900 crossing. Cleaner-air
stricter targets, manual leases, dwell and fault guards remain in effect.
Existing adverse classification is dust, outdoor AQI >100, or indoor/outdoor
temperature difference >=15 C; missing weather does not authorize relaxation.
Original Favorite/300 action remains subject to the existing weather flow caps
and manual setting protection.

49 tests passed. Deployed only dynamic.py on top of the running image;
rollback container: homemind-air-pre-baseline-20260907;
rollback image: homemind-air:pre-baseline-20260907.
Live at 23:06:20: healthy, HA connected with 10 inputs, quality good,
bounded_auto. Outdoor AQI 104 selected the preserved adverse branch
(start 950/26, stop 800/21); ordinary-weather bounds verified in tests.

## Separate AQI flow caps from IAQ floor — 2026-09-07 23:20 CST

Supersedes the earlier entry's AQI >100 exception. AQI alone no longer permits
CO2 stop targets above 700 ppm or start thresholds above 900 ppm. Without the
existing dust (PM10 >=150 or weather containing 沙/尘) / temperature-difference
(>=15 C) exceptions, PM start/stop caps remain 26/21 and stop requires BOTH strict
lower bounds. Cleaner-air and low-CO2 manual-session targets can be lower.
Existing AQI-based flow caps and manual/session/fault protections are unchanged.
Dust and thermal exceptions are now explicitly named in the published reason;
they cease applying when their existing predicates are false. No new pollutant
model or ozone limit table was introduced in this change.

61 tests pass, including the actual AQI 104 / CO2 747 and 724 early-stop cases,
strict 700/21 boundaries, AQI 100/101/150/151 boundaries and preserved exceptions.
Only dynamic.py changed in the running image; HA automation already reads the
published targets and rechecks them after its stop delay, so no HA reload needed.
Rollback container: homemind-air-pre-aqi-floor-20260907-2319.
Rollback image: homemind-air:pre-aqi-floor-20260907-2319.
Post-start consistent audit snapshot: /data/aqi-floor-20260907-2320.sqlite3.
The initial pre-start snapshot attempt failed on directory permissions; the
successful snapshot used the service UID after restart. The database schema and
existing audit history were not changed by this deployment.

Live verification at 23:21:14 CST: container healthy, HA connected (10 inputs),
input quality good, bounded_auto. AQI still 104, but targets now 700/21 and
starts 850/26 (earlier CO2 start remains permitted); recommended flow 100.
HA Recorder independently confirms all four published threshold sensors.
Fan remains off from the earlier 23:14 stop, CO2 728; a full natural cycle under
this version has not occurred and is not claimed as validated.

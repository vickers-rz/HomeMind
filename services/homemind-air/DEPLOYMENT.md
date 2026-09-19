# HomeMind Air deployment record

## Current deployment

### 0.5.1 adaptive-learning capture source + shadow learner — 2026-09-19

Repository source has advanced to `homemind-air:0.5.1`, but the realtime live
container remains `homemind-air:0.5.0` at the time of this record. 0.5.1 is a
data-capture preparation release and does not add automatic heater control.

0.5.1 adds the fresh-air unit's local heater state and three-level heat setting
to the realtime context/history:

- `switch.dmaker_t2017_ee71_heater`
- `select.dmaker_t2017_ee71_heat_level`
- local device-info attributes `air_fresh.heater` and
  `air_fresh.heat_level`

Manual heater and heat-level changes are recorded as setting transitions and
receive a 15-minute manual observation lease. The realtime decision policy does
not yet issue heater actions.

A separate `homemind-air-learner:0.1.0` sidecar is running on the N100 in
shadow mode. It has a 1 CPU / 768 MB resource limit, reads the HomeMind SQLite
history, retrains every 15 minutes over the latest 30 days, and writes only
versioned JSON model output to `/data/adaptive_model.json`. It has no Home
Assistant token and no device-control path.

The learner uses episode-based robust system identification with NumPy, SciPy
and scikit-learn. The first historical replay covered about 35.6k decision
samples, 3.5k stable windows and 74 configuration transitions. Initial accepted
shadow estimates included approximately 0.36 h^-1 natural ACH, a 4.6 h derived
thermal time constant, about 1.49 ACH additional fan effect at 300 m3/h, and
about 3.27 h^-1 PM2.5 removal at 300 m3/h. The fan thermal-exchange coefficient
failed validation and was rejected. Heater Level1/Level2/Level3 all have zero
real training samples and therefore zero learned confidence.

The full target architecture, safety shell, confidence gates and staged
shadow -> advisory -> bounded adaptive -> lightweight MPC rollout are documented
in [ADAPTIVE-CONTROL.md](ADAPTIVE-CONTROL.md).

Source regression result before commit/push: 85 tests passed.

### 0.5.0 BLE thermal-moisture + seasonal forecast policy — 2026-09-19

Current image: `homemind-air:0.5.0`. The previous 0.4.2 container is retained as
`homemind-air-pre050-20260919-215656`, with a consistent SQLite backup at
`<HOMEMIND_DATA_DIR>/pre050-20260919-215656.sqlite3`.

0.5.0 makes the nearby Xiaomi MJWSD05MMC BLE thermometer/hygrometer a first-class
thermal/moisture policy input. It was already mapped as `indoor_temperature`
and `indoor_humidity`, but earlier policy used it only shallowly and could mark
an unchanged temperature stale while humidity continued to report. The two
entities are now treated as one paired BLE sample: a recent report from either
keeps both valid for up to 30 minutes when both numeric values remain valid.

Thermal/moisture source model:

- Indoor temperature + RH: local Xiaomi BLE sensor beside the fresh-air unit.
- Intake temperature: local fresh-air-unit `environment.temperature`, with
  QWeather temperature fallback.
- Outdoor absolute humidity: QWeather temperature + QWeather RH from the same
  weather source. Intake temperature is intentionally not mixed with QWeather
  RH because there is no local intake-humidity sensor.
- Outdoor particulate pollution: QWeather/AQI only; the unit PM2.5 sensor
  remains indoor PM2.5.
- Forecast: nearest valid 1/3/6-hour QWeather hourly temperature + humidity.
- Seasonal prior: `CLIMATE_PROFILE=xian_cold_monsoon`, with solar-longitude
  modes `hot_humid`, `autumn_humid`, `cold_dry`, and
  `spring_transition`.

The climate exchange layer is deliberately bounded. It adjusts preferred flow
and manual-off lockout, but does not suppress hard IAQ start conditions.
Direction matters: ventilation is favored when it helps cool/warm or correct
indoor humidity and penalized when it imports moisture during warm/wet seasons
or worsens dryness during the cold/dry season. A materially better 1/3/6-hour
forecast window may reduce preferred flow for nonurgent IAQ; forecast deferral is
disabled once CO₂ or indoor PM2.5 reaches the hard start condition.

The maximum-flow shortcut is also stricter in 0.5.0: AQI <= 100 alone is no
longer sufficient. 300 m3/h additionally requires outdoor PM2.5 <= 35,
PM10 < 150, no dust condition, wind <= 30 km/h, no current precipitation, no
severe temperature delta, and no materially better near-term climate window.

Manual-off lockout keeps the original CO₂/trend/outdoor-pollution base, but its
thermal/moisture correction is now directional. For example, dry outdoor air can
shorten lockout when indoor RH is high, while the same air can lengthen lockout
during a cold/dry season when indoor RH is already low. The combined
thermal/moisture/forecast correction remains bounded to +/-20% of the lockout
duration, and the original manual-off timestamp remains the deadline anchor.

MQTT Discovery additionally exposes:

- `sensor.homemind_air_seasonal_mode`
- `sensor.homemind_air_climate_exchange_factor`
- `sensor.homemind_air_indoor_absolute_humidity`
- `sensor.homemind_air_outdoor_absolute_humidity`

Deployment verification:

- 83 regression tests passed.
- Live BLE input: 25.3 C / 63% RH; both values were accepted as fresh.
- Live intake temperature: 22-23 C from the fresh-air unit.
- Live coherent absolute humidity: indoor about 14.75 g/m3 and outdoor about
  14.82 g/m3, yielding a neutral humidity strategy.
- Solar longitude selected `autumn_humid` (current solar term: 白露).
- QWeather AQI 93 with PM2.5 56 no longer qualified for the 300 m3/h shortcut;
  the live recommendation was 260-280 m3/h as indoor PM2.5 was about 35.
- The existing manual-off lockout remained authoritative throughout deployment:
  action stayed `no_action` and the fan remained off.
- Controller was disabled during the container switch and restored only after
  source/decision verification.
- HomeMind returned healthy with HA WebSocket connected and input quality good.

### 0.4.2 local intake temperature priority — 2026-09-19

Current image: `homemind-air:0.4.2`. The previous 0.4.1 container is retained as
`homemind-air-pre042-20260919-211946`, with a consistent SQLite backup at
`<HOMEMIND_DATA_DIR>/pre042-20260919-211946.sqlite3`.

Outdoor temperature selection now follows:

1. Fresh-air unit local device-info property `environment.temperature` when
   the device-info snapshot is no older than 180 seconds.
2. QWeather `weather.*.temperature` as fallback.
3. No outdoor temperature when neither source is valid.

The separate `sensor.dmaker_t2017_ee71_temperature` entity is intentionally
not used for freshness because the local Xiaomi integration does not refresh its
`last_reported` timestamp while the numeric value remains unchanged. The
device-info entity refreshes locally about every 30 seconds and carries the same
`environment.temperature` property, making it the authoritative live source.

MQTT Discovery now exposes:

- `sensor.homemind_air_outdoor_temperature`
- `sensor.homemind_air_outdoor_temperature_source`

The source value is `fresh_air_intake`, `qweather`, or `none`.
Outdoor PM2.5/PM10 and dust decisions remain sourced from QWeather/AQI inputs;
the unit's `environment.pm2_5_density` remains classified as indoor PM2.5 and
is never substituted for outdoor particulate data.

Deployment verification:

- 70 local regression tests passed.
- Live device-info reported intake temperature 22.0 C while QWeather reported
  19.0 C; HomeMind selected 22.0 C with source `fresh_air_intake`.
- The reason sensor explicitly reported that the outdoor temperature came from
  the fresh-air intake.
- HomeMind returned healthy with 11 HA source entities connected.
- Controller was disabled during the container switch and re-enabled only after
  the new source was validated; the already-running fan remained on without an
  unintended power transition.

### 0.4.1 manual-setting lease adjustment — 2026-09-19

Current image: `homemind-air:0.4.1`. The previous 0.4.0 container is retained as
`homemind-air-pre041-20260919-210630`, with a consistent SQLite backup at
`<HOMEMIND_DATA_DIR>/pre041-20260919-210630.sqlite3`.

Manual flow and preset/mode changes now create a 15-minute override lease
(previously 30 minutes in DynamicEngine; the older base-class fallback was also
normalized from two hours to 15 minutes). During the lease, the engine continues
to calculate and publish a recommendation but will not automatically correct
flow or mode. The lease boundary is covered by regression tests: it is active at
14 minutes and expired at 15 minutes.

The manual-off dynamic lockout algorithm was unchanged in 0.4.1. Its historical
0.4.x policy is documented below; 0.5.0 supersedes the humidity/forecast
correction with the direction-aware climate-exchange model above.

### Historical 0.4.x manual-off lockout algorithm

A manual off event creates a power override anchored to the original manual-off
timestamp. The initial duration is selected from current indoor CO₂:

- CO₂ unavailable: 120 minutes.
- CO₂ < 600 ppm: 240 minutes.
- 600 <= CO₂ < 750 ppm: 180 minutes.
- 750 <= CO₂ < 900 ppm: 90 minutes.
- CO₂ >= 900 ppm: 30 minutes.

Then the engine applies context corrections:

- CO₂ trend uses the last 10 minutes of samples and requires at least six samples
  spanning at least five minutes. Rising at >= 2 ppm/min subtracts 30 minutes;
  falling at <= -2 ppm/min adds 30 minutes.
- Outdoor PM2.5 > 35, PM10 >= 150, or a weather condition containing 沙/尘 adds
  60 minutes.
- Indoor/outdoor temperature delta >= 15 C contributes +60 minutes.
- Absolute-humidity delta > 5 contributes +15 minutes; delta < 2 contributes
  -15 minutes.
- If any available forecast hour differs from current indoor temperature by
  >= 15 C, it contributes +15 minutes.
- The combined temperature/humidity/forecast correction is capped to +/-20% of
  the duration after the CO₂-trend and outdoor-pollution adjustments.
- If the user manually turns the fan off within 30 minutes after an automatic
  resume, the result is forced to at least 240 minutes.
- The final lockout is clamped to 30..480 minutes.

While locked and critical inputs remain valid, the duration is recalculated at
most once every five minutes from current context, but the deadline is always
`original_manual_off_time + recalculated_duration`; recalculation therefore
does not create a sliding window. A continuous critical-input-valid CO₂ level of
>=1500 ppm for 10 minutes activates emergency control, releases the manual power
lock, and allows ventilation to resume.

### 0.4.0 single-policy executor — 2026-09-19

Current image: `homemind-air:0.4.0`. HomeMind Air is running in
`bounded_auto` with `DynamicEngine` as the only IAQ/session state machine.
Home Assistant no longer duplicates CO₂/PM2.5 start/stop thresholds, the
continuous stop dwell, or the anti-short-cycle rule. It executes retained MQTT
recommendations through `sensor.homemind_air_action`:

- `air_normal`: apply the engine-recommended preset/flow and turn on only when
  the fan is currently off; when already running it can perform an authorized
  flow correction.
- `air_off`: turn the fan off.
- `no_action`: leave the device unchanged.

The engine publishes both `input_quality` (whole context) and
`critical_input_quality` (CO₂, PM2.5 and required fan state). Optional
humidity/weather staleness can therefore degrade context quality without
freezing baseline IAQ execution.

Deployment verification:

- Local policy/executor regression suite: 67 tests passed after final deployment regression coverage.
- Home Assistant `check_config` passed before each restart.
- MQTT Discovery created `sensor.homemind_air_action` and
  `sensor.homemind_air_critical_input_quality`.
- Live manual session verification: the fan was already running at 60 m³/h;
  the engine published `air_normal`, the HA executor triggered, and the device
  changed to 100 m³/h. The engine then returned to `no_action`; a later
  recommendation of 80 m³/h remained unchanged because the configured flow
  correction deadband is 40 m³/h.
- After an additional HA restart, HomeMind returned healthy with HA WebSocket
  connected, critical input quality `good`, and the bounded-auto helpers and
  executor automations enabled.
- Flow-change audit now attributes each transition from the HA state context
  (`user_id` / `parent_id`) instead of inferring the actor from the current
  control-session helper.

A first 0.4.0 container build failed before service startup because a plain
native `docker build` did not populate BuildKit's `TARGETARCH`, while the
Dockerfile incorrectly defaulted to arm64. The live 0.3.0 container was
immediately restored. The Dockerfile now falls back to `apk --print-arch` and
accepts both Docker and Alpine architecture names; the rebuilt amd64 image
started normally.

Rollback assets retained from the deployment window:

- Previous container: `homemind-air-pre040-20260919-202030`.
- Previous image snapshot: `homemind-air:pre-040-20260919-202030`.
- Consistent SQLite backup:
  `<HOMEMIND_DATA_DIR>/pre040-20260919-202030.sqlite3`.
- HA package and automation backup:
  `<HA_CONFIG_DIR>/backups/homemind-air-040-20260919-202030/`.

The failed first-build container is retained temporarily as
`homemind-air-failed040-20260919-202030` for deployment audit and can be
removed after the validation window.

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

# HomeMind Air

HomeMind Air is a local fresh-air policy engine for Home Assistant. One container
runs Mosquitto and the Python decision engine under s6-overlay. Home Assistant
WebSocket supplies live device/context state; MQTT supplies discovery,
recommendations, policy state and observability.

## Current control architecture

Version `0.5.1` keeps a single realtime policy/state-machine source of truth while adding a separate shadow learning plane:

```text
Home Assistant state/context
          ↓ WebSocket
DynamicEngine
  - IAQ thresholds
  - manual leases
  - minimum runtime
  - continuous stop dwell
  - anti-short-cycle
  - weather flow limits
  - BLE indoor thermal/humidity context
  - intake-temperature / forecast window selection
  - low-weight seasonal climate prior
  - fault/critical-input guard
          ↓ MQTT recommendation
sensor.homemind_air_action
          ↓
Home Assistant deterministic executor
          ↓
Xiaomi fresh-air device

Historical decisions + device transitions
          ↓
homemind-air-learner (scikit-learn, shadow only)
          ↓
/data/adaptive_model.json
```

In `bounded_auto`, Home Assistant no longer reimplements CO₂/PM2.5 thresholds,
stop dwell or anti-short-cycle logic. It only executes the engine's
`air_normal` and `air_off` actions. `air_normal` is also used to correct the
flow of an already-running fan when the engine authorizes it. Manual flow or
mode changes create a 15-minute override lease before automatic flow correction
may resume. Outdoor temperature uses the fresh-air unit's locally reported
intake temperature when its device-info snapshot is no older than 180 seconds;
QWeather is the fallback. Outdoor PM2.5/PM10 still come from weather/AQI sources,
not from the unit's indoor PM2.5 sensor.

The nearby Xiaomi BLE thermometer/hygrometer is the primary indoor thermal and
humidity context. Temperature and humidity are treated as a paired BLE sample:
a recent report from either entity keeps the pair fresh for up to 30 minutes,
which avoids marking an unchanged temperature stale while humidity continues to
report. Absolute humidity is calculated from coherent source pairs: indoor BLE
temperature+RH and QWeather temperature+RH; intake temperature is never mixed
with QWeather RH because the fresh-air unit has no intake-humidity sensor.

The default `CLIMATE_PROFILE=xian_cold_monsoon` is a low-weight seasonal prior
for the site's cold-region monsoon climate. Solar longitude selects four policy
modes (`hot_humid`, `autumn_humid`, `cold_dry`, `spring_transition`). The prior
only changes the weight of thermal/moisture exchange and manual-off lockout; it
never overrides the hard IAQ start floor. The 1/3/6-hour forecast may lower the
preferred flow when a materially better near-term thermal/moisture window is
available, or favor the current window before conditions worsen.

`input_quality` describes the whole context. `critical_input_quality` only
covers the inputs required for safe device execution, so stale optional humidity
or weather data may degrade context quality without freezing baseline IAQ
control.

0.5.1 also records the fresh-air unit's heater switch and three-level heat setting
into every decision input. Manual heater/heat-level changes are audited as
setting transitions and receive the same 15-minute manual observation lease, but
the realtime controller does **not** automatically operate the heater yet.

A separate `homemind-air-learner` sidecar reads the decision history and trains
an episode-based grey-box room model every 15 minutes using robust scikit-learn
fits. It estimates natural leakage/ACH, fan ventilation effectiveness, envelope
thermal time constant, moisture exchange, PM removal, and—once real samples
exist—heater gain for Level1/Level2/Level3. The learner writes only versioned
JSON to `/data/adaptive_model.json`; it has no Home Assistant token and no
device-control path. Parameters that fail physical-sign/range or holdout
validation remain rejected. The model is currently `shadow` and cannot change
device actions.

The adaptive-control design and rollout plan is in [ADAPTIVE-CONTROL.md](ADAPTIVE-CONTROL.md).
The live deployment and rollback record is in [DEPLOYMENT.md](DEPLOYMENT.md).
The earlier 0.3.0 observation-policy record is retained in
[OBSERVATION-030.md](OBSERVATION-030.md).

## Persistent data

```text
/data/secrets/ha_token
/data/secrets/mqtt_password
/data/secrets/mosquitto.passwd
/data/secrets/mosquitto.acl
/data/ephemeris/de440s.bsp
/data/homemind-air.sqlite3
/data/health.json
/data/adaptive_model.json
```

Do not commit the contents of `/data/secrets`.

## Development

```bash
uv run --extra test pytest -q
docker buildx build --platform linux/amd64 --load -t homemind-air:0.5.1 .
docker build -t homemind-air-learner:0.1.0 learner/

```

## Rollout levels

- `observe`: publish state/recommendations only; executor remains inactive.
- `recommend`: reserved approval workflow; notification/feedback path remains
  available but disabled in the current deployment.
- `bounded_auto`: engine actions are executed by the Home Assistant
  deterministic executor when the controller helper is enabled.

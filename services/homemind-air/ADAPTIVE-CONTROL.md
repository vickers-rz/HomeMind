# HomeMind Air Adaptive Control Architecture

## 1. Objective

HomeMind Air should not evolve into a larger collection of fixed rules such as:

~~~text
outdoor_temperature < 5 C  -> heater Level2
outdoor_temperature < 0 C  -> heater Level3
~~~

Those rules are acceptable only as conservative fallbacks. The target architecture is an adaptive grey-box room model learned from this dwelling, this fresh-air unit, and the observed response after real actions.

The system should progressively identify how this apartment actually exchanges air, heat, moisture, CO2 and particles, then use that model to predict the consequences of candidate fan/heater actions.

## 2. State

At time t, the model state S(t) may include:

~~~text
Indoor:
  CO2
  PM2.5
  temperature
  relative humidity
  absolute humidity

Fresh-air unit:
  power
  fan flow
  preset/mode
  intake temperature
  heater on/off
  heater Level1 / Level2 / Level3

Outdoor/current weather:
  temperature
  relative humidity
  absolute humidity
  AQI
  PM2.5
  PM10
  wind
  precipitation
  dust/weather condition

Forecast:
  nearest 1 h / 3 h / 6 h temperature
  humidity
  weather condition

Seasonal context:
  solar longitude
  current solar term
  low-weight climate mode

Control context:
  manual leases
  manual-off lockout
  minimum runtime
  anti-short-cycle
  session state
~~~

The Xiaomi MJWSD05MMC BLE thermometer/hygrometer beside the fresh-air unit is the primary indoor thermal/moisture observation point. It represents the environment near the unit, not an unqualified whole-apartment average.

## 3. Action space

The future adaptive controller evaluates candidate actions instead of applying one fixed threshold rule.

~~~text
A(t) = {
  fan: on/off,
  flow: 60 / 80 / 100 / 120 / 140 / ... / 300 m3/h,
  heater: off / Level1 / Level2 / Level3
}
~~~

For each candidate, HomeMind should predict the likely state trajectory over horizons such as 10, 20 and 30 minutes.

## 4. What the model learns

The learner observes the response after stable action episodes:

~~~text
Delta CO2 / Delta t
Delta PM2.5 / Delta t
Delta Temperature / Delta t
Delta AbsoluteHumidity / Delta t
~~~

From those responses it estimates physically interpretable parameters.

### 4.1 Airtightness and ventilation

Learn:

- natural infiltration/leakage as equivalent ACH;
- additional ACH produced by the fresh-air unit;
- effective ACH at individual fan-flow settings;
- uncertainty for poorly sampled flow settings.

This distinguishes the nominal m3/h setting from the ventilation effect actually observed in this dwelling.

### 4.2 Thermal envelope

Learn:

- natural indoor-temperature drift toward outdoor temperature while the fan is off;
- envelope heat-transfer rate;
- derived thermal time constant tau as an empirical insulation/thermal-inertia indicator;
- additional thermal exchange caused by ventilation at each flow.

A larger tau means the room changes temperature more slowly. It is a control parameter, not a formal building-energy certification metric.

### 4.3 Moisture

Use absolute humidity rather than relative humidity alone.

Learn:

- natural indoor/outdoor moisture exchange;
- additional moisture exchange caused by ventilation;
- whether the current outdoor-air window will dry or humidify the indoor air;
- the room's moisture buffering behavior.

Indoor absolute humidity uses the colocated BLE temperature + RH pair. Outdoor absolute humidity uses a coherent QWeather temperature + RH pair. Intake temperature is intentionally not combined with remote RH because the fresh-air unit has no intake-humidity sensor.

### 4.4 PM2.5

Learn:

- background PM2.5 drift/deposition;
- outdoor-particle infiltration behavior;
- net PM2.5 removal rate produced by each observed fan flow;
- filtration effectiveness under different operating conditions.

The unit PM2.5 sensor remains an indoor sensor and is never substituted for outdoor PM2.5.

### 4.5 Heater effectiveness

For Level1 / Level2 / Level3, learn the actual thermal response only from real heater episodes where fan flow remains stable.

~~~text
heater_gain(level, flow, conditions)
  -> additional indoor temperature slope
~~~

No heater level becomes automatically controllable until enough real samples exist and the learned effect passes validation.

The current historical recorder contains no real heater-on episodes, so all three levels begin with zero learned confidence by design.

## 5. Episode-based system identification

Raw point-wise regression is not enough because occupancy, weather, internal heat sources and user behavior are confounders.

HomeMind therefore learns from stable action episodes.

~~~text
configuration remains stable:
  fan state unchanged
  flow unchanged
  heater state/level unchanged
for about 5 minutes
      ->
measure state slope
~~~

When the configuration changes, compare neighboring pre/post episodes.

Example:

~~~text
5 min @ fan off
      ->
fan changed to 120
      ->
5 min @ fan 120
~~~

The difference between the two slopes is more useful than a global correlation because it cancels part of the latent occupancy/background-source term.

The learner does not autonomously perturb the equipment merely to collect training data. Normal automation and explicit user actions provide the experiments.

## 6. Machine-learning implementation

The learning plane is a separate container:

~~~text
homemind-air-learner
~~~

Current implementation:

- Python 3.13
- NumPy
- SciPy
- scikit-learn
- HuberRegressor for robust actuator-response fitting
- median/MAD robust estimation for passive physical parameters
- rolling 30-day history
- retraining every 15 minutes
- JSON-only model output

The learner reads:

~~~text
/data/homemind-air.sqlite3
~~~

and writes:

~~~text
/data/adaptive_model.json
~~~

It receives no Home Assistant token and has no device-control path. A learner failure therefore cannot directly start, stop or reconfigure the fresh-air unit.

The realtime HomeMind Air container remains lightweight and deterministic.

## 7. Why JSON instead of pickle/joblib

The realtime control plane should consume only explicit, versioned parameters and validation metadata.

Example:

~~~json
{
  "schema_version": 1,
  "mode": "shadow",
  "parameters": {
    "natural_ach": {
      "value": 0.36,
      "confidence": 1.0,
      "accepted": true
    },
    "fan_ach_at_300": {
      "value": 1.49,
      "confidence": 0.56,
      "accepted": true
    }
  }
}
~~~

This keeps the control boundary inspectable and avoids loading arbitrary serialized Python objects into the realtime controller.

## 8. Validation and confidence gates

A learned value is not automatically trusted.

A parameter must pass an appropriate combination of:

1. minimum sample count;
2. physically plausible sign and range;
3. robust outlier handling;
4. chronological holdout validation;
5. stability across repeated retraining;
6. coverage of the operating region where it will be used.

If validation fails:

~~~text
accepted = false
~~~

and the parameter must not affect realtime control.

The system must be able to know that it does not know something.

## 9. Current shadow-model bootstrap

The first sklearn replay over existing history used approximately:

~~~text
35.6k decision samples
3.5k stable windows
74 configuration transitions
history: 2026-09-07 through 2026-09-19
~~~

First-pass estimates are evidence that the identification pipeline works, not final building constants.

| Parameter | First estimate | Status |
| --- | ---: | --- |
| natural infiltration / ventilation | ~0.36 ACH | accepted |
| envelope heat-transfer rate | ~0.218 h^-1 | accepted |
| derived thermal time constant | ~4.6 h | derived |
| additional fan effect at 300 | ~1.49 ACH | accepted, medium confidence |
| PM2.5 removal rate at 300 | ~3.27 h^-1 | accepted |
| moisture exchange rate | ~0.67 h^-1 | accepted |
| fan thermal-exchange coefficient | unavailable | validation failed |
| heater Level1 gain | no samples | unavailable |
| heater Level2 gain | no samples | unavailable |
| heater Level3 gain | no samples | unavailable |

These values should continue to evolve as more seasons, flow levels and heater episodes are observed.

## 10. Predictive-control target

When model confidence is sufficient, HomeMind can progress from rule-selected flow to a lightweight model-predictive action selector.

For every candidate action:

~~~text
current state
    ->
simulate 10 / 20 / 30 min
    ->
predict:
  CO2
  PM2.5
  indoor temperature
  absolute humidity
~~~

First remove any candidate that violates a deterministic hard safety/IAQ constraint.

Among the remaining candidates, minimize an objective such as:

~~~text
J =
    IAQ penalty
  + thermal discomfort penalty
  + humidity discomfort penalty
  + heater energy penalty
  + fan energy/noise penalty
  + outdoor-pollution exposure penalty
  + switching / short-cycle penalty
  + model-uncertainty penalty
~~~

The uncertainty term is deliberate: a poorly learned action should cost more than a well-characterized action with similar expected performance.

## 11. Deterministic safety shell

Machine learning does not replace the state machine.

The deterministic shell continues to own:

- critical-input validation;
- manual priority and leases;
- manual-off lockout;
- minimum runtime;
- anti-short-cycle;
- emergency CO2 handling;
- hard IAQ boundaries;
- actuator validity;
- model freshness/schema validation.

The learned model may optimize only inside the admissible region.

~~~text
state
  ->
learned predictor
  ->
candidate actions
  ->
deterministic safety filter
  ->
lowest-cost safe action
~~~

## 12. Rollout stages

### Stage A — Shadow

Current stage.

- learner retrains periodically;
- parameters are persisted and audited;
- learned values do not change device actions;
- compare predictions with subsequent observations.

### Stage B — Advisory

- model generates preferred actions and predicted trajectories;
- deterministic controller continues executing its own action;
- log disagreement and prediction error.

### Stage C — Bounded adaptive flow

- allow the model to choose fan flow;
- IAQ/manual/anti-cycle safety shell remains authoritative;
- require confidence thresholds and automatic fallback.

### Stage D — Learned heater advisory

- collect real Level1/2/3 heater episodes;
- learn heater gain by level and flow;
- generate heater recommendations without execution.

### Stage E — Bounded adaptive heater control

Only after all three heater levels have sufficient validated coverage:

- heater joins candidate-action search;
- heater energy is penalized explicitly;
- manual heater changes retain user-priority leases;
- confidence loss immediately falls back to heater-off/advisory behavior.

### Stage F — Lightweight MPC

Jointly select fan flow + heater using the learned room model, forecast and deterministic safety shell.

## 13. Data collection requirements

Retain:

- 30-second decision snapshots;
- exact fan power transitions;
- exact flow changes;
- exact heater on/off transitions;
- exact heater-level changes;
- actor/context for every transition;
- weather/forecast snapshot used at the time;
- model version and prediction for each executed action;
- observed 5/10/20/30-minute response after each action.

No artificial exploration should be enabled by default. Any future calibration mode must be opt-in and bounded by comfort and IAQ limits.

## 14. Climate and season

Xi'an climate profile and solar-season mode remain useful as priors and regularization, not fixed truth.

They may:

- initialize sensible parameter ranges;
- increase uncertainty when a season lacks data;
- separate warm-humid from cold-dry regimes;
- prevent a short autumn dataset from pretending it already knows winter.

As local data accumulates across seasons, validated local response should dominate generic climate priors.

## 15. Design hierarchy

The intended hierarchy is:

~~~text
measured local response
    >
validated learned dwelling model
    >
current weather + forecast
    >
season/climate prior
    >
generic fallback rule
~~~

The objective is not a complicated rule table. It is to make HomeMind progressively learn this apartment's airtightness, insulation, moisture buffering, pollutant dynamics, fresh-air effectiveness and heater response while keeping all safety-critical behavior explainable and bounded.

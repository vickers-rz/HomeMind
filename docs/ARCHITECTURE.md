# HomeMind Architecture

## 1. Architectural boundary

HomeMind is an intelligence layer **above** Home Assistant, not a replacement for it.

```text
Physical Devices
      ↓
Home Assistant
      ↓
Normalized Events / States
      ↓
HomeMind
      ↓
Recommendation
      ↓
Human confirmation
      ↓
Home Assistant Script
```

Home Assistant owns device integrations and deterministic execution. HomeMind owns context, memory, pattern learning and recommendations.

## 2. Layers

### Layer A — Device & State Plane

Home Assistant remains the source of truth for current device state.

Responsibilities:

- device integrations;
- entity state;
- automation;
- scenes;
- scripts;
- Recorder/history;
- weather;
- presence;
- Companion App notifications.

HomeMind should avoid talking directly to individual vendor APIs whenever HA already exposes the device.

### Layer B — Perception

#### Environmental sensing

Suggested initial sensors:

- indoor SEN55: PM + VOC Index + NOx Index + temperature/humidity;
- outdoor/balcony SEN55;
- indoor SCD41: CO₂.

Optional later additions:

- H₂S electrochemical sensor;
- NH₃ electrochemical sensor;
- dedicated outdoor weather station.

VOC Index is a trend signal, not a universal “odor meter”. Human feedback remains important.

#### Visual perception

```text
Camera
  ↓
go2rtc
  ↓
Frigate
  ├─ object detection
  ├─ zones
  ├─ event lifecycle
  └─ snapshots / clips
        ↓
Vision LLM
```

The first visual domain model can normalize observations to:

```text
closed
idle
truck_arriving
unloading
compressing
truck_leaving
unknown
```

The important output is a semantic event, not a prose caption.

### Layer C — Event Normalization

Raw HA state changes should become normalized events.

Example:

```json
{
  "timestamp": "2026-08-08T23:42:10+08:00",
  "type": "device_state_change",
  "entity": "fan.bedroom_fresh_air",
  "from": "medium",
  "to": "sleep",
  "actor": "human"
}
```

Actor/source attribution matters. A manual user action is much stronger behavioral evidence than an automation changing the same entity.

Possible actor values:

```text
human
home_assistant_automation
homemind_recommendation
homemind_autonomous
unknown
```

### Layer D — Context Builder

The Context Builder creates a snapshot around a decision point.

Example:

```json
{
  "time": "23:42",
  "presence": "home",
  "activity": "preparing_to_sleep",
  "indoor": {
    "temperature": 26.1,
    "humidity": 53,
    "co2": 886,
    "pm25": 8,
    "voc_index": 103
  },
  "outdoor": {
    "pm25": 31,
    "voc_index": 187,
    "wind_direction": "SE",
    "wind_speed": 2.8
  },
  "garbage_station": {
    "state": "compressing",
    "confidence": 0.93
  },
  "devices": {
    "fresh_air": "medium",
    "purifier": "auto",
    "ac": "cool_25"
  }
}
```

Context should be generated at meaningful event boundaries instead of continuously feeding every raw sample into an LLM.

### Layer E — Memory

HomeMind should distinguish several memory types.

#### Raw events

Short/medium retention, useful for debugging and episode construction.

#### Episodes

A semantically meaningful interval:

```text
Garbage compression event
19:31–19:47
Outdoor VOC +61%
User closed fresh air at 19:33
Indoor VOC remained stable
Feedback: successful
```

#### Patterns

Aggregated behavioral rules discovered from multiple episodes.

Example:

```json
{
  "pattern": "pollution_protection_after_compression",
  "support": 14,
  "user_action_rate": 0.79,
  "median_delay_minutes": 3,
  "conditions": {
    "wind_toward_home": true
  }
}
```

#### Preferences

Explicitly confirmed user policy, e.g. “never automatically switch the AC off while I am home”.

Preferences should have higher authority than inferred patterns.

### Layer F — Pattern Learner

Do not ask the LLM to rediscover simple statistics.

Use conventional computation for:

- frequency;
- conditional probability;
- time-of-day distributions;
- lag/correlation;
- repeated action sequences;
- episode similarity;
- acceptance rate;
- false-positive rate.

LLM reasoning consumes these derived features.

### Layer G — LLM Reasoning

LLM input should be bounded and structured:

```text
Current Context
+ relevant patterns
+ a few similar Episodes
+ explicit preferences
+ allowed actions
```

Expected structured output:

```json
{
  "action": "pollution_protection",
  "confidence": 0.91,
  "duration_minutes": 20,
  "reason": "...",
  "evidence": ["..."],
  "recheck_after_minutes": 20
}
```

The model may also return:

```json
{"action":"no_action"}
```

Silence is a first-class result.

### Layer H — Policy Guard

Policy Guard is deterministic and sits between AI output and user/device execution.

Examples:

- reject unknown actions;
- only allow whitelisted HA scripts;
- limit maximum ventilation-off duration;
- prevent actions when required sensors are unavailable;
- require human confirmation for specified action classes;
- enforce CO₂/environmental safety policy;
- rate-limit notifications.

### Layer I — Recommendation / Feedback

Home Assistant Companion App is the initial UI.

Example:

```text
空气环境建议

垃圾站正在进行压缩作业。
当前风向朝住宅方向，历史相似事件有较高概率导致异味。

建议：污染防护模式 20 分钟

[执行] [忽略] [30分钟后提醒]
```

Every response becomes a feedback event.

## 3. Action abstraction

LLMs should select semantic actions rather than device-level commands.

Initial action vocabulary:

```text
normal
sleep
pollution_protection
fast_ventilation
away
no_action
```

Each maps to a Home Assistant Script.

This makes execution deterministic, auditable and reversible.

## 4. Proposed HomeMind Core modules

```text
homemind/
├── api/
├── connectors/
│   ├── home_assistant.py
│   └── mqtt.py
├── context/
│   ├── builder.py
│   └── schemas.py
├── events/
│   ├── collector.py
│   └── normalizer.py
├── learning/
│   ├── episodes.py
│   ├── patterns.py
│   └── similarity.py
├── memory/
│   ├── models.py
│   └── repository.py
├── reasoning/
│   ├── llm.py
│   ├── prompts.py
│   └── recommendation.py
├── policy/
│   └── guard.py
└── feedback/
    └── handler.py
```

## 5. Deployment model

For the prototype:

```text
Home Assistant host
    │
    ├── MQTT
    │
    └── HA API
          │
          ▼
NUC / always-on host
    ├── Frigate
    ├── HomeMind
    └── SQLite/PostgreSQL
          │
          ▼
Apple Silicon / GPU host
    └── Ollama LLM/VLM
```

HomeMind must not require the router itself to run AI workloads.

## 6. Privacy

Preferred defaults:

- local camera processing;
- local event/memory database;
- local Ollama option;
- cloud LLM as opt-in provider;
- redact unnecessary camera regions;
- store semantic events rather than unlimited raw imagery where possible;
- expose only required HA entities to AI components.

## 7. Future architecture

Potential later components:

- PostgreSQL/TimescaleDB for larger histories;
- embedding-based Episode retrieval if conventional filters become insufficient;
- multimodal household activity model;
- learned notification policy;
- multiple residents and preference conflicts;
- simulation/dry-run mode;
- recommendation evaluation dashboard;
- Home Assistant custom integration / add-on packaging.

A vector database and multi-agent orchestration should only be introduced when measurements show they solve a real limitation.

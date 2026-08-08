# HomeMind Roadmap

Roadmap 的原则：先验证“智能是否真的有用”，再增加系统复杂度。

相关研究结论见 [RELATED_WORK.md](RELATED_WORK.md)。研究后，HomeMind 的重点已进一步收敛为：

```text
被动观察
→ 多模态 Context
→ Episode
→ Pattern / Preference
→ Recommendation / no_action
→ Manual Override / Feedback
→ Bounded Autonomy
```

而不是重新实现一个自然语言 Home Assistant 控制助手。

## Phase 0 — Foundation

目标：整理 Home Assistant 现有基础设施。

- [ ] 整理空调、新风、净化器、空气传感器实体
- [ ] 统一 entity naming
- [ ] 创建 `air_normal`
- [ ] 创建 `air_sleep`
- [ ] 创建 `air_pollution_protection`
- [ ] 创建 `air_fast_ventilation`
- [ ] 创建“现在很臭 / 空气正常” Helper
- [ ] 确认天气实体包含可靠风向/风速

完成标准：所有动作无需 AI 即可通过 HA Script 可靠执行。

## Phase 1 — Visual Environment Sensor

目标：把摄像头从“视频”变成结构化环境传感器。

优先复用 **Frigate + LLM Vision / HA AI Task**，MVP 不自行开发 Vision Adapter。

- [ ] 稳定摄像头 → go2rtc
- [ ] 部署 Frigate
- [ ] 配置 garbage station zone
- [ ] truck/car/person 基础检测
- [ ] 接入 LLM Vision 或 HA AI Task
- [ ] 输出结构化状态

状态：

```text
closed
idle
truck_arriving
unloading
compressing
truck_leaving
unknown
```

完成标准：真实事件测试中能够可靠地区分“普通经过”和“垃圾站作业”。

## Phase 2 — Environmental Sensor Fusion

目标：验证视觉事件与实际空气变化之间的关系。

- [ ] 卧室 PM/VOC/NOx
- [ ] 卧室 CO₂
- [ ] 阳台 PM/VOC/NOx
- [ ] Weather / wind context
- [ ] 建立事件时间轴
- [ ] 手工臭味反馈
- [ ] 记录人工设备操作来源

完成标准：能够回看一个垃圾站 Episode 的完整多模态时间线。

## Phase 2.5 — Baseline Harness

在完整 HomeMind Core 之前，先回答一个科学问题：

> LLM 到底在哪些决策上真的比简单统计方法更有价值？

建立统一离线评估 Harness，同时运行：

### B0 — Rule baseline

```text
VOC threshold
+ garbage station state
+ wind direction
```

### B1 — Conditional frequency baseline

```text
P(user_action | structured context bucket)
```

### B2 — AdaHome-style semantic-temporal estimator

```text
similarity^γ × temporal_decay
→ weighted preference estimate
```

### B3 — Episode Retrieval + LLM

```text
current context
+ similar episodes
→ recommendation
```

评估指标：

- [ ] recommendation precision
- [ ] acceptance rate
- [ ] false interruption rate
- [ ] manual override rate
- [ ] adaptation delay after preference change
- [ ] latency
- [ ] token / compute cost

完成标准：能够用相同历史 Episode 离线比较不同 Recommendation Engine。

## Phase 3 — Recommendation MVP

目标：第一次产生有依据的 AI 建议。

不开发完整通用 LLM Provider Framework；第一版通过 HA AI Task、Home LLM、Local OpenAI compatible endpoint 等现成能力提供 Reasoner adapter。

- [ ] Context schema
- [ ] Recommendation schema
- [ ] 最小 `Reasoner` protocol
- [ ] HA AI Task / OpenAI-compatible adapter
- [ ] `no_action` support
- [ ] deterministic Policy Guard
- [ ] HA actionable notification
- [ ] accept / ignore feedback
- [ ] recommendation explanation/evidence references

完成标准：AI 不能直接控制设备；用户确认后可靠执行白名单 Script。

## Phase 3.5 — Automation Ownership / Manual Override

借鉴 Adaptive Lighting 的 `take_over_control` 模型，把人工操作本身变成反馈。

建议状态机：

```text
AI_ELIGIBLE
AI_RECOMMENDED
USER_OVERRIDE
COOLDOWN
USER_LOCKED
```

- [ ] 区分 human / HA automation / HomeMind action source
- [ ] 检测 recommendation 后的人工反向操作
- [ ] 把 manual override 记录为高权重负反馈
- [ ] notification cooldown
- [ ] autoreset override
- [ ] domain-level override
- [ ] parameter-level override（类似 `pause_changed`）

例如：

```text
AC temperature: USER_OVERRIDE
fresh-air mode: AI_ELIGIBLE
purifier speed: AI_ELIGIBLE
```

完成标准：用户手工接管以后，HomeMind 不会继续机械地覆盖或重复提醒。

## Phase 4 — HomeMind Core

目标：从 HA YAML/零散自动化中抽离真正的智能层。

- [ ] FastAPI service
- [ ] HA WebSocket subscriber
- [ ] MQTT connector
- [ ] SQLite models
- [ ] normalized event model
- [ ] actor/source attribution
- [ ] Context Builder
- [ ] Recommendation Engine
- [ ] Feedback Handler
- [ ] Ownership State Manager
- [ ] health/diagnostics

完成标准：HomeMind 服务重启/故障不会影响 Home Assistant 基础自动化。

## Phase 5 — Episode Memory

目标：建立长期可解释记忆。

HomeMind Memory 分为两条线。

### Behavior Memory

```text
Context → user action / feedback
```

- [ ] garbage pollution episode schema
- [ ] sleep preparation episode schema
- [ ] manual override episode
- [ ] daily summarization
- [ ] retention policy
- [ ] similar episode retrieval

### Task / Goal Memory

借鉴 IoTGPT 的 Task → Subtask → Context 思路：

```text
Goal
→ semantic subactions
→ current-device implementation
```

例如：

```text
protect_indoor_air
├── reduce_outdoor_air_intake
├── increase_filtration
└── maintain_thermal_comfort
```

- [ ] semantic goal model
- [ ] device-agnostic subaction model
- [ ] HA Script mapping
- [ ] device replacement/remapping

完成标准：既能回答“这种情况下用户通常怎么做”，也能回答“这个 Goal 在当前设备组合里怎样实现”。

## Phase 6 — Pattern Learning

目标：从“记住历史”进化到“发现规律”。

- [ ] conditional frequency
- [ ] action sequence mining
- [ ] event lag statistics
- [ ] time-of-day patterns
- [ ] acceptance statistics
- [ ] weak-pattern expiry
- [ ] minimum support thresholds
- [ ] AdaHome-style semantic-temporal estimator
- [ ] pattern-specific decay timescale

不要固定使用单一 7-day decay。不同 Pattern 可以拥有不同时间尺度：

```text
污染反应 → days/weeks
睡眠偏好 → weeks/months
季节温度 → months/seasonal
临时访客 → hours
```

完成标准：LLM 使用的行为概率来自可复现统计计算。

## Phase 7 — Continuous & Device-Agnostic Preference Model

AdaHome 当前主要评估 binary device state；HomeMind 需要处理真实智能家居里的连续参数。

目标属性：

```text
temperature
fan_speed
brightness
color_temperature
ventilation_duration
noise preference
```

借鉴 IoTGPT，把偏好尽量从设备 ID 提升到环境属性：

```text
sleep.temperature ≈ 25°C
sleep.noise = low
sleep.air_exchange = quiet
```

- [ ] continuous preference estimator
- [ ] confidence interval / uncertainty
- [ ] device-agnostic environmental property
- [ ] transfer preference to replacement devices
- [ ] seasonal/context conditioning

完成标准：更换设备后不需要完全重新学习用户偏好。

## Phase 8 — Activity / Intent Model

目标：开始理解人的生活状态，而不仅是设备状态。

候选状态：

```text
PreparingForSleep
Sleeping
Working
Cooking
LeavingHome
ReturningHome
Relaxing
```

- [ ] activity features
- [ ] hybrid deterministic/probabilistic inference
- [ ] lightweight decision-complexity routing
- [ ] LLM semantic interpretation only when needed
- [ ] user correction
- [ ] confidence tracking

引入类似 AdaHome 的 decision complexity routing：

```text
D0 Deterministic
D1 Learned Pattern
D2 Lightweight LLM
D3 Rich reasoning / Ask User
```

完成标准：HomeMind 可以根据情境而非固定时间判断 Routine，并避免无意义 LLM 调用。

## Phase 9 — Bounded Autonomy

默认仍然保持 recommendation-first。

只允许用户明确授权的 Pattern 升级为自动执行。

要求：

- [ ] high confidence threshold
- [ ] minimum historical support
- [ ] explicit opt-in
- [ ] reversible action
- [ ] automatic rollback/recheck
- [ ] audit log
- [ ] emergency disable switch
- [ ] manual takeover always wins

例如：

```text
“过去 30 天你接受了 19/20 次这个建议。
是否允许以后在相同条件下自动进入污染防护模式？”
```

## Phase 10 — Generalize Beyond Air

在空气场景证明有效以后扩展：

### Sleep

- 温度
- 新风
- 灯光
- 噪声
- 起床/睡眠 Routine

### Energy

- 空调能耗
- 峰谷电价
- 无人在家
- 设备待机

### Lighting

- 活动状态
- 自然光
- 时间
- 用户长期亮度/色温偏好

### Device health

- 异常功耗
- 设备 unavailable
- 传感器漂移
- 滤芯/耗材趋势

## Phase 11 — Packaging

如果核心模型稳定，再考虑：

- [ ] Home Assistant custom integration
- [ ] Home Assistant Add-on
- [ ] Docker image
- [ ] configuration UI
- [ ] LLM API / MCP exposure where useful
- [ ] documentation site
- [ ] anonymized demo dataset
- [ ] automated tests
- [ ] CI/CD

## Explicit non-goals for early versions

早期不做：

- Kubernetes deployment requirement
- Kafka requirement
- mandatory vector DB
- autonomous multi-agent swarm
- unrestricted Home Assistant tool access
- cloud-only architecture
- custom vision stack when LLM Vision / HA AI Task is sufficient
- custom universal LLM-provider framework
- opaque end-to-end model that cannot explain recommendations

## North-star metrics

HomeMind 的核心指标不应该是：

```text
自动化执行次数
```

而应该是：

```text
Recommendation usefulness
User acceptance rate
False interruption rate
Manual override rate
Time-to-adapt
Explanation accuracy
Inference cost
Safety policy violations = 0
```

长期最重要的指标可能是：

> **系统越来越了解用户以后，应该更少打扰用户，而不是更多。**
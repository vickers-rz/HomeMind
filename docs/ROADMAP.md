# HomeMind Roadmap

Roadmap 的原则：先验证“智能是否真的有用”，再增加系统复杂度。

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

- [ ] 稳定摄像头 → go2rtc
- [ ] 部署 Frigate
- [ ] 配置 garbage station zone
- [ ] truck/car/person 基础检测
- [ ] 接入 Vision LLM
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

完成标准：能够回看一个垃圾站 Episode 的完整多模态时间线。

## Phase 3 — Recommendation MVP

目标：第一次产生有依据的 AI 建议。

- [ ] Context schema
- [ ] Recommendation schema
- [ ] LLM provider abstraction
- [ ] Ollama provider
- [ ] `no_action` support
- [ ] deterministic Policy Guard
- [ ] HA actionable notification
- [ ] accept / ignore feedback

完成标准：AI 不能直接控制设备；用户确认后可靠执行白名单 Script。

## Phase 4 — HomeMind Core

目标：从 HA YAML/零散自动化中抽离真正的智能层。

- [ ] FastAPI service
- [ ] HA WebSocket subscriber
- [ ] MQTT connector
- [ ] SQLite models
- [ ] normalized event model
- [ ] Context Builder
- [ ] Recommendation Engine
- [ ] Feedback Handler
- [ ] health/diagnostics

完成标准：HomeMind 服务重启/故障不会影响 Home Assistant 基础自动化。

## Phase 5 — Episode Memory

目标：建立长期可解释记忆。

- [ ] Episode builder
- [ ] garbage pollution episode schema
- [ ] sleep preparation episode schema
- [ ] daily summarization
- [ ] retention policy
- [ ] similar episode retrieval

完成标准：系统能够回答“这次情况和过去哪些情况相似”。

## Phase 6 — Pattern Learning

目标：从“记住历史”进化到“发现规律”。

- [ ] conditional frequency
- [ ] action sequence mining
- [ ] event lag statistics
- [ ] time-of-day patterns
- [ ] acceptance statistics
- [ ] weak-pattern expiry
- [ ] minimum support thresholds

完成标准：LLM 使用的行为概率来自可复现统计计算。

## Phase 7 — Activity / Intent Model

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
- [ ] LLM semantic interpretation
- [ ] user correction
- [ ] confidence tracking

完成标准：HomeMind 可以根据情境而非固定时间判断 Routine。

## Phase 8 — Bounded Autonomy

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

例如：

```text
“过去 30 天你接受了 19/20 次这个建议。
是否允许以后在相同条件下自动进入污染防护模式？”
```

## Phase 9 — Generalize Beyond Air

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

## Phase 10 — Packaging

如果核心模型稳定，再考虑：

- [ ] Home Assistant custom integration
- [ ] Home Assistant Add-on
- [ ] Docker image
- [ ] configuration UI
- [ ] provider plugin system
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
Explanation accuracy
Safety policy violations = 0
```

长期最重要的指标可能是：

> **系统越来越了解用户以后，应该更少打扰用户，而不是更多。**

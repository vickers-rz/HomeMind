# Related Work：HomeMind 与现有智能家居 AI 项目的关系

> Reviewed: 2026-08-08

本文不是相关项目列表，而是回答一个更重要的问题：

> **HomeMind 是否真的值得独立做？如果值得，它应该做什么，而不应该重复做什么？**

结论先行：

**HomeMind 不应该再把“自然语言控制智能家居”当作核心创新。这个问题已经被 Home Assistant、Home LLM、Sasha、SAGE、IoTGPT、AdaHome 等项目和研究充分覆盖。**

HomeMind 更值得聚焦的方向是：

> **Ambient Adaptive Home Intelligence**：系统不依赖用户每次发出命令，而是持续观察真实家庭环境和人工操作，把多模态事件压缩为可解释的生活 Episode，学习长期情境化行为模式，然后只在值得打扰用户时提出建议，并把人工接管和反馈作为第一等公民。

---

# 1. 能力对照矩阵

| 能力 | Home Assistant / AI Task | Home LLM | LLM Vision | Adaptive Lighting | AdaHome | IoTGPT | HomeMind 目标 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 设备接入与可靠执行 | ★★★★★ | 依赖 HA | 依赖 HA | 依赖 HA | 原型 | SmartThings | **复用 HA** |
| 自然语言设备控制 | ★★★★ | ★★★★★ | ★ | — | ★★★★★ | ★★★★★ | 非核心 |
| 本地小模型 | ★★★ | ★★★★★ | ★★★★ | — | ★★★★★ | 非重点 | 可选 |
| 视觉理解 | AI Task 可做 | 部分模型可做 | ★★★★★ | — | 文本实验 | 非核心 | **直接复用** |
| 用户确认 | 可编排 | 可编排 | 通知可编排 | manual takeover | ambiguous commands | final review | **默认机制** |
| 人工接管检测 | HA Context 可推断 | 非核心 | — | ★★★★★ | correction | correction | **核心** |
| 长期偏好学习 | 很弱 | 很弱 | reference memory | — | ★★★★★ | ★★★★★ | **核心** |
| 从人工设备操作学习 | 原始数据存在 | — | — | 只识别接管 | 主要来自确认/纠正 | interaction/history | **核心** |
| 多传感器时序 Context | HA 数据存在 | 请求时上下文 | 视觉为主 | 灯光上下文 | 较有限 | context-aware | **核心** |
| 多模态 Episode Memory | — | — | 视觉 Timeline | — | interaction tuple | task DAG | **核心** |
| 连续参数偏好 | HA 可执行 | 可控制 | — | ★★★★★ | **当前仅二值** | ★★★★★ | **核心** |
| 主动推荐而非命令响应 | Automation 可触发 | 主要响应式 | 事件触发 | 主动适配 | 主要命令触发 | 主要命令触发 | **核心** |
| `no_action` / 克制通知 | 手工实现 | 非核心 | 手工实现 | 接管后停止 | confirmation | review | **核心指标** |
| 确定性 Policy Guard | HA 可实现 | tool/schema | — | 自身规则 | schema validation | virtual validation | **核心** |

这里最值得注意的是：**HomeMind 的单个技术组件几乎都不是新的。差异化来自这些组件如何围绕“被动观察 + 长期学习 + 推荐而非接管”组合。**

---

# 2. Home Assistant：不要重造执行平面

- Core: https://github.com/home-assistant/core
- LLM API: https://developers.home-assistant.io/docs/core/llm/
- AI Task: https://www.home-assistant.io/integrations/ai_task/

Home Assistant 已经提供：

- 实体与设备抽象；
- Automation / Script / Scene；
- Recorder；
- REST / WebSocket API；
- Assist LLM API；
- AI Task structured data；
- camera attachment；
- Companion App actionable notification。

2026 年的 HA LLM API 还允许 integrations 向 LLM API 注册自定义 tools，并可通过 MCP 暴露注册的 LLM APIs。

## 对 HomeMind 的结论

### 直接复用

```text
Device Plane
Execution Plane
Notification UI
AI Task abstraction
Entity exposure/security boundary
```

### 不应该做

HomeMind 不应：

- 自己维护厂商设备协议；
- 自己做通用 service-call router；
- 自己重新实现 HA Conversation Agent；
- 自己做另一套 Scene/Automation engine。

HomeMind 应把输出收敛成语义动作，再调用白名单 HA Script。

---

# 3. Home LLM：已经把“本地 LLM 控制 HA”做得很完整

- Repo: https://github.com/acon96/home-llm

Home LLM 当前已经包含：

- Home Assistant custom integration；
- local llama.cpp；
- Ollama；
- OpenAI-compatible endpoint；
- 专门面向 smart-home function calling 的小模型；
- Conversation Agent；
- AI Task；
- structured output / tool-based extraction；
- vision-capable model attachment；
- 自定义训练数据和训练流程。

其当前 AI Task 实现已经直接基于 HA `AITaskEntity` 和 `llm.Tool`，能够用 schema 或 tool call 强制抽取结构化结果，并具有重试/校验逻辑。

## Home LLM 已经解决的问题

```text
“我怎样让本地小模型理解一句命令并调用 Home Assistant？”
```

这个问题 HomeMind 没有必要再重新解决。

## HomeMind 应直接借鉴

- provider/backend 抽象方式；
- HA 原生 AI Task integration 方式；
- schema constrained generation；
- retry-on-invalid-structured-output；
- 小模型优先的 Prompt 设计。

## 不建议直接 fork 成 HomeMind Core

原因是两者职责不同：

```text
Home LLM:
User utterance → LLM → HA tools

HomeMind:
Environment + history + human behavior
→ Context/Patterns
→ Recommendation
→ Human
→ HA Script
```

Home LLM 更像 **language control plane**，HomeMind 目标是 **behavior/context intelligence plane**。

因此更好的关系是：

> Home LLM 可以成为 HomeMind 的一种 LLM provider / HA-side adapter，而不是 HomeMind 的基础架构。

---

# 4. LLM Vision：视觉层第一版基本不需要自己写

- Repo: https://github.com/valentinfrlch/ha-llmvision
- Docs: https://llmvision.gitbook.io/getting-started

LLM Vision 已经支持：

- image analysis；
- video analysis；
- live camera stream；
- Frigate Event ID；
- 多种云端和本地 provider；
- Ollama/OpenAI-compatible provider；
- Timeline；
- reference memory；
- JSON structured response；
- 从分析结果更新 HA sensor。

其 service schema 甚至已经支持：

```text
response_format: json
structure: JSON Schema
store_in_timeline: true
use_memory: true
```

这和 HomeMind 的垃圾站 VLM Sensor 几乎完全匹配。

## 直接复用建议

MVP 不要开发 `homemind/vision/`。

先直接让：

```text
Frigate event
    ↓
LLM Vision video_analyzer
    ↓
structured JSON
    ↓
sensor.garbage_station_activity
    ↓
HomeMind Event Collector
```

输出统一为：

```json
{
  "state": "compressing",
  "confidence": 0.93,
  "reason": "..."
}
```

## HomeMind 仍然需要做的

LLM Vision 的 Timeline 是 **视觉事件记忆**，不是家庭行为记忆。

HomeMind 需要把：

```text
视觉事件
+ VOC/PM/CO₂
+ 风向
+ Presence
+ 设备状态
+ 用户之后的人工动作
```

合成一个 Episode。

这是两者的边界。

---

# 5. Adaptive Lighting：HomeMind 最值得借鉴的不是灯光算法，而是“尊重人工接管”

- Repo: https://github.com/basnijholt/adaptive-lighting
- Manual control docs: https://github.com/basnijholt/adaptive-lighting/blob/main/docs/advanced/manual-control.md

Adaptive Lighting 的 `take_over_control` 是非常成熟的 Human-in-the-loop 设计。

它会：

1. 自动调整灯光；
2. 检测用户或其他来源是否修改了 brightness/color；
3. 一旦发现人工修改，把实体标记为 `manually controlled`；
4. 停止继续覆盖用户；
5. 等待 off/on、显式 reset 或超时以后再恢复；
6. 还能用 `pause_changed` 只暂停被人工修改的维度。

它还支持：

```text
detect_non_ha_changes
autoreset_control_seconds
manual_control event
```

## 这是 HomeMind 应该直接抽象出来的设计模式

建议 HomeMind 定义：

```text
Automation Ownership State
```

每个可推荐/可自动化的 domain 都可以处于：

```text
AI_ELIGIBLE
AI_RECOMMENDED
USER_OVERRIDE
COOLDOWN
USER_LOCKED
```

例如用户在 HomeMind 推荐 `air_sleep` 后，马上手工把新风改成中档：

```text
HomeMind recommendation
↓
user manual change
↓
USER_OVERRIDE
↓
本次 Episode 标记 recommendation_rejected_by_override
↓
本晚停止继续提示相同建议
```

这比“用户点了忽略按钮才算负反馈”更真实。

### 进一步借鉴 `pause_changed`

空气环境也应该允许维度级接管：

```text
AC temperature: USER_OVERRIDE
fresh-air mode: AI_ELIGIBLE
purifier speed: AI_ELIGIBLE
```

而不是用户碰了一台设备以后整个系统彻底退出。

这是 HomeMind 应列为核心架构能力的部分。

---

# 6. AdaHome：最重要的学术参考之一

- Paper: https://arxiv.org/abs/2607.18034
- ICMI 2026

AdaHome 解决两个核心问题：

1. 不要对所有命令都使用重型 reasoning；
2. 如何在不 fine-tune、不把全部历史塞进 Prompt 的情况下持续适应用户偏好。

## 6.1 Intent-aware routing

AdaHome 把请求分成：

```text
Direct
Indirect
Ambiguous
```

Direct 走简单 Planner；Indirect/Ambiguous 才使用 lightweight reasoning（Chain-of-Draft）。

它的实验非常值得 HomeMind重视：在统一 Llama 3.2 3B 模型下，复杂 reasoning 对已经明确的 direct command 反而容易引入额外错误；AdaHome 在 direct/indirect 上均达到 86.7% success，且整体延迟最低。Ambiguous 场景里更重的 Harmony reasoning 略强，但延迟显著更高。

### 对 HomeMind 的启发

HomeMind 也应该做 **decision complexity routing**，而不是每个传感器事件都调用大模型。

可以定义：

```text
D0 Deterministic
D1 Learned Pattern
D2 Lightweight LLM
D3 Rich reasoning / ask user
```

例如：

```text
CO₂ > hard limit
→ D0 Policy

“过去 20 次相同条件 19 次用户都选 sleep”
→ D1 Pattern

垃圾站作业 + 风向变化 + 数据互相冲突
→ D2 LLM

首次出现、风险高、用户偏好未知
→ D3 Ask user
```

这比“所有事情都 Agent 化”更合理。

## 6.2 Preference adaptation

AdaHome 的偏好算法非常简单，但很有价值。

它先从命令中抽取一个短 intent representation，然后 embedding；查询 top-k 类似历史交互，再使用：

```text
weight = semantic_similarity^γ × exp(-λ × age)
```

对历史行为进行语义相似度 + 时间衰减加权，再通过 kernel regression 估计设备 activation probability。

论文实验里，它在模拟 longitudinal sequences 上达到：

- preference consistency: 87.5%；
- recovery from temporary deviation: 80%；
- adaptation success after preference shift: 100%；
- adaptation delay: 2.6 turns。

相比把历史直接作为 RAG prompt 的 baseline，稳定性明显更好。

## HomeMind 应实现一个 AdaHome-compatible baseline

Pattern Learner 第一版可以直接实现：

```text
SemanticTemporalPreferenceEstimator
```

作为 baseline，而不是一上来做复杂 ML。

但不要直接复制论文参数：

```text
γ = 3
λ = 0.1/day
```

HomeMind 应让不同 Pattern 有不同时间尺度。

例如：

```text
睡眠偏好：weeks/months
垃圾站污染反应：days/weeks
季节温度偏好：months/seasonal
一次临时访客场景：hours
```

## AdaHome 的关键局限，正好是 HomeMind 可以扩展的地方

论文作者明确指出：

- 当前 preference model 只处理 **binary device state**；
- continuous attributes（如 temperature）尚未处理；
- 需要真正长期 user study；
- 实验主要是 **text-based interaction**；
- cold start 仍依赖 LLM reasoning。

此外，从系统设计看，AdaHome 的学习入口仍主要是：

```text
user command → confirm/correct → preference memory
```

而 HomeMind 的原始设想更进一步：

```text
用户根本不说话
↓
正常生活、手动控制设备
↓
系统观察
↓
形成 Episode
↓
发现 Context-conditioned behavior
```

这应该成为 HomeMind 的关键边界。

截至本次检索，没有找到 AdaHome 作者公开的官方代码仓库，因此目前更适合作为算法参考和 baseline，而不是直接依赖的软件组件。

---

# 7. IoTGPT：目前与 HomeMind 架构思想最接近的研究

- Paper: https://arxiv.org/abs/2601.04680

IoTGPT 比 AdaHome 更接近 HomeMind 的“情境 + 个性化 + 连续参数”问题。

它采用：

```text
Decompose
→ Derive
→ Refine
→ Human Review
```

并建立三层 task memory DAG：

```text
Task
  ↓
Subtask
  ↓
Context
```

更重要的是，它没有只记“某台空调设为 20°C”，而是试图抽象：

```text
cool → temperature property
```

使偏好可以跨设备迁移，例如空调不可用时，把“cool”的偏好映射到风扇。

## HomeMind 应借鉴两件事

### A. Semantic action decomposition

HomeMind 的：

```text
air_pollution_protection
air_sleep
fast_ventilation
```

后续可以进一步抽象成：

```text
Goal: protect_indoor_air
    ├── reduce_outdoor_air_intake
    ├── increase_particle_filtration
    └── maintain_thermal_comfort
```

这会让 Action 不再被绑定到某个品牌设备。

### B. Device-agnostic environmental preference

应该学习：

```text
sleep.temperature ≈ 25°C
sleep.noise ≈ low
sleep.air_exchange ≈ low/quiet
```

而不仅是：

```text
climate.xxx = 25
fan.xxx = sleep
```

这是未来支持换设备、多个家庭和不同设备组合的关键。

## IoTGPT 与 HomeMind 的关键区别

IoTGPT 仍然主要从：

```text
user instruction
```

开始工作。

HomeMind 的目标则是：

```text
physical world events
+ sensor history
+ visual events
+ manual device changes
+ explicit feedback (optional)
```

即使用户没有说一句话，也应该逐渐形成行为模型。

另外 HomeMind 更强调：

- recommendation-first；
- silence/no_action；
- event-sourced Episode；
- proactive prediction；
- manual override ownership；
- deterministic policy before action。

所以 IoTGPT 应作为第二个核心算法参考，而不是竞争到需要放弃 HomeMind 的项目。

---

# 8. Sasha / SAGE / Harmony / HomeLLaMA：补充定位

这些研究说明“LLM smart home assistant”已经是一个成熟研究方向。

## Sasha

https://arxiv.org/abs/2305.09802

重点：

```text
underspecified goal
→ creative reasoning
→ action plan
```

如：`make it cozy`、`help me sleep better`。

**借鉴：** goal-oriented action abstraction。

**不是 HomeMind 核心：** 它仍由用户 goal 触发。

## SAGE

https://saic-montreal.github.io/

重点：agent + tool orchestration + persistent condition monitoring + preference + visual grounding。

它甚至支持由 LLM 生成条件检查代码，然后由 server 持续 polling，条件满足时执行。

**借鉴：** tool grounding、persistent command 的设计问题。

**警告：** AdaHome 的统一小模型实验表明，复杂多步 agent reasoning 在 SLM 上容易产生额外延迟和错误传播。这强化了 HomeMind“不要默认多 Agent”的决定。

## Harmony

重点：local LLM + modular reasoning + rule-based validation。

**借鉴：** LLM 后的 deterministic validator。

## HomeLLaMA（学术项目，不是 GitHub Home LLM）

https://arxiv.org/abs/2507.08878

重点：tailored SLM、privacy-preserving local inference、用户 profile、本地持续更新，以及必要时通过 PrivShield 选择性使用 cloud LLM。

**借鉴：** local-first + optional cloud escalation。

---

# 9. 深度研究后，对 HomeMind 架构的修正

原方案有几处应该调整。

## 修正 1：MVP 不开发自己的 Vision Adapter

原：

```text
HomeMind → Vision model API
```

改：

```text
Frigate
→ LLM Vision / HA AI Task
→ structured HA entity/event
→ HomeMind
```

只有现成插件不能满足需求以后才写 `homemind-vision`。

## 修正 2：MVP 不开发通用 LLM provider framework

Home LLM、Local OpenAI LLM、HA AI Task 已经解决大量 provider 兼容问题。

HomeMind Core 第一版只定义一个很小的接口：

```python
class Reasoner:
    async def recommend(context, memories) -> Recommendation:
        ...
```

HA AI Task / OpenAI-compatible endpoint 都可以成为 adapter。

## 修正 3：Pattern Learner 不等于 RAG

第一版至少建立三个 baseline：

```text
B0 Frequency / conditional statistics
B1 AdaHome-style semantic + temporal kernel estimator
B2 Episode retrieval + LLM reasoning
```

然后实测谁更好。

不要预设“向量数据库 + LLM”一定最好。

## 修正 4：新增 Automation Ownership / Manual Override 状态机

这是 Adaptive Lighting 给 HomeMind 最重要的启发。

必须能判断：

```text
AI 建议以后用户手工改了什么？
```

并把它视为高权重反馈。

## 修正 5：Memory 应分两条线

### Behavior Memory

```text
Context → user action
```

回答：

> 在这种情况下用户通常怎么做？

### Task/Goal Memory

借鉴 IoTGPT：

```text
Goal → semantic subactions → device mapping
```

回答：

> “污染防护”在这个家庭当前设备组合里应该怎么实现？

二者不要混成一个向量库。

---

# 10. HomeMind 真正应该主打的差异化

## 10.1 Ambient learning，而不是 command learning

现有大量研究的数据入口：

```text
用户说了一句话
```

HomeMind 的核心入口：

```text
用户正常生活
```

这意味着 manual HA actions、sensor changes、camera events 本身就是监督信号。

## 10.2 Multimodal Episode，而不是聊天记录

```text
垃圾站压缩
+ 东南风
+ 阳台 VOC 上升
+ 用户 3 分钟后关闭新风
+ 20 分钟后重新打开
```

应该成为一个可计算 Episode，而不是一段自然语言聊天历史。

## 10.3 Proactive recommendation，而不是 reactive assistant

系统不等用户说：

> “现在是不是应该关闭新风？”

而是在有足够证据时主动说：

> “建议关闭 20 分钟。”

同时必须优化 `no_action`，避免从“智能家居”变成“智能骚扰”。

## 10.4 Learn from overrides

用户不需要专门点击“不喜欢”。

他在 AI 操作后把设备改回去，本身就是强烈负反馈。

## 10.5 Continuous, contextual preferences

比 AdaHome 当前 binary state 更进一步：

```text
25°C
30% fan
20 min ventilation-off duration
brightness 18%
```

而且偏好依赖：

```text
activity × season × time × environment × presence
```

## 10.6 Recommendation-to-autonomy ladder

```text
Observe
→ Recommend
→ Confirmed Routine
→ Explicitly authorized bounded autonomy
```

自治是逐渐 earned 的，而不是 Agent 默认拥有的。

## 10.7 HA-native open-source implementation

许多学术系统运行在自建 simulator 或 SmartThings prototype 上。

HomeMind 可以提供一个很实际的价值：

> **把这些研究思想做成真正可以安装在现有 Home Assistant 家庭里的开源系统。**

---

# 11. 是否值得继续做？

## 作为“LLM 智能家居助手”

**差异化不足。**

Home LLM、IoTGPT、AdaHome、SAGE 等已经覆盖大量问题。

## 作为“Home Assistant 的长期情境行为学习与推荐层”

**值得。**

尤其下面这个组合，目前仍然具有明确的工程空缺：

```text
Home Assistant event stream
+ multimodal physical context
+ passive manual-action learning
+ temporal Episode memory
+ continual preference estimator
+ recommendation / no_action policy
+ manual takeover semantics
+ bounded autonomy
```

HomeMind 的价值应该建立在这个组合上，而不是模型名称上。

---

# 12. 下一步技术验证：不要马上写完整 Core

首先做一个 **Research Prototype / Baseline Harness**。

选择空气场景，采集真实 Episode，然后同时跑：

### Baseline A — Rule

```text
VOC threshold + garbage station state
```

### Baseline B — Frequency

```text
P(user_action | structured context bucket)
```

### Baseline C — AdaHome-style

```text
semantic/context similarity
× temporal decay
→ weighted preference estimate
```

### Baseline D — LLM + Episode retrieval

```text
current context
+ top similar Episodes
→ recommendation
```

评估：

```text
Precision of recommendation
Acceptance rate
Manual override rate
False interruption rate
Time-to-adapt after habit change
Inference latency
Token / compute cost
```

如果一个简单的 B/C 已经表现很好，就没有理由让 D 接管所有决策。

这将成为 HomeMind 一个非常重要的设计原则：

> **LLM is not the system. The LLM is one reasoning component inside the system.**

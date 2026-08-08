# 智能家居 AI 技术综述：AdaHome、Home LLM、IoTGPT、LLM Vision、MiCU、DevPiolt 与 HomeMind

> Reviewed: 2026-08-08
>
> 本文记录 HomeMind 当前阶段的深度研究结论，重点不是“有哪些相关项目”，而是拆解它们真正解决的问题、核心算法、技术实现路径、工程边界、可直接复用部分和对 HomeMind 的启发。

---

# 0. 结论先行

需要首先区分两类项目。

## 可直接部署/复用的开源项目

- **Home LLM**：Home Assistant 本地 LLM、Conversation Agent、Tool Calling、AI Task。
- **LLM Vision**：Home Assistant 图像/视频/Frigate Event 多模态视觉理解。
- **Adaptive Lighting**：成熟的自适应自动化和人工接管检测设计。
- **Home Assistant / ESPHome / Frigate / go2rtc / MQTT**：底层设备、事件与执行基础设施。

## 研究型方案/论文原型

- **AdaHome**：轻量推理路由 + 持续偏好适应。
- **IoTGPT**：Task/Subtask/Context 分层任务记忆 + 跨设备环境偏好。
- **MiCU**：智能家居领域小模型训练、命令理解和结构化控制。
- **DevPiolt**：根据历史操作与环境主动推荐设备操作，并通过置信度控制曝光。

HomeMind 不应该再把“自然语言控制 Home Assistant”当作核心创新。真正值得做的是：

> **Ambient, multimodal, continuously adapting recommendation and bounded-autonomy layer for Home Assistant.**

即：

```text
被动观察真实家庭环境
+
人工自然操作
+
多模态 Context
+
长期 Episode / Pattern Memory
+
持续偏好估计
+
主动但克制的 Recommendation
+
Manual Override
+
Bounded Autonomy
```

---

# 1. 全局能力对照

| 能力 | Home LLM | AdaHome | IoTGPT | LLM Vision | MiCU | DevPiolt | HomeMind |
|---|---:|---:|---:|---:|---:|---:|---:|
| HA 原生集成 | ★★★★★ | ☆ | ☆ | ★★★★★ | ☆ | ☆ | ★★★★★ |
| 自然语言控制 | ★★★★★ | ★★★★ | ★★★★★ | ★ | ★★★★★ | ★ | 非核心 |
| 本地小模型 | ★★★★★ | ★★★★★ | 可替换 | ★★★★★ | ★★★★★ | 非重点 | 可选 |
| 多模态视觉 | 部分 | ☆ | ☆ | ★★★★★ | ☆ | ☆ | 直接复用 |
| 长期偏好 | ★ | ★★★★★ | ★★★★★ | ★★ | ☆ | ★★★★★ | 核心 |
| 连续参数 | ★★★ | ★ | ★★★★★ | N/A | ★★★★ | ★★★★★ | 核心 |
| 任务复用 | ★★ | ★★ | ★★★★★ | ☆ | ☆ | ★ | 核心 |
| 主动推荐 | ★ | ★★ | ★★ | ★ | ☆ | ★★★★★ | 核心 |
| 用户反馈学习 | ★ | ★★★★★ | ★★★★★ | ★★ | ☆ | ★★★★★ | 核心 |
| Human-in-loop | ★★ | ★★★★★ | ★★★★★ | N/A | N/A | ★★★ | 默认 |
| `no_action` / 克制 | 一般 | ★★★ | ★★★ | N/A | N/A | ★★★★★ | 核心指标 |
| 可直接部署 | 是 | 否 | 否 | 是 | 训练代码 | 否 | — |

---

# 2. AdaHome：轻量决策路由与持续偏好学习

AdaHome 的核心思想不是“让模型思考更多”，而是：

> **只在真正需要推理的时候调用推理。**

它主要解决两个问题：

1. 不要对所有智能家居命令使用昂贵、冗长的 reasoning pipeline；
2. 不 fine-tune 模型的情况下，如何根据用户持续反馈动态学习个人偏好。

## 2.1 Intent-aware routing

AdaHome 将请求划分为：

```text
Direct
Indirect
Ambiguous
```

例如：

```text
Direct:
“打开卧室灯”

Indirect:
“屋里太热了”

Ambiguous:
“我想放松一下”
```

整体流程：

```text
User Request
     │
     ▼
Intent Classifier
     │
 ┌───┼─────────────┐
 │   │             │
 ▼   ▼             ▼
Direct Indirect  Ambiguous
 │     │             │
 │     ▼             ▼
 │  Lightweight   Reasoning
 │  Reasoning      + Preference
 │     │             │
 └─────┴──────┬──────┘
              ▼
           Planner
              │
              ▼
      Structured Action
              │
              ▼
       Schema Validator
              │
              ▼
     User Confirmation
      when necessary
```

对 HomeMind 最重要的结论：

> **Reasoning 是一种昂贵资源，不应该成为默认执行路径。**

HomeMind 因此应设计 Decision Complexity Router：

```text
D0 — Deterministic
D1 — Learned Pattern
D2 — Lightweight LLM
D3 — Rich Reasoning / Ask User
```

例如：

```text
CO₂ 超过安全硬阈值
→ D0

过去 20 次相同 Context，19 次用户选择 sleep mode
→ D1

垃圾站作业 + 风向 + VOC + CO₂ 相互冲突
→ D2

第一次出现、高风险、用户偏好未知
→ D3
```

## 2.2 Chain-of-Draft

AdaHome 使用的是简化的 Chain-of-Draft，而不是长 Chain-of-Thought。

例如：

```text
User:
“房间太热了”

Draft:
room too hot → cooling required

Action:
{
  "device": "air_conditioner",
  "action": "cool"
}
```

对于智能家居这种目标高度结构化的任务，很多时候只需要：

```text
Intent → Short Draft → Structured Action
```

而不是：

```text
Thought → Tool → Observation → Thought → Tool → ...
```

这可以降低延迟、Token 消耗以及额外 hallucination。

## 2.3 Preference Adaptation

AdaHome 最值得 HomeMind 直接实现成 baseline 的是它的语义-时间偏好估计器。

每一条历史交互保存：

```text
intent embedding
+
device state / user choice
+
timestamp
```

新请求到来后：

1. 计算当前 intent embedding；
2. 检索 top-k 相似历史；
3. 同时考虑语义相似度和时间衰减；
4. 对过去行为进行加权估计。

权重形式：

```text
w_i = similarity_i^γ × exp(-λ × age_i)
```

论文实验参数包括：

```text
γ = 3
λ = 0.1 / day
k = 10
```

对于二值设备状态：

```text
x_i ∈ {0,1}
```

可以估计：

```text
P(device_on | current_context)
=
Σ(w_i × x_i) / Σ(w_i)
```

这本质上是 kernel regression / locally weighted estimation。

### 为什么优于“把所有历史塞给 LLM”

因为以下工作完全可以由确定性程序完成：

```text
相似度计算
时间衰减
条件概率
历史支持度
```

LLM 只需要解释结果，而不应该自行“猜统计数字”。

## 2.4 AdaHome 的局限

最重要的限制是当前 preference model 主要针对：

```text
ON / OFF
```

即二值设备状态。

HomeMind 更需要处理：

```text
24.5 ℃
37% fan speed
18% brightness
3200 K color temperature
fresh air off for 17 min
```

因此 HomeMind 需要把 AdaHome-style estimator 扩展到：

```text
continuous target
mixed discrete/continuous target
context-dependent duration
```

最简单的连续 baseline 可以直接变成：

```text
ŷ = Σ(w_i × y_i) / Σ(w_i)
```

之后再评估：

- Bayesian regression；
- contextual bandit；
- online learning；
- quantile regression；
- drift detection。

## 2.5 对 HomeMind 的落地

建议实现：

```text
SemanticTemporalPreferenceEstimator
```

接口：

```text
observe(context, action, feedback)
predict(context, target)
explain_prediction()
```

但不要机械复制论文的固定时间衰减参数。

不同偏好应该拥有不同时间尺度：

```text
睡眠温度偏好      → weeks / months
垃圾站污染响应    → days / weeks
季节性空调偏好    → months / seasonal
临时访客模式      → hours / days
```

---

# 3. Home LLM：成熟的 Home Assistant 本地 LLM 执行适配层

Repo:

```text
https://github.com/acon96/home-llm
```

Home LLM 目前是最成熟的“本地模型 ↔ Home Assistant”开源方案之一。

它更适合被理解为：

> **Home Assistant language/tool control plane**

而不是长期行为学习系统。

## 3.1 核心组成

```text
Home LLM Integration
+
Home Models
```

Integration 负责：

- Home Assistant Conversation Agent；
- AI Task；
- Home Assistant LLM API / Tools；
- Provider adapter；
- structured output；
- tool-call loop。

模型端可以使用：

```text
llama.cpp
Ollama
OpenAI-compatible API
LM Studio
LocalAI
vLLM
Anthropic-style API
OpenAI Responses API
```

## 3.2 数据流

典型流程：

```text
User Voice/Text
      │
      ▼
HA Assist Pipeline
      │
      ▼
Home LLM Conversation Agent
      │
      ├── System Prompt
      ├── exposed HA context
      └── HA LLM Tools
              │
              ▼
             LLM
              │
          tool_call
              │
              ▼
     Home Assistant LLM API
              │
              ▼
       HA Intent / Service
              │
              ▼
            Device
```

重点：

> 模型并不直接调用小米、Matter、Zigbee 或其他厂商 API。

设备执行仍然经过 Home Assistant。

## 3.3 Agentic Tool Loop

Home LLM 已经不仅是一次性：

```text
text → tool call
```

而可以形成：

```text
LLM
 ↓
GetState
 ↓
Tool Result
 ↓
LLM
 ↓
SetClimate
 ↓
Tool Result
 ↓
LLM
 ↓
Final Response
```

这意味着 HomeMind 没必要重新实现一个通用 HA tool-calling agent。

## 3.4 AI Task 与结构化输出

Home LLM 当前实现已经基于 HA `AITaskEntity`。

支持：

```text
GENERATE_DATA
SUPPORT_ATTACHMENTS
```

同时可以通过：

```text
JSON Schema structured output
```

或：

```text
tool-based structured response
```

强制模型输出符合 Schema 的数据。

内部还包含：

```text
validation
retry
malformed JSON recovery
```

这样的工程能力。

对 HomeMind 来说，LLM 输出不应该只是：

```text
“我觉得应该关新风。”
```

而应该是：

```json
{
  "recommendation": "pollution_protection",
  "confidence": 0.91,
  "duration_minutes": 20,
  "reason": "..."
}
```

Home LLM / HA AI Task 已经提供了成熟的结构化输出基础。

## 3.5 Home Models

Home LLM 还维护针对智能家居 function calling 的专用小模型和数据。

设计思想是：

```text
通用模型知识
+
智能家居命令/Tool Calling 专用训练
```

从而让 270M / 3B 等小模型也能够可靠完成窄领域控制任务。

典型训练样本：

```text
User:
Turn off the bedroom light

Assistant:
<tool_call>
light.turn_off(...)
```

## 3.6 对 HomeMind 的结论

### 直接复用

- Provider adapter；
- HA tool calling；
- AI Task；
- structured output；
- local LLM runtime；
- Conversation interface。

### 不应该塞进 Home LLM 的能力

- 长期行为记忆；
- 多模态 Episode；
- Pattern Mining；
- Preference Estimation；
- Recommendation Exposure Policy。

因此关系应该是：

```text
HomeMind Brain
      │
      ▼
Home LLM / HA AI Task
      │
      ▼
Home Assistant
```

Home LLM 是 HomeMind 的“嘴和手”，不是长期“大脑”。

---

# 4. IoTGPT：Task / Subtask / Context 分层任务记忆

IoTGPT 的架构价值非常高。

如果说 AdaHome 研究：

> 什么时候需要推理？

IoTGPT 更接近：

> **复杂智能家居任务如何逐渐变成可复用的技能？**

## 4.1 总体 Pipeline

```text
User Instruction
       │
       ▼
   DECOMPOSE
       │
       ▼
   Subtasks
       │
       ▼
    DERIVE
       │
       ▼
Command Templates
       │
       ▼
    REFINE
       │
       ▼
Personalized Commands
       │
       ▼
 Human Review
       │
       ▼
   Execution
```

## 4.2 Decompose

例如：

```text
“把卧室弄得适合睡觉。”
```

不会直接变成 API 调用。

而会先变成：

```json
[
  {
    "subtask": "cool room",
    "capability": "temperature"
  },
  {
    "subtask": "dim lights",
    "capability": "brightness"
  },
  {
    "subtask": "reduce ventilation noise",
    "capability": "airflow_noise"
  }
]
```

模型会被提供当前真实设备能力，减少 hallucinated device。

## 4.3 Derive：从语义 Subtask 到 Command Template

例如：

```text
cool_room
```

可以被编译成：

```text
turn_on(ac)
set_mode(cool)
set_temperature([temperature_value])
```

最重要的是：

```text
[temperature_value]
```

此时故意不填。

这样把：

```text
How to execute
```

和：

```text
What the user prefers
```

彻底分开。

## 4.4 RAG 用在哪里

IoTGPT 使用 RAG 主要不是为了“检索用户记忆”，而是为了检索庞大的 IoT API 文档。

流程：

```text
Subtask
   ↓
Retrieve relevant API docs
   ↓
LLM derives command template
```

这个思想对 HomeMind 仍然有启发，但 Home Assistant 已经完成大量 API abstraction，因此 HomeMind 不需要对 HA Service 文档做重型 RAG。

## 4.5 Refine

Refine 阶段才注入用户偏好和具体 Context。

例如：

```text
Template:
set_temperature([temperature_value])

Context:
sleeping

Preference:
cool

↓

set_temperature(20)
```

这意味着：

> “如何执行任务”和“这个人在这种情况下喜欢什么参数”应该分层。

## 4.6 Task Memory DAG

IoTGPT 最值得 HomeMind 借鉴的是三级 Task Memory：

```text
TASK
 │
 ├── SUBTASK
 │      │
 │      └── command template
 │
 └── CONTEXT
        │
        └── personalized parameters
```

例如：

```text
TASK
prepare bedroom for sleep
       │
       ├──────────────┬───────────────┐
       ▼              ▼               ▼
   cool_room       dim_light      reduce_noise
       │
       ▼
 set_temperature(?)
       │
 ┌─────┴──────┐
 ▼            ▼
sleeping    working
 20°C         24°C
```

### 为什么这比普通 RAG 更强

普通 RAG：

```text
新请求
↓
检索相似历史
↓
重新让 LLM 推理
```

Task Memory：

```text
Task match
→ 可以复用分解

Subtask match
→ 可以复用 command template

Context match
→ 可以复用参数
```

因此使用次数越多：

> 理论上 LLM 调用应该逐渐减少。

这非常符合 HomeMind 的长期目标。

## 4.7 Device-Agnostic Preference

IoTGPT 不应该只记：

```text
AC.temperature = 20
```

而应该抽象成：

```text
sleeping:
temperature_preference = cool
```

这样设备变化后：

```text
AC available
→ set_temperature(20)

AC unavailable
Fan available
→ set_fan_speed(high)
```

用户真正偏好的不是某台设备的参数，而是：

> **环境目标。**

这启发 HomeMind 将语义动作设计成：

```text
protect_indoor_air
maintain_thermal_comfort
reduce_noise
increase_freshness
```

然后再映射到当前设备。

## 4.8 Virtual Smart Home / Dry-run

IoTGPT 还设计了先在虚拟环境中验证 command 的机制。

```text
Generated Command
       │
       ▼
Virtual Smart Home
       │
       ▼
Runtime / API Error?
       │
       ├─ yes → feed error back → repair
       │
       └─ no  → Human Review / Execute
```

HomeMind 不需要完整模拟所有设备，但应该实现：

```text
Schema Validator
+
Policy Guard
+
State Simulator
```

例如：

```text
Recommendation:
关闭新风 3 小时

Policy:
max_ventilation_off = 30 min

Result:
REJECT
```

## 4.9 对 HomeMind 的落地

建议内部同时维护两种 Memory：

### Behavior Memory

回答：

> 这种情况下，我通常怎么做？

结构：

```text
Context
→ User Action
→ Outcome
```

### Task / Goal Memory

回答：

> 这个环境目标应该怎样用当前设备实现？

结构：

```text
Goal
→ Semantic Subtasks
→ Device Mapping
```

例如：

```text
protect_indoor_air
│
├─ reduce_outdoor_air_intake
│    └─ fresh_air low/off
├─ increase_filtration
│    └─ purifier high
└─ maintain_thermal_comfort
     └─ AC hold temperature
```

---

# 5. LLM Vision：成熟的视觉感知层

Repo:

```text
https://github.com/valentinfrlch/ha-llmvision
```

HomeMind 第一版基本没有必要自己实现视觉模型调用框架。

LLM Vision 已经支持：

```text
Image
Video
Live Camera
Frigate Event
```

同时支持多种 provider，包括本地模型和 OpenAI-compatible API。

## 5.1 技术路径

```text
Camera
  ↓
go2rtc
  ↓
Frigate
  ↓
Object / Zone Event
  ↓
LLM Vision
  ↓
VLM
  ↓
Structured JSON
  ↓
HA Sensor / Timeline
  ↓
HomeMind Event Collector
```

## 5.2 Structured output

LLM Vision 的 HA service 已经支持：

```text
response_format: json
structure: JSON Schema
store_in_timeline: true
use_memory: true
```

因此垃圾站分析可以直接要求：

```json
{
  "activity": "compressing",
  "truck_present": true,
  "door_open": true,
  "confidence": 0.91
}
```

而不是返回自由文本：

```text
“I can see what looks like a truck near...”
```

## 5.3 HomeMind 与 LLM Vision 的边界

LLM Vision 负责：

```text
pixels → semantic visual event
```

HomeMind 负责：

```text
visual event
+
air sensors
+
weather
+
presence
+
device state
+
manual action
↓
multimodal episode
```

所以 HomeMind 应看到：

```text
garbage_station_activity = compressing
confidence = 0.91
```

而不是原始视频。

这叫：

> **Perception / Cognition Separation**

---

# 6. MiCU：领域小模型与智能家居命令理解

MiCU 的价值在于证明：

> **领域数据 + 结构化训练目标，有时比简单增加模型尺寸更重要。**

它以约 4B 级别模型为基础，针对智能家居 command understanding 进行领域训练。

## 6.1 数据集

构造类似：

```text
DevCmd
~50k samples
28 categories
```

包含两类数据。

### Easy

```text
device specification
+
template
↓
synthetic command
+
ground-truth action
```

### Hard

```text
real-world user logs
↓
retrieval / annotation
+
LLM
+
Self-Refine
↓
intent / action labels
```

## 6.2 训练路线

```text
Base Model
   │
   ▼
Curriculum Learning
Easy → Hard
   │
   ▼
Domain Knowledge
   │
   ▼
Reasoning Cold-start SFT
   │
   ▼
RL / DAPO
   │
   ▼
MiCU
```

它的 teacher reasoning 也不是完全自由 CoT，而是包含 smart-home domain rules，例如：

```text
1. 判断命令是否合法
2. 判断设备类别
3. 根据房间、设备、属性筛选
4. 只有规则不足时才进行语义推理
```

这和 AdaHome 的“不要过度 reasoning”是同一方向。

## 6.3 MiCU-fast：Schema / Device Context 压缩

智能家居很容易出现：

```text
100+ entities
×
大量属性
×
大量可调用动作
```

导致 Tool Schema / Prompt 极其庞大。

MiCU-fast 的方向是把冗长设备描述压缩成更紧凑的表示，从而减少 token 和 latency。

对 HomeMind 的启发：

不要无脑把：

```text
全部 HA Entity
全部 Attribute
全部 Service
```

暴露给模型。

而是根据当前 Decision Context 动态构建最小工具/状态集合。

## 6.4 为什么 HomeMind 现在不应该训练自己的模型

HomeMind 当前没有足够高质量的：

```text
Context
User Action
Recommendation
Acceptance / Rejection
Manual Override
Outcome
```

数据。

所以现阶段训练 `HomeMind-3B` 价值很低。

正确顺序应该是：

```text
先收真实数据
↓
建立 baseline
↓
识别系统瓶颈
↓
确认 prompting / retrieval 已经不够
↓
再考虑 SFT / DPO / RL
```

---

# 7. DevPiolt：主动推荐与 Exposure Control

DevPiolt 是与 HomeMind 初衷非常接近的研究方向。

它不是：

```text
用户说一句话
→ 控制设备
```

而是：

```text
历史设备操作
+
环境状态
+
时间 / 房间 / 当前设备状态
↓
预测下一步值得推荐的操作
```

这与 HomeMind 的“先观察用户正常生活，再逐渐学会推荐”高度一致。

## 7.1 数据来源

典型数据包括：

```text
Historical Operation
Environment Log
Action Log
Time
Room
Device
Field / Value
```

不仅包含语音命令，也包含直接操作设备。

这说明：

> **Manual action 本身就是高价值监督信号。**

## 7.2 模型路线

```text
Historical Device Operations
           │
           ▼
   Continual Pretraining
           │
           ▼
       Fine-tuning
           │
           ▼
           DPO
   User Preference Align
           │
           ▼
 Recommendation Model
           │
           ▼
 Confidence Estimation
           │
       confidence gate
       /             \
     low             high
      │                │
   no_action       expose recommendation
```

## 7.3 从 Manual Override 构造 Preference Pair

例如：

```text
System Recommendation:
AC → 24℃
```

用户随后实际操作：

```text
AC → 26℃
```

可以构造：

```text
preferred = 26℃
dispreferred = 24℃
```

如果用户在推荐后很快执行反向操作，也可以被解释为强负反馈。

这与 HomeMind 的 Automation Ownership 模型完全一致。

## 7.4 Exposure Control

DevPiolt 最值得 HomeMind 直接借鉴的思想之一：

> **产生了 Recommendation，不等于必须打扰用户。**

应该有：

```text
Recommendation
      │
      ▼
Confidence / Utility Estimator
      │
      ▼
Exposure Gate
     /   \
   low   high
    │      │
no_action Notify
```

HomeMind 的优化目标不应该是：

```text
max(recommendation_count)
```

而应该接近：

```text
max(useful_recommendations / interruptions)
```

这意味着 `no_action` 必须是一等输出，而不是失败情况。

---

# 8. Adaptive Lighting：人工接管是架构能力，不是异常

Repo:

```text
https://github.com/basnijholt/adaptive-lighting
```

Adaptive Lighting 的灯光算法不是 HomeMind 最该关注的部分。

最值得借鉴的是：

> **系统如何发现“用户现在不想听自动化的”。**

## 8.1 Manual Control Detection

Adaptive Lighting 可以：

1. 自动调整灯光；
2. 检测 brightness / color 被用户或外部系统改变；
3. 标记 `manually controlled`；
4. 暂停自动 adaptation；
5. 等待 reset、off/on 或超时后恢复。

还有：

```text
take_over_control
pause_changed
detect_non_ha_changes
autoreset_control_seconds
```

## 8.2 HomeMind Automation Ownership State

建议 HomeMind 对每个可控制维度维护：

```text
AI_ELIGIBLE
AI_RECOMMENDED
USER_OVERRIDE
COOLDOWN
USER_LOCKED
```

例如：

```text
HomeMind:
推荐 fresh_air = sleep

User:
2 分钟后手工改成 medium

System:
USER_OVERRIDE
↓
本次 recommendation 视为被自然行为拒绝
↓
今晚对同一建议进入 cooldown
```

更进一步：

```text
AC temperature → USER_OVERRIDE
fresh air mode → AI_ELIGIBLE
purifier speed → AI_ELIGIBLE
```

即维度级 ownership，而不是“一碰设备就整个 AI 停止”。

---

# 9. 最新综合研究结论：HomeMind 不应该成为“全屋 Agent”

把上述方案放在一起以后，可以得到几个非常明确的结论。

## 9.1 不要默认 LLM

最佳路径应该是：

```text
Current Event
    │
    ▼
Decision Router
    │
 ┌──┼───────────────┐
 ▼  ▼               ▼
Rule Pattern       LLM
 │    │              │
 └────┴──────┬───────┘
             ▼
      Recommendation
```

只有 D2/D3 级问题才应该调用较复杂 LLM。

## 9.2 LLM 不负责统计

下面这些应该由程序算：

```text
过去 14 次类似情况出现 11 次异味
历史 median lag = 11 min
用户接受率 = 82%
最近 30 天 override rate = 23%
```

LLM 负责：

```text
解释这些数字为什么支持当前建议
```

## 9.3 Memory 必须分层

不能只有一个“Vector DB Memory”。

至少应分成：

```text
Raw Events
Episodes
Behavior Patterns
Explicit Preferences
Task / Goal Memory
Recommendation Feedback
```

## 9.4 Goal 应与 Device 解耦

HomeMind 应学习：

```text
sleeping → prefer cool / quiet / moderate fresh air
```

而不只是：

```text
Xiaomi fan = level 2
```

## 9.5 Manual Override 是训练数据

用户不需要总是点击：

```text
[拒绝]
```

他直接去操作设备，本身就是更真实的反馈。

## 9.6 系统越聪明，应该越安静

目标不是：

```text
AI 每天提醒 20 次
```

而是：

```text
只在高 utility / 高 confidence 时提醒
```

因此：

```text
NO_ACTION
```

必须是一等结果。

---

# 10. HomeMind Best-of-Breed Architecture

综合各项目以后，推荐架构：

```text
                     Home Assistant
                   Device / State Plane
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
       Sensors          Weather          Frigate
                                             │
                                             ▼
                                        LLM Vision
                                             │
                                             ▼
                                     Structured Event
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                     Context Builder
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
        Behavior Memory           Task / Goal Memory
       AdaHome-inspired          IoTGPT-inspired
               │                       │
               └───────────┬───────────┘
                           ▼
                    Decision Router
                     AdaHome-style
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      Deterministic     Statistics         LLM
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                  Recommendation Engine
                           │
                           ▼
                 Confidence / Utility Gate
                   DevPiolt-inspired
                           │
                     ┌─────┴─────┐
                     ▼           ▼
                 NO_ACTION    Notify User
                                 │
                         [Accept / Ignore]
                                 │
                                 ▼
                         Policy Guard
                                 │
                                 ▼
                      Whitelisted HA Script
                                 │
                                 ▼
                         Manual Override
                                 │
                                 └──────→ Learning
```

---

# 11. HomeMind 各模块对应借鉴来源

| HomeMind Module | 主要借鉴 |
|---|---|
| Device / State Plane | Home Assistant |
| Local LLM / Tool Adapter | Home LLM |
| Visual Perception | Frigate + LLM Vision |
| Decision Complexity Router | AdaHome |
| Semantic Temporal Preference | AdaHome |
| Task / Goal Memory | IoTGPT |
| Device-agnostic semantic action | IoTGPT |
| Dry-run / Policy Validation | IoTGPT + HA |
| Manual Override / Ownership | Adaptive Lighting |
| Recommendation Confidence Gate | DevPiolt |
| Domain-specific small-model strategy | MiCU / Home LLM |
| `no_action` optimization | DevPiolt + HomeMind |

---

# 12. 真正值得 HomeMind 自己开发的部分

经过这一轮研究，HomeMind 应避免重新开发：

```text
camera VLM transport
Home Assistant tool calling
local LLM runtime
vendor device drivers
basic Conversation Agent
```

应该集中开发：

```text
Event Normalization
      ↓
Actor / Source Attribution
      ↓
Context Builder
      ↓
Episode Builder
      ↓
Behavior Memory
      ↓
Semantic Temporal Preference Estimator
      ↓
Task / Goal Memory
      ↓
Decision Complexity Router
      ↓
Recommendation Engine
      ↓
Confidence / Utility Gate
      ↓
Automation Ownership
      ↓
Policy Guard
      ↓
Feedback Learning
```

这才是 HomeMind 真正具有项目价值的地方。

---

# 13. Baseline-first：不要为了 AI 而 AI

HomeMind 后续必须建立 baseline harness。

至少同时比较：

```text
A. Fixed Rules
B. Simple Frequency / Statistics
C. AdaHome-style SemanticTemporalPreferenceEstimator
D. Episode Retrieval + LLM
E. Future learned model
```

比较指标：

```text
recommendation precision
acceptance rate
override rate
false interruption rate
latency
token / compute cost
explainability
safety violations
```

核心原则：

> **如果简单统计已经能解决 90% 的场景，就不应该为了“AI 味”强行让 LLM 接管。**

---

# 14. 推荐的实际技术实现路径

## Stage A — 感知与事件

直接复用：

```text
Home Assistant
ESPHome
Frigate
LLM Vision
MQTT
```

输出规范化事件：

```json
{
  "type": "garbage_station_activity",
  "state": "compressing",
  "confidence": 0.91,
  "timestamp": "..."
}
```

## Stage B — Context / Episode

HomeMind 自己实现：

```text
HA WebSocket subscriber
Event Normalizer
Context Builder
Episode Builder
```

## Stage C — Preference Baseline

实现：

```text
SemanticTemporalPreferenceEstimator
```

先不训练模型。

## Stage D — Recommendation

```text
Decision Router
→ Pattern / LLM
→ Recommendation
→ Confidence Gate
→ Policy Guard
```

## Stage E — Ownership / Feedback

记录：

```text
accepted
ignored
modified
manual override
result after N minutes
```

## Stage F — Task / Goal Memory

再加入：

```text
Goal
Subtask
Device Mapping
Context Parameter
```

## Stage G — Learned Model

只有积累足够真实家庭数据后，再评估：

```text
SFT
DPO
Continual Learning
Domain Small Model
```

---

# 15. HomeMind 的最终定位

经过对 AdaHome、IoTGPT、Home LLM、LLM Vision、MiCU、DevPiolt 和 Adaptive Lighting 的对照，HomeMind 最合适的定位不是：

> LLM Smart Home Controller

而是：

> **Ambient Adaptive Home Intelligence**
>
> 一个运行于 Home Assistant 上层的多模态、长期适应、推荐优先、人工接管优先、有限自治的家庭智能层。

它回答的核心问题不是：

```text
“用户刚刚说了什么？”
```

而是：

```text
“现在家里发生了什么？”
“这和过去哪些情况类似？”
“用户通常怎样处理？”
“他的偏好最近有没有变化？”
“我真的有必要打扰他吗？”
“如果建议被接受，怎样安全执行？”
“如果他随后手动修改，这意味着我学错了什么？”
```

这才是 HomeMind 和传统 Home Assistant Automation、Conversation Agent、单纯 LLM Tool Calling 的真正边界。

---

# 16. 参考入口

## Home LLM

```text
https://github.com/acon96/home-llm
```

## LLM Vision

```text
https://github.com/valentinfrlch/ha-llmvision
```

## Adaptive Lighting

```text
https://github.com/basnijholt/adaptive-lighting
```

## Home Assistant LLM API

```text
https://developers.home-assistant.io/docs/core/llm/
```

## AdaHome

```text
https://arxiv.org/abs/2607.18034
```

## IoTGPT

```text
https://arxiv.org/abs/2601.04680
```

## MiCU / Xiaomi IoT LLM

```text
https://github.com/xiaomi-research/iot_spec_llm
```

## DevPiolt

```text
https://arxiv.org/abs/2511.14227
```

> 注意：研究型论文方案的公开代码、实验实现状态可能随时间变化。HomeMind 在引入任何论文组件前，应再次核查作者最新仓库、许可证、复现实验和维护状态。

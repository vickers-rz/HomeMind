# HomeMind

> A human-in-the-loop, LLM-powered intelligence layer for Home Assistant.
>
> 让智能家居从“机械规则自动化”进化为“能够理解情境、学习习惯、提出建议，但把最终决定权留给人”的家庭智能系统。

## 为什么做 HomeMind

传统智能家居的核心通常还是规则引擎：

```text
IF 条件 A AND 条件 B
THEN 执行动作 C
```

它能自动化，但并不真正理解人的生活。

HomeMind 的出发点不同：**先让人正常生活和手动控制设备，系统在后台观察环境、设备状态和人的选择，逐渐总结规律；当遇到相似情境时，再给出带理由和置信度的建议，而不是擅自替用户做决定。**

一个典型例子是住宅空气管理。住宅附近可能存在垃圾回收/转运作业，异味并不遵循固定时间表。仅靠“每天 19:00 关闭新风”这样的规则没有意义。HomeMind 希望综合：

- 室内外 PM2.5、VOC、NOx、CO₂、温湿度；
- 天气、风向、风速、时间；
- 摄像头对垃圾车进入、卸料、压缩、关门等事件的视觉理解；
- 空调、新风、净化器当前状态；
- 用户过去在相似情况下的手动操作；
- 用户对建议的接受、拒绝和修改；

最终得到类似这样的建议：

> 垃圾站正在进行压缩作业。虽然阳台 VOC 尚未明显升高，但过去 14 次相似事件中有 11 次在 8–15 分钟后出现异味，当前风向也朝向住宅。建议提前进入“污染防护模式”20分钟。当前卧室 CO₂ 为 720 ppm，短时关闭新风尚可接受。
>
> **[执行] [忽略] [稍后提醒]**

这不是“LLM 控制家电”，而是一个 **Context-aware Recommendation System for the Home**。

## 核心原则

1. **Human in the loop**：默认只建议，不直接执行高影响操作。
2. **Home Assistant 仍是设备与状态总线**：不重造 IoT 平台。
3. **LLM 负责语义理解和推理，不负责替代确定性逻辑。**
4. **统计学习负责习惯规律，LLM 负责解释复杂情境。**
5. **设备控制通过白名单 Script / Scene 抽象，不让模型任意拼接 Service Call。**
6. **所有建议应尽量可解释**：为什么建议、参考了哪些上下文、置信度多高。
7. **用户反馈本身就是训练数据**：接受、拒绝、修改和“现在很臭/空气正常”等显式反馈都应进入记忆。
8. **本地优先、云端可选**：隐私敏感数据应尽可能留在家庭网络中。
9. **安全护栏高于 AI 决策**：CO₂、安全、设备约束等硬规则永远不能被模型覆盖。

## 总体架构

```text
Sensors / Cameras / Weather / Presence
                │
                ▼
        Home Assistant
     Device & State Bus
                │
        ┌───────┴────────┐
        ▼                ▼
   Frigate / VLM     Event Stream
  Visual Perception       │
        └───────┬─────────┘
                ▼
         Context Builder
                │
       ┌────────┴────────┐
       ▼                 ▼
 Pattern Learner     Long-term Memory
       │                 │
       └────────┬────────┘
                ▼
             LLM
      Reasoning / Explanation
                │
                ▼
     Recommendation Engine
                │
                ▼
          Policy Guard
                │
                ▼
       Home Assistant App
      [Accept] [Ignore] [Edit]
                │
                ▼
     Whitelisted HA Scripts
```

## 推荐组件

| 层 | 组件 | 职责 |
|---|---|---|
| IoT / 状态总线 | Home Assistant | 设备接入、状态、Recorder、Automation、Script、Scene |
| MCU / 空气传感器 | ESPHome + ESP32 | PM/VOC/NOx/CO₂/温湿度采集 |
| 视频接入 | go2rtc | RTSP/WebRTC 视频流中转 |
| 事件视觉 | Frigate | 目标检测、Zone、事件触发、录像 |
| 视觉语义 | Frigate GenAI / HA AI Task | 垃圾车、卸料、压缩、关门等场景理解 |
| 本地模型 | Ollama | 本地 VLM/LLM，例如 Qwen3-VL 等 |
| HomeMind Core | Python + FastAPI | Context、事件聚合、推荐、反馈、API |
| 长期记忆 | SQLite → PostgreSQL | 行为 Episode、Pattern、Recommendation、Feedback |
| 消息总线 | MQTT | Frigate / HA / HomeMind 事件通信 |
| 用户交互 | HA Companion App | Actionable Notification 与确认执行 |

## 推荐的第一版技术栈

```text
Home Assistant
ESPHome
MQTT
Frigate
Go2RTC
Ollama
Python 3.12+
FastAPI
SQLAlchemy
SQLite
APScheduler
Home Assistant WebSocket / REST API
```

第一版不需要 Kubernetes，不需要向量数据库，也不需要复杂的多 Agent 框架。

## 文档

- [项目愿景与设计原则](docs/VISION.md)
- [总体架构设计](docs/ARCHITECTURE.md)
- [MVP 操作手册](docs/MVP_RUNBOOK.md)
- [数据、记忆与习惯学习](docs/DATA_AND_LEARNING.md)
- [Related Work：深度研究与差异化定位](docs/RELATED_WORK.md)
- [智能家居 AI 技术综述：AdaHome / Home LLM / IoTGPT / LLM Vision / MiCU / DevPiolt](docs/TECHNICAL_SURVEY.md)
- [Roadmap](docs/ROADMAP.md)
- [资源附录：开源项目、插件与研究](docs/RESOURCES.md)

## MVP 目标

MVP 先只解决一个具体问题：**卧室空气环境管理**。

```text
垃圾站视觉事件
      +
室内外空气质量
      +
天气 / 风向 / 时间
      +
当前设备状态
      +
用户历史行为
      ↓
  生成一个建议
      ↓
用户确认后执行 HA Script
      ↓
记录反馈与结果
```

MVP 的成功标准不是“AI 能自动开关设备”，而是：

- 能正确观察到关键环境事件；
- 能形成稳定、结构化的 Context；
- 建议具有可解释性；
- 用户可以一键接受或拒绝；
- 系统能够从反馈中逐步降低无意义提醒；
- 所有行为可审计、可撤销。

## 项目状态

**Early design / prototype stage.**

当前重点是先打通感知 → Context → 推荐 → 人工确认 → 反馈闭环，再逐步加入长期习惯学习。

# 资源附录：可参考的开源项目、Home Assistant 插件与研究

> Last reviewed: 2026-08-08

本页不是简单的“相关链接合集”，而是按 HomeMind 的架构层次整理：**哪些可以直接复用、哪些值得读源码、哪些只建议借鉴设计思想。**

HomeMind 的基本原则仍然不变：Home Assistant 负责可靠的设备与状态平面，HomeMind 负责 Context、长期记忆、行为模式、推荐和反馈闭环。

---

# 1. 第一优先级：建议直接复用

## Home Assistant Core

- Repo: https://github.com/home-assistant/core
- Docs: https://www.home-assistant.io/
- Developer docs: https://developers.home-assistant.io/

**用途**

作为 HomeMind 的 Device & State Plane：

- entity state；
- device/service/action；
- Script / Scene / Automation；
- Recorder；
- Weather；
- Presence；
- Companion App；
- REST/WebSocket API。

**HomeMind 应借鉴/复用**

HomeMind 不应重新实现设备驱动。设备厂商协议只要已经被 HA 正常抽象，就应该通过 HA 接入。

尤其值得阅读：

- LLM API: https://developers.home-assistant.io/docs/core/llm/
- REST API: https://developers.home-assistant.io/docs/api/rest/
- WebSocket API: https://developers.home-assistant.io/docs/api/websocket/
- Exposing scripts to LLMs: https://www.home-assistant.io/voice_control/exposing_scripts_to_llms/

**建议**：★★★★★ 直接依赖。

---

## ESPHome

- Repo: https://github.com/esphome/esphome
- Docs: https://esphome.io/

**用途**

HomeMind 的低成本环境感知层，例如：

- SEN55；
- SCD41；
- 温湿度；
- PM；
- VOC / NOx Index；
- mmWave / PIR；
- 自定义 GPIO / I²C / UART 传感器。

**HomeMind 应借鉴/复用**

空气感知硬件尽量直接通过 ESPHome 暴露成 HA Entity，而不是 HomeMind 自己和 ESP32 建立一套设备协议。

**建议**：★★★★★ 直接复用。

---

## Eclipse Mosquitto / MQTT

- Repo: https://github.com/eclipse-mosquitto/mosquitto
- HA MQTT: https://www.home-assistant.io/integrations/mqtt/

**用途**

事件通信和松耦合：

```text
Frigate → MQTT → Home Assistant / HomeMind
```

也适合未来第三方 perception service 发布结构化事件。

**建议**：★★★★☆。有明确事件总线需求再用，不要为了“架构完整”把所有 HA 状态重复发 MQTT。

---

# 2. 摄像头与视觉理解

## go2rtc

- Repo: https://github.com/AlexxIT/go2rtc
- Website: https://go2rtc.org/

**用途**

摄像头流的统一接入与协议转换：

- RTSP；
- WebRTC；
- ONVIF；
- HLS / MSE；
- FFmpeg；
- 双向音频；
- 多源流组合。

**HomeMind 应借鉴/复用**

不要让视觉 AI 自己处理不同厂商摄像头协议。统一成稳定的视频/快照接口。

**安全注意**

go2rtc API/流端口不应直接暴露到公网；其 API 能力较强，应限制访问范围。

**建议**：★★★★★ 对已有非标准摄像头尤其适合。

---

## Frigate

- Repo: https://github.com/blakeblackshear/frigate
- Docs: https://docs.frigate.video/

**用途**

本地 NVR + 事件视觉层：

- object detection；
- zones；
- tracking；
- Review events；
- snapshots / recordings；
- MQTT；
- Home Assistant integration；
- GenAI / semantic description。

**HomeMind 最值得借鉴的点**

不要让 VLM 24/7 理解每一帧。

推荐链路：

```text
传统目标检测 / motion
        ↓
产生候选事件
        ↓
只把事件关键帧交给 VLM
        ↓
生成结构化语义事件
```

例如：

```text
truck detected
→ garbage_station zone
→ VLM
→ activity = compressing
```

这比持续 VLM 推理更可靠、便宜、可解释。

**建议**：★★★★★ HomeMind 视觉层首选。

---

## LLM Vision for Home Assistant

- Repo: https://github.com/valentinfrlch/ha-llmvision
- Website: https://llmvision.org/

**定位**

现成的 Home Assistant 多模态视觉 Integration。

支持分析：

- camera image；
- video；
- live camera feed；
- Frigate events；
- timeline；
- 将提取出的视觉信息更新为 HA sensor。

支持多种 provider，包括 OpenAI、Anthropic、Gemini、OpenRouter、Ollama、LocalAI、Open WebUI 等。

**HomeMind 最值得参考的部分**

1. Provider abstraction；
2. Frigate → VLM 的事件链；
3. timeline / event memory；
4. 视觉结果转 HA Sensor；
5. Prompt 与媒体附件的接口设计。

**是否直接依赖？**

MVP 可以直接使用，快速验证“垃圾站视觉状态”场景。

长期 HomeMind 可能仍应保持自己的标准化视觉事件 Schema，以避免核心 Context Engine 绑定某一个插件。

**建议**：★★★★★ MVP 强烈建议试用；源码也值得重点研究。

---

# 3. Home Assistant + LLM / Agent 相关项目

## Home Assistant 官方 OpenAI Integration

- Docs: https://www.home-assistant.io/integrations/openai_conversation/

当前官方能力包括 Conversation 和 AI Task 等 AI 能力，并可以通过 HA Assist API 使用经过暴露控制的实体/工具。

**HomeMind 最值得参考**

- AI Task 的结构化生成范式；
- HA 对 LLM entity/tool exposure 的权限模型；
- LLM provider 与 HA 生命周期的集成方式。

HomeMind 不应复制官方 Conversation Agent；更合理的是让它成为 Context/Recommendation 层。

**建议**：★★★★★ 先研究官方实现，再决定哪些能力需要自己写。

---

## Home Assistant 官方 Ollama Integration

- Docs: https://www.home-assistant.io/integrations/ollama/
- Ollama repo: https://github.com/ollama/ollama

**用途**

本地 LLM/VLM Provider。

HomeMind 可以把 Ollama 作为一种 provider，而不是硬编码唯一后端。

建议未来统一接口：

```text
LLMProvider
├── OllamaProvider
├── OpenAIProvider
├── OpenRouterProvider
└── ...
```

**建议**：★★★★★ 本地优先路线的重要组件。

---

## Home LLM

- Repo: https://github.com/acon96/home-llm

**定位**

专门针对 Home Assistant 的本地 LLM Integration + 智能家居控制模型。

项目包含：

- local LLM integration；
- Ollama / llama.cpp / OpenAI-compatible backend；
- AI Task；
- 面向智能家居控制微调的小模型；
- 训练数据与训练脚本。

**HomeMind 最值得参考**

1. 小模型如何理解 HA 设备与控制语义；
2. Tool/function-call schema；
3. 本地模型 provider；
4. 智能家居专用训练数据如何组织；
5. 低资源硬件上的模型选择。

**HomeMind 与它的区别**

Home LLM 更偏：

```text
用户语言 → 设备控制
```

HomeMind 更偏：

```text
长期观察 → Context → 用户习惯 → Recommendation → Feedback
```

因此它是互补项目，不是重复项目。

**建议**：★★★★★ 必读源码之一。

---

## Extended OpenAI Conversation

- Repo: https://github.com/jekalmin/extended_openai_conversation

**定位**

扩展 Home Assistant Conversation Agent，增加：

- service call；
- automation creation；
- external API；
- web data；
- entity state history 等能力。

**HomeMind 最值得参考**

- function calling/tool definition；
- 将 HA 历史状态提供给 LLM 的接口设计；
- Agent 与 HA service 边界。

**需要警惕**

HomeMind 不应该照搬“给模型很宽的 service-call 权限”这一思路。HomeMind 应坚持白名单 semantic action + Policy Guard。

**建议**：★★★★☆ 重点参考接口，不建议照搬权限模型。

---

# 4. 自动化与 Python 扩展框架

## Pyscript

- Repo: https://github.com/custom-components/pyscript

**定位**

允许在 Home Assistant 中用 Python 编写 trigger/action/state logic。

**HomeMind 可借鉴**

适合在 MVP 阶段快速编写：

- feedback event；
- Context 拼装；
- recommendation result → notification；
- Script 调度胶水代码。

**是否作为 HomeMind Core？**

不建议。

HomeMind 长期需要独立数据库、后台任务、测试和 provider abstraction，独立 FastAPI/Python service 更干净。

**建议**：★★★★☆ 原型胶水很好用，核心服务仍保持独立。

---

## AppDaemon

- Repo: https://github.com/AppDaemon/appdaemon
- Community add-on: https://github.com/hassio-addons/app-appdaemon

**定位**

成熟的 Python Home Assistant automation runtime。

**HomeMind 可参考**

- HA event subscription；
- 长驻 Python app 生命周期；
- scheduler；
- state callback；
- app isolation/configuration。

**是否直接采用？**

如果只是复杂 HA Automation，AppDaemon 很合适。

但 HomeMind 还需要 memory / learning / API / experiments，所以更建议参考其 HA connector 和 runtime 思路，而不是把整个项目做成 AppDaemon App。

**建议**：★★★★☆ 值得参考。

---

## Node-RED + Home Assistant WebSocket

- Repo: https://github.com/zachowj/node-red-contrib-home-assistant-websocket
- Docs: https://zachowj.github.io/node-red-contrib-home-assistant-websocket/

**用途**

用可视化 flow 快速验证：

```text
HA Event
→ filtering
→ HTTP call HomeMind
→ parse recommendation
→ HA Notification
→ user action
```

**优势**

非常适合 prototype 和观察事件流。

**局限**

当 Episode、Pattern、长期状态和测试逻辑增加以后，大量 Node-RED flow 会逐渐难以维护。

**建议**：★★★☆☆ 可以做 MVP 编排，不建议成为长期 intelligence core。

---

# 5. 很值得借鉴的“人优先”自动化项目

## Adaptive Lighting

- Repo: https://github.com/basnijholt/adaptive-lighting

这个项目虽然不是 AI，但它对 HomeMind 有一个非常重要的参考价值：**如何处理自动化和人工操作之间的冲突。**

Adaptive Lighting 能检测灯光被手动修改，并把灯标记为 `manually controlled`，停止继续覆盖人工选择。

这与 HomeMind 的核心原则高度一致：

```text
人工行为 > 推断的自动化意图
```

**HomeMind 应重点借鉴**

- manual-control detection；
- automation takeover semantics；
- 用户手动干预以后暂停自动控制；
- clear/reset manual control；
- 自动化永远不能和人“抢控制权”。

这套思想未来可以抽象成：

```text
control_lease / manual_override
```

例如用户手动调了新风以后：

```text
HomeMind 30 min 内不再建议覆盖该设备
```

**建议**：★★★★★ 设计思想非常值得借鉴。

---

# 6. 时序数据、可视化与调试

## Home Assistant InfluxDB Integration

- Docs: https://www.home-assistant.io/integrations/influxdb/
- InfluxDB: https://github.com/influxdata/influxdb

可以将 HA state changes 写入独立时序数据库。

**HomeMind 适用场景**

- 对齐垃圾站事件与 VOC/PM/CO₂ 曲线；
- 研究事件延迟；
- 环境数据长周期分析；
- debugging。

**是否 MVP 必须？**

不是。SQLite + HA history 足以起步。

数据规模增长以后再引入。

**建议**：★★★☆☆ 第二阶段。

---

## Grafana Home Assistant Add-on

- Repo: https://github.com/hassio-addons/addon-grafana
- Grafana: https://github.com/grafana/grafana

**用途**

非常适合开发阶段验证：

```text
垃圾站开始压缩
        ↓
Outdoor VOC
        ↓
Indoor VOC
        ↓
用户关闭新风
        ↓
CO₂变化
```

HomeMind 的很多“学习结果”在投入模型前应该先用曲线肉眼验证。

**建议**：★★★★☆ 调试和研究价值高。

---

# 7. Habit Learning / Pattern Mining 可参考库

## River

- Repo: https://github.com/online-ml/river
- Docs: https://riverml.xyz/

River 是 Python online machine learning 库，支持：

- incremental learning；
- online statistics；
- anomaly detection；
- drift detection；
- clustering；
- recommender；
- time-series；
- bandits。

**与 HomeMind 的契合点非常高。**

HomeMind 的用户行为和家庭环境都是 streaming data，并且人的习惯会变化。

例如：

```text
过去半年：23:30 sleep mode
最近一个月：01:00 sleep mode
```

这里不是简单“平均”，而是发生了 concept drift。

River 的 drift detector 和 incremental model 很值得实验。

**建议**：★★★★★ HomeMind Pattern Learner 第一批应评估的 ML 库。

---

## STUMPY

- Repo: https://github.com/TDAmeritrade/stumpy

Matrix Profile 时间序列分析库，擅长：

- motif discovery；
- repeated subsequence detection；
- anomaly/discord detection；
- segmentation；
- multidimensional time series；
- streaming analysis。

**HomeMind 潜在用途**

自动寻找类似：

```text
主灯关闭
→ 床头灯打开
→ 手机充电
→ 活动下降
→ 新风 sleep
```

这种重复的时序“形状”。

但它更适合连续数值时间序列；离散 HA event sequence 仍应使用专门的事件/序列方法。

**建议**：★★★★☆ 适合环境传感器 Pattern 与连续时序研究。

---

## ruptures

- Repo: https://github.com/deepcharles/ruptures

离线 change-point detection 库。

**潜在用途**

把长时间的 VOC/CO₂/PM 数据自动切成不同 regime，例如：

```text
normal
→ pollution rising
→ pollution peak
→ recovery
```

也可用于 Episode Builder 辅助寻找事件边界。

**建议**：★★★☆☆ 很适合离线 Episode segmentation 实验。

---

# 8. 研究方向：与 HomeMind 非常接近的论文

## AdaHome: An Adaptive Smart Home Assistant using Local Small Language Models

- arXiv: https://arxiv.org/abs/2607.18034

2026 年的研究，方向与 HomeMind 很接近：

- local small language models；
- intent-aware planning；
- 简单命令与复杂推理分流；
- 从用户 feedback 中进行 preference adaptation；
- 不依赖不断扩大 Prompt 或重新训练模型来维持偏好。

**HomeMind 最值得深入比较的部分**

### 1. Intent-aware routing

并不是任何问题都调用昂贵推理：

```text
简单确定性请求 → fast path
复杂/模糊请求 → reasoning path
```

这与 HomeMind 的：

```text
Deterministic where possible,
probabilistic where useful
```

高度一致。

### 2. Preference adaptation

HomeMind 应重点研究其 preference adaptation 思路，并和自己的：

```text
Feedback → Episode → Pattern → Preference
```

机制比较。

**建议**：★★★★★ 当前最值得跟踪的研究之一。

---

## SmartHomeSecure

- arXiv: https://arxiv.org/abs/2607.06748

研究 Home Assistant YAML 的自动检测与 LLM 修复，采用：

```text
确定性 program analysis
+
constraint-guided LLM generation
```

虽然它解决的不是 habit learning，但其架构思想与 HomeMind 的 Policy Guard 十分一致：

> 能用程序验证的约束，就不要交给模型凭感觉判断。

**HomeMind 可以借鉴**

- constrained generation；
- deterministic validation；
- LLM 输出执行前验证；
- minimal repair / minimal action philosophy。

**建议**：★★★★☆ Policy Guard 设计参考。

---

# 9. 实验性/未来方向

## RuView

- Repo: https://github.com/ruvnet/RuView

使用 Wi-Fi CSI 做非视觉 presence / activity sensing，目标包括：

- occupancy；
- movement；
- activity recognition；
- spatial sensing。

这类技术未来可能给 HomeMind 提供一个有意思的选择：

```text
不用摄像头
→ 仍然理解“房间里有没有人/是否活动”
```

目前建议视为研究和实验性方向，不作为 MVP 核心依赖。

**建议**：★★☆☆☆ 跟踪即可。

---

# 10. 推荐的实际复用组合

HomeMind MVP 不需要同时引入所有项目。

推荐第一套组合：

```text
Home Assistant
    │
    ├── ESPHome
    │     └── Air sensors
    │
    ├── go2rtc
    │     └── Camera stream
    │
    ├── Frigate
    │     └── Event detection
    │
    ├── LLM Vision / HA AI Task
    │     └── Visual semantics
    │
    └── Actionable Notification
            │
            ▼
       HomeMind Core
       Python/FastAPI
            │
     ┌──────┴────────┐
     ▼               ▼
   SQLite          Ollama
     │
     ▼
 Episode / Pattern
```

Pattern Learner 第一阶段：

```text
Python statistics
+ SQL aggregation
```

第二阶段再评估：

```text
River
STUMPY
ruptures
```

而以下项目主要作为设计参考：

```text
Home LLM
Extended OpenAI Conversation
Adaptive Lighting
AdaHome
SmartHomeSecure
```

---

# 11. 当前优先阅读顺序

如果只打算认真读 8 个项目/资料，建议顺序：

1. **Home Assistant LLM API / AI Task / Script exposure**
2. **Frigate**
3. **LLM Vision**
4. **Home LLM**
5. **Adaptive Lighting**
6. **River**
7. **AdaHome**
8. **Extended OpenAI Conversation**

原因分别对应 HomeMind 的八个核心问题：

```text
权限边界
事件视觉
多模态输入
本地智能家居 LLM
人工控制优先
在线习惯学习
偏好适应研究
Tool calling
```

---

# 12. HomeMind 不应照搬的东西

即使上述项目很好，也不应该机械组合成：

```text
HA + Frigate + Node-RED + AppDaemon + Pyscript
+ InfluxDB + Grafana + LangChain + Vector DB
+ Multi-Agent + Kubernetes
```

这会迅速变成一个难以维护的“家庭云平台”。

HomeMind 的优先级应该始终是：

```text
最少组件
→ 跑通闭环
→ 收集真实数据
→ 找到真实瓶颈
→ 再增加一个组件
```

每引入一个依赖，都应该能够回答：

> 它具体解决了当前哪个已经出现的问题？

如果答案只是“以后也许会用”，就暂时不要引入。

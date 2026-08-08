# HomeMind MVP 操作手册

本文档定义第一阶段可实际部署的 MVP。目标不是一次完成“全屋 AI”，而是跑通一个闭环：

```text
感知 → Context → 建议 → 人工确认 → 执行 → 反馈
```

首个场景：卧室空气环境与附近垃圾站作业联动。

---

## 0. MVP 完成标准

完成后应该能够做到：

1. Home Assistant 能读取空调、新风、净化器和环境数据；
2. 摄像头能够观察指定垃圾站区域；
3. 系统能得到结构化的垃圾站状态；
4. 能将天气、空气质量、视觉状态和设备状态组合起来；
5. AI 只能从预定义空气模式中推荐一个；
6. 手机收到可执行/忽略的建议；
7. 用户确认后才执行 HA Script；
8. 接受/拒绝和人工异味反馈被记录。

---

# Phase 1 — 整理 Home Assistant 实体

先建立实体清单。

至少需要：

```text
climate.bedroom_ac
fan.bedroom_fresh_air
fan.bedroom_air_purifier
sensor.bedroom_temperature
sensor.bedroom_humidity
sensor.bedroom_co2
sensor.bedroom_pm25
sensor.bedroom_voc
sensor.balcony_pm25
sensor.balcony_voc
weather.home
camera.garbage_station
```

实体名称不要求完全相同，但建议先统一命名。

不要让 HomeMind 直接依赖厂商设备 ID。

---

# Phase 2 — 创建语义化 HA Scripts

在 Home Assistant 中创建以下脚本：

```text
script.air_normal
script.air_sleep
script.air_pollution_protection
script.air_fast_ventilation
```

## air_pollution_protection 示例逻辑

```text
新风 → 关闭/最小允许档
净化器 → 高档
空调 → 保持舒适温度
启动 20 分钟重新评估计时
```

注意：具体设备 Service 和 entity_id 根据实际集成填写。

AI 后续只能选择 Script 名，不直接决定设备 Service Call。

---

# Phase 3 — 增加人工空气反馈

Home Assistant：

```text
Settings
→ Devices & services
→ Helpers
→ Create helper
→ Button
```

创建：

```text
input_button.smell_bad
input_button.air_good
```

UI 名称建议：

```text
现在很臭
空气正常
```

每次用户点击都作为显式标注保存。

后续还可以增加：

```text
input_button.recommendation_helpful
input_button.recommendation_wrong
```

---

# Phase 4 — 环境传感器

推荐第一版：

## 卧室

```text
ESP32
├── SEN55
└── SCD41
```

采集：

```text
PM2.5
VOC Index
NOx Index
temperature
humidity
CO₂
```

## 阳台/新风进气附近

```text
ESP32
└── SEN55
```

主要用于观察室外污染变化。

第一阶段不要把 VOC Index 解释为“臭味浓度”。它是环境变化信号。

如果实际运行发现明显异味事件无法被 VOC/NOx 捕捉，再评估 H₂S/NH₃ 电化学传感器。

---

# Phase 5 — 摄像头与 go2rtc

目标是获得稳定的视频流：

```text
camera → go2rtc → Frigate / HA
```

确保：

- 摄像头位置固定；
- 只覆盖需要分析的公共/目标区域；
- 垃圾站主要工作区在画面内；
- 尽量避免不必要地拍摄私人住宅窗口等区域；
- RTSP/go2rtc 服务仅在可信 LAN/VPN 内开放。

---

# Phase 6 — Frigate

第一阶段只检测：

```yaml
objects:
  track:
    - person
    - car
    - truck
```

为垃圾站工作区建立 Zone：

```text
garbage_station
```

只对进入 Zone 的相关对象生成后续视觉分析事件。

这样比 24/7 把所有视频帧送给 VLM 更经济、更稳定。

---

# Phase 7 — Vision LLM

可以采用两条路径。

## Path A：HA AI Task

适合最早原型。

输入：

```text
camera snapshot
```

要求结构化输出：

```json
{
  "state": "compressing",
  "odor_risk": 82,
  "confidence": 0.91,
  "reason": "垃圾车正在压缩/卸载区域持续作业"
}
```

允许状态必须限定为：

```text
closed
idle
truck_arriving
unloading
compressing
truck_leaving
unknown
```

## Path B：Frigate GenAI

适合第二阶段。

Frigate 先用传统检测发现 truck/zone 事件，再将事件生命周期的关键帧交给 VLM。

优势：

- 不需要固定频率分析无变化画面；
- 可以利用多帧理解动作；
- 视频事件与录像天然关联。

---

# Phase 8 — Ollama

本地模型服务可以独立部署在 Apple Silicon 或 GPU 主机。

示例：

```bash
ollama pull qwen3-vl:4b
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

只允许可信 LAN/VPN 访问 11434。

不要直接映射到公网。

视觉模型的任务必须尽量结构化，而不是要求它写长篇自然语言。

---

# Phase 9 — Weather Context

至少加入：

```text
temperature
humidity
wind_speed
wind_bearing / wind_direction
precipitation/condition
```

对垃圾站异味问题，风向和风速尤其重要。

最终希望学习：

```text
垃圾站压缩
+
特定风向
+
特定风速
→
住宅受到影响的概率
```

而不是“只要看到垃圾车就提醒”。

---

# Phase 10 — Recommendation Schema

LLM 不允许自由生成设备动作。

输入允许动作：

```text
normal
sleep
pollution_protection
fast_ventilation
no_action
```

输出 Schema：

```json
{
  "recommendation": "pollution_protection",
  "confidence": 0.91,
  "duration_minutes": 20,
  "reason": "垃圾站正在压缩，当前风向朝住宅方向。",
  "recheck_after_minutes": 20
}
```

必须允许：

```json
{
  "recommendation": "no_action",
  "confidence": 0.88,
  "reason": "垃圾站虽在作业，但当前风向远离住宅且阳台指标稳定。"
}
```

减少提醒本身就是优化目标。

---

# Phase 11 — Policy Guard

在执行通知之前检查：

```text
recommendation ∈ whitelist
confidence >= configured threshold
required sensors available
notification cooldown passed
CO₂ policy satisfied
requested duration <= maximum duration
```

第一版所有实际设备操作都要求人工确认。

---

# Phase 12 — 手机 Actionable Notification

通知示例：

```text
空气环境建议

垃圾站正在压缩垃圾，当前风向朝住宅方向。
过去相似情况下存在较高异味概率。

建议：污染防护模式 20 分钟

[执行]
[忽略]
[30分钟后提醒]
```

点击“执行”以后才调用：

```text
script.air_pollution_protection
```

点击“忽略”同样必须记录，因为它是负反馈。

---

# Phase 13 — Recorder

开发期可以适当提高 HA Recorder 的保留期，例如：

```yaml
recorder:
  purge_keep_days: 90
```

但长期不要无限保存高频原始数据。

HomeMind 应把原始事件压缩成 Episode 后长期保存。

---

# Phase 14 — HomeMind Core 最小服务

第一版建议：

```text
Python 3.12+
FastAPI
SQLAlchemy
SQLite
APScheduler
httpx
websockets
pydantic
```

最低 API：

```text
GET  /health
POST /events
GET  /context/current
POST /recommendations/generate
POST /feedback
GET  /patterns
```

后台任务：

```text
HA event subscriber
context builder
episode builder
pattern aggregation
recommendation evaluator
```

---

# Phase 15 — 第一次数据收集期

最初 1–2 周建议：

```text
只观察
+
用户继续正常手动控制
+
主动点击“现在很臭/空气正常”
```

不要急着让系统“学习出结论”。

重点验证：

- 数据是否连续；
- 手工操作能否区分于自动化；
- 视频状态是否准确；
- 风向数据是否可信；
- 传感器变化与人的嗅觉是否有关系。

---

# Phase 16 — 第一个可验证 Pattern

例如：

```text
条件：
垃圾站 compressing
AND wind_toward_home = true

历史：14 次
发生用户“臭”反馈：11 次

median lag = 11 min
```

这时系统才有依据说：

```text
过去 14 次类似事件中有 11 次在约 11 分钟后出现异味反馈。
```

不要让 LLM 编造这种统计数字。

---

# 故障与降级原则

如果：

```text
Vision unavailable
```

则仅根据空气传感器 + 天气工作。

如果：

```text
Ollama unavailable
```

HA 传统自动化仍正常工作。

如果：

```text
HomeMind unavailable
```

不得影响空调、新风、Home Assistant 本身。

如果：

```text
关键 sensor unavailable
```

推荐系统应降低 confidence 或 no_action，而不是猜测。

---

# 不要在 MVP 做的事情

暂时不要：

- Kubernetes；
- 微服务拆分；
- Kafka；
- 向量数据库；
- 多 Agent；
- 自动 fine-tuning；
- 让 LLM 任意调用所有 HA Service；
- 24/7 对所有摄像头帧做 VLM 推理；
- 一开始就全屋部署。

先证明闭环有效，再增加复杂度。

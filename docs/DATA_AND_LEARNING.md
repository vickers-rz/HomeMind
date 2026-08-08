# Data, Memory and Habit Learning

HomeMind 的“学习”不能等同于把所有 Home Assistant 历史记录塞进 LLM Context。

需要明确区分：**数据、事件、Episode、Pattern、Preference 和 Recommendation Feedback。**

## 1. 数据层级

```text
Raw Sensor Samples
       ↓
State Changes / Events
       ↓
Episodes
       ↓
Patterns
       ↓
Context + Relevant Memory
       ↓
Recommendation
       ↓
Feedback
       └──────────────→ Pattern update
```

## 2. Raw samples

典型数据：

```text
VOC = 103
CO₂ = 886
PM2.5 = 8
wind_speed = 2.8
```

它们主要用于：

- 趋势计算；
- 异常检测；
- Episode 聚合；
- 调试。

不应该长期逐条送给 LLM。

## 3. Events

事件表示发生了有意义的变化。

```json
{
  "event_type": "fresh_air_mode_changed",
  "timestamp": "2026-08-08T23:42:00+08:00",
  "from": "medium",
  "to": "sleep",
  "actor": "human"
}
```

重要事件包括：

- 用户手动控制；
- HA 自动化动作；
- HomeMind 推荐被执行；
- 视觉状态变化；
- 用户空气反馈；
- Presence / activity 变化；
- 关键环境指标显著变化。

## 4. Episode

Episode 是 HomeMind 长期记忆的核心单位。

例：

```json
{
  "type": "garbage_station_pollution_event",
  "start": "2026-08-08T19:31:00+08:00",
  "end": "2026-08-08T19:55:00+08:00",
  "visual": {
    "activity": "compressing",
    "confidence": 0.94
  },
  "weather": {
    "wind_toward_home": true,
    "wind_speed_mean": 2.4
  },
  "environment": {
    "outdoor_voc_delta_pct": 61,
    "indoor_voc_delta_pct": 4,
    "co2_start": 720,
    "co2_end": 845
  },
  "human": {
    "odor_feedback": "bad",
    "feedback_at_minute": 10
  },
  "actions": [
    {
      "action": "fresh_air_off",
      "actor": "human",
      "minute": 2
    },
    {
      "action": "purifier_high",
      "actor": "human",
      "minute": 3
    }
  ]
}
```

Episode 比原始时序数据更适合长期检索和推理。

## 5. Patterns

Pattern 是跨 Episode 的统计规律。

例如：

```text
P(odor_bad | compressing AND wind_toward_home) = 0.79
```

或：

```text
P(user_selects_sleep_mode |
  bedroom_presence
  AND main_light_off
  AND time > 22:30) = 0.86
```

Pattern 至少保存：

```text
support
confidence / probability
conditions
outcome
median delay
last observed
stability
```

低 support 的 Pattern 不应该被描述成“用户习惯”。

## 6. Explicit Preference

显式偏好与统计 Pattern 必须分开。

例如用户明确设置：

```text
睡觉时不要自动关闭空调
```

它应该成为 Policy/Preference，而不是和推断习惯放在同一个概率模型里。

权威顺序建议：

```text
Safety Policy
    >
Explicit User Preference
    >
User-confirmed Routine
    >
Inferred Pattern
    >
Single Episode
```

## 7. Similarity retrieval

MVP 不需要向量数据库。

先使用结构化过滤：

```text
activity = compressing
wind_toward_home = true
time_bucket = evening
presence = home
season = summer
```

再对数值特征计算距离。

只有当 Episode 类型越来越复杂、自然语言语义检索成为明显瓶颈以后，再考虑 embedding/vector retrieval。

## 8. Recommendation feedback

每次推荐都保存：

```json
{
  "recommendation_id": "...",
  "context_id": "...",
  "recommended_action": "pollution_protection",
  "confidence": 0.91,
  "accepted": true,
  "modified": false,
  "response_delay_seconds": 18,
  "outcome": {
    "odor_feedback_after": "good"
  }
}
```

核心指标：

```text
acceptance rate
ignore rate
modified rate
false-positive notification rate
repeat recommendation rate
manual override rate
```

最终目标不是最大化“AI 建议次数”，而是最大化：

```text
useful recommendations / total interruptions
```

## 9. Manual actions as weak supervision

用户没有必要每天回答调查问卷。

自然操作本身就是监督信号。

例如：

```text
垃圾站开始压缩
↓ 3 min
用户关闭新风
↓ 20 sec
用户提高净化器档位
```

如果这一序列重复发生，它可以形成候选 Pattern。

但必须区分 actor，避免把 HA 既有自动化误认为用户偏好。

## 10. Activity inference

长期可以从事件序列推断活动状态：

```text
PreparingForSleep
Cooking
LeavingHome
ReturningHome
Working
WatchingTV
Sleeping
```

第一阶段应采用规则/特征 + LLM 解释的混合方式，而不是训练一个大型行为模型。

例如：

```text
bedroom_presence = true
main_light = off
bedside_light = on
phone_charging = true
low_activity_for = 15 min
```

可以得到：

```text
activity_candidate = PreparingForSleep
confidence = 0.82
```

## 11. Learning cadence

建议把学习分成两个时间尺度。

### Online

事件发生时：

```text
build context
retrieve patterns
generate recommendation
record feedback
```

### Offline

每天低频执行：

```text
build/merge episodes
recalculate pattern statistics
expire weak patterns
update acceptance statistics
summarize long-term behavior
```

这样避免每次事件都调用 LLM 做昂贵的“重新学习”。

## 12. Explainability

每个 Recommendation 最好都能追溯到：

```text
Current observations
Relevant patterns
Similar episodes
Explicit preferences
Policy checks
```

因此数据库设计中应该保留引用关系。

用户最终应该能够问：

> 为什么你刚才建议我关闭新风？

系统能回答：

```text
1. 垃圾站被识别为 compressing；
2. 当前风向朝住宅；
3. 阳台 VOC Index 在 6 分钟内上升 23%；
4. 过去 12 个相似 Episode 中 9 个出现了“很臭”反馈；
5. 当前 CO₂ 允许短时关闭新风；
6. 因此推荐污染防护模式 20 分钟。
```

这里的统计数字必须来自数据库，而不是 LLM 自行生成。

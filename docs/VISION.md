# HomeMind：项目愿景与设计原则

## 初衷

今天大量所谓“智能家居”，本质仍然是联网家电加规则自动化。

用户需要提前猜测未来会发生什么，再人工编写大量：

```text
IF 时间 = 23:00
AND 人在卧室
THEN 新风 = 睡眠档
```

这种方式的问题不是自动化能力不足，而是系统没有形成对“生活情境”的理解。

真正有价值的家庭智能系统应该能够：

1. 观察用户真实的生活行为，而不是要求用户先把所有习惯写成规则；
2. 将设备、环境、时间、天气、视觉事件和人的行为组合成 Context；
3. 从长期历史中寻找重复模式；
4. 理解用户当前可能正在做什么以及为什么；
5. 在适当的时候提出建议；
6. 让用户保留最终决定权；
7. 从接受、拒绝和修改中继续学习。

因此 HomeMind 的核心命题不是：

> 如何让 LLM 控制 Home Assistant？

而是：

> 如何让家庭自动化系统逐渐形成一个属于这个家庭自己的情境模型和行为模型？

## 从“Automation”到“Recommendation”

传统模型：

```text
Trigger → Condition → Action
```

HomeMind：

```text
Observation
   ↓
Context
   ↓
Historical Similarity
   ↓
Pattern + LLM Reasoning
   ↓
Recommendation
   ↓
Human Decision
   ↓
Action
   ↓
Feedback
   └────────→ Learning
```

最关键的变化是中间增加了 **Context、Reasoning、Recommendation 和 Feedback**。

## 为什么默认不自动执行

一个会学习的系统在早期必然会犯错。

如果“学习结果”直接等于设备控制，错误模式会迅速变成错误自动化。HomeMind 因此采用渐进式自治：

### Level 0 — Observe

只记录，不提醒、不执行。

### Level 1 — Recommend

生成建议，由用户确认。

### Level 2 — Confirmed Routine

用户多次确认某个模式以后，可以提出“是否允许以后自动执行”。

### Level 3 — Bounded Autonomy

只对低风险、高置信度、明确授权的场景自动执行，并始终允许撤销。

默认目标是 Level 1，而不是追求无人值守。

## HomeMind 不是什么

HomeMind 不应该成为：

- Home Assistant 的替代品；
- 一个把所有实体直接暴露给 LLM 的聊天机器人；
- 一个依赖巨大 Prompt 保存全部家庭历史的系统；
- 一个把任何数值异常都交给 LLM 判断的系统；
- 一个为了“Agent”而堆叠 Agent 框架的项目。

## 设计哲学

### Deterministic where possible, probabilistic where useful

确定的问题用确定性程序解决。

例如：

- CO₂ 是否超过安全策略阈值；
- 某个实体当前是否 unavailable；
- 新风是否已经关闭超过最大允许时间。

不需要 LLM。

真正适合 LLM 的问题是：

- 用户是不是正在准备睡觉？
- 垃圾站当前到底是在卸料还是普通车辆经过？
- 当前情况和过去哪些 Episode 相似？
- 多个互相冲突的因素应该怎样解释给用户？

### Learn behavior, not just device states

HomeMind 不应该只学习：

```text
23:42 fan = sleep
```

而应该逐渐理解：

```text
PreparingForSleep
```

可能由以下行为共同构成：

```text
主灯关闭
+ 床头灯打开
+ 手机充电
+ 人在卧室
+ 活动量下降
```

设备状态是证据，生活情境才是目标。

### Explicit feedback is valuable data

用户点击：

- “现在很臭”；
- “空气正常”；
- “执行建议”；
- “忽略”；
- “以后不要这样建议”；

都属于高价值标注。

HomeMind 应优先利用这些真实反馈，而不是假装模型能够凭空理解一个人的全部偏好。

## 首个真实场景：空气环境

HomeMind 的第一个实验场景选择空气环境，是因为它天然需要多模态 Context：

```text
空气传感器
+
视觉事件
+
天气 / 风向
+
时间
+
人在不在家
+
当前新风/空调/净化器状态
+
历史操作
```

例如垃圾站正在压缩垃圾并不一定意味着住宅一定会受到影响。

系统还应该知道：

- 风是不是朝住宅方向吹；
- 过去类似风向是否真的发生过异味；
- 阳台 VOC 是否开始变化；
- 室内 CO₂ 是否允许暂时关闭新风；
- 用户过去遇到类似情况通常怎么处理。

只有这些因素组合起来，才构成一个真正有意义的 Recommendation。

## 长期愿景

HomeMind 最终应该形成一个家庭自己的 Environment + Behavior Model。

它不仅可以应用于空气环境，还可以扩展到：

- 睡眠环境；
- 灯光；
- 温湿度；
- 能源管理；
- 噪声；
- 安防；
- 家庭影音；
- 日常 Routine；
- 设备异常诊断。

目标不是让房子“自己做更多事情”，而是让系统 **更少打扰、更懂上下文、更知道什么时候应该保持沉默**。

# 0.3.0 动态策略观察版

本次交付按已批准计划先开始7天观察。动态计算、会话恢复、SQLite逐次审计、HA展示已实现。**没有接管风机**；即使改变模式辅助实体，本版本也不发送动作，HA保留的执行脚本明确拒绝执行。现有900/700自动化继续工作，因此影子手动锁定暂不能保护用户操作。

## 动态启停已启用

经用户要求，原固定900/700自动化已停用，HA已加载两条动态自动化。启动阈值读取 `sensor.homemind_air_start_co2` 和 `sensor.homemind_air_start_pm25`；停止阈值读取 `sensor.homemind_air_target_co2` 和 `sensor.homemind_air_target_pm25`。停止仍需两个指标同时低于目标，并连续保持2分钟。

当前HomeMind仍处于observe部署，但这两条HA动态自动化是实际执行路径：它们直接控制新风机。手动锁定、最低运行时间和手动档位保护尚未完整接入HA执行条件；在完成下一步执行保护前，手动操作可能被动态停止自动化影响。

## 已实现规则

- 每30秒计算、写入决策记录并通过MQTT推送；每15分钟更新本地星历节气。
- 手动开机最低10分钟；初始CO₂≤700时目标600；其他场景CO₂目标650/700/800、PM2.5目标15/21。连续两分钟低于两个目标才建议停机。
- 手动关机锁定30–480分钟，锚定原始关机时刻；每5分钟复算。CO₂十分钟线性趋势以±2 ppm/min为明显变化。
- 室外PM2.5>35、PM10≥150或沙尘增加60分钟；温差≥15℃加60分钟，但温湿度与预报合计修正限制为±20%。绝对湿度差>5 g/m³加15分钟，<2减15分钟；未来1/3/6小时温差≥15℃加15分钟。重复否决至少240分钟。
- CO₂≥1500连续10分钟产生接管建议；≤1000退出紧急状态。重启和关键数据失效均清除连续时间证据，不把离线时间计入。
- 手动调档保护30分钟，不妨碍停机建议；自动调档建议相隔至少10分钟，幅度至少40。
- 下降趋势至少覆盖5分钟、6个采样点，预测>120分钟或无法下降时显示不可估计。该估计不是关机计时器。
- 天气/BLE失效取消对应修正；CO₂、室内PM或风机不可用禁止动作建议。last_reported用于区分数值不变与未上报，每5分钟通过WebSocket快照补查。
- 来源仅在已知自动化context匹配时判为自动；其它有效变化标为人工/推定人工。快照和unavailable恢复不制造人工操作。米家/物理操作与丢失context的自动动作仍有歧义，需观察期核对。

## 接口与记录

`homemind/air/v1/recommendation`新增`target_co2`、`target_pm25`、`minimum_run_minutes`、`minimum_run_until`、`estimated_remaining_minutes`、`lockout_until`、`flow_hold_until`、`decision_id`、`session_id`、`execution_mode`、`algorithm_version`、`stale`、`not_executed_reason`。null表示不可估计或没有期限，不表示0。

SQLite新增`decisions`、`sessions`、`actions`。每次决策保存输入快照、理由、版本及执行状态。动作结果表预留关联请求和设备反馈；观察版动作请求数必须为0。90天清理保护活动会话，UTC保存，北京时间界面展示。SQLite写失败触发worker退出，由s6重启并报告不可用。

导出到标准输出（不包含凭据），时间参数使用UTC ISO格式：

```sh
docker exec --user 1000 homemind-air python -m app.export --format json --since 2026-09-07T00:00:00+00:00
docker exec --user 1000 homemind-air python -m app.export --format csv --session-id SESSION_UUID
```

HA新增目标浓度、最低运行时间、预计剩余时间、三个截止时间、理由和“未接管”传感器。理由完整字段与最新建议作为属性；状态文本截断到240字符。

## 审批与后续接管：明确尚未交付的部分

保留recommend/bounded_auto选项及审批自动化，审批辅助开关默认off，通知和反馈自动化初始禁用；观察版收到反馈仅记录ignored。取消`approved`绕过，执行脚本和执行器双重拒绝所有动作。

完成7天观察并核对人工会话后，下一批实现并验证：持久化请求去重、有效审批与模式代次绑定、HA侧即时手动保护、故障期限镜像与基线互斥、真实执行结果核对。**现有保留执行器不是已完成的闭环保护，不得只删除false条件就启用。**阶段先手动锁定，再动态风量，最后动态目标。没有部署LLM。

观察验收：0条动作请求；无无效数据导致动作建议；每个决策有日志；BLE/QWeather/基线自动化正常；重启恢复不产生虚假手动会话。至少7个完整自然日且典型手动场景足够后再评估。7天并不自动意味着验收通过。

参考接口：[HA WebSocket](https://developers.home-assistant.io/docs/api/websocket/)、[HA Weather entity](https://developers.home-assistant.io/docs/core/entity/weather/)。天气小时预报通过`weather/subscribe_forecast`订阅，缺失不虚构预报数据。

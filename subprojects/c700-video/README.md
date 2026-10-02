# HomeMind C700 Video — 摄像头与视频证据子项目

本项目是 **HomeMind 的摄像头接入、录像元数据与保留策略子系统**。它将小米 C700 的专有视频传输转换为标准视频入口，并为后续视觉理解提供可追溯的时间线。源码独立维护于 [go2rtc-c700-cloud-relay](https://github.com/vickers-rz/go2rtc-c700-cloud-relay)（公开仓库）。本目录是 HomeMind 内直接可浏览的子项目文档入口，可直接阅读职责、架构并访问实现源码。

## 在 HomeMind 中的位置

```text
小米 C700 ── MISS/CS2 ── patched go2rtc ── RTSP/WebRTC
    │                                      │
    │                               HA / 后续 Frigate、VLM
    ├── RDT SD 时间线 ── Pi 索引器 ── SQLite  │
    └── 摄像头主动 SMB 备份 ── Pi NAS         │
                               │            ▼
                         N100 保留规划   HomeMind Context（规划）
                               │            │
                         Pi 受限执行器   推荐 / Policy / 用户反馈
```

视频入口与录像保留已经有代码和实机研究记录；Frigate/VLM 到 HomeMind Context 的语义事件链路是后续集成目标。摄像头的 `PeopleMotion` / `Face` 标签来自设备协议，不能当作本项目自行训练或验证的视觉模型结果。

## 能力与证据

| 能力 | 当前证据 | 边界 |
|---|---|---|
| LAN / 云中继实时接入 | 模式切换脚本、MISS/CS2 补丁、视频探测工具 | 不承诺任意网络下均可直连或达到固定延迟 |
| 标准视频出口 | go2rtc RTSP/WebRTC；稳定流名 `c700` | 客户端解码与音频兼容性需单独验证 |
| SD 时间线索引 | RDT 命令 6、命令 11、SQLite 索引器 | 索引读取不等同于历史视频下载完成 |
| 受保护的夜间保留 | N100 planner、Pi agent、离线单元测试 | 未知、过期、缺段、有运动或 saved 状态保留 |
| 运维与状态 | Mac launchd、N100 服务脚本、HA 状态包 | 历史部署记录不能替代当前在线健康检查 |
| AI 场景理解 | HomeMind 架构中的视觉事件入口 | 垃圾车识别、异味预测与视觉推荐闭环尚未在本子项目验收 |

## 阅读顺序

1. [架构、数据契约与故障边界](ARCHITECTURE.md)
2. [技术说明与演示清单](TECHNICAL_GUIDE.md)
3. [源码与运行文档](https://github.com/vickers-rz/go2rtc-c700-cloud-relay)（公开）

## 仓库关系

HomeMind 负责系统级目标、上下文、推荐与策略；C700 Video 负责视频基础设施和录像证据。两者为父项目与独立源码子项目关系，不是 Git submodule。HomeMind 在本目录维护不含账号、实际主机地址及现场录像的概览；源码仓库维护补丁、工具与具体运行手册。修改接口或能力边界时应同步两侧文档。

文档核对日期：2026-10-02。本次基于本地源码及历史研究记录核对，没有重新访问摄像头或验证线上部署。

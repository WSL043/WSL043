# Inside the workshop

我喜欢小工具，但小工具也会遇到真实的工程问题：异步状态过期、运行中的任务如何停止、更新时哪些数据必须保留，以及一个看起来有效的实验究竟验证到了哪一步。

这里把主页里的几个入口展开，给出可以继续阅读和验证的位置。

## Contribution Arcade → Inspectable search

主页的五种原生 SVG 并不是手写位移动画。它们先读取贡献日历，再由独立模型规划动作，最后生成矢量时间轴。其余五种玩法使用外部生成器；两者在 [Actions 工作流](.github/workflows/daily-arcade.yml) 中分别调用。

| 工程问题 | 当前实现 | 验证入口 |
| --- | --- | --- |
| 炸弹人能否真正撤离 | BFS 获取可达区，爆炸遇墙停止，撤离终点必须在爆炸范围外 | [模型](scripts/svg_models.py) · [路径与伤害测试](tests/test_heatmap_models.py) |
| 连连看是否隔墙消除 | 同等级配对；路线经过空格或外围走道，最多两次转向 | [模型与边界测试](tests/test_heatmap_models.py) |
| 动画是否篡改日期形状 | 拼装覆盖原始活跃格；传送保持格子身份与颜色；生成完整日历 | [矢量渲染](scripts/svg_arcade.py) |
| 网络失败或旧任务晚到 | 抓取失败保留上一版；发布前检查来源、SHA-256 与主分支是否改变 | [数据管线](scripts/heatmap_data.py) · [发布校验](scripts/publish_arcade.py) |

新增的搜索比较直接显示在 **GitHub README 内**，不需要跳去个人网站。三种搜索使用同一份贡献日历、相同的起终点和四方向邻接规则；波纹显示实际展开节点，光点沿算法返回的路径前进。

- **BFS** 用 FIFO 队列求最少步数；有权地形上不保证最低代价。
- **Dijkstra** 用二叉最小堆求最低代价。
- **A*** 使用 `f = g + Manhattan`。进入代价为 `1 + 贡献等级`，最低为 1，所以启发式可采纳且一致。并列优先级按入队顺序处理。
- 固定周三行首尾的有效日期作为起终点，不为了放大算法差异挑选有利案例。缺失日期不可走，起点代价不计，贡献等级不是精确提交次数。
- `expanded` 是实际展开的不同节点数，包括终点；动画速度只是回放节奏，不能据此声称 A* 的设备耗时更少，也不保证它在所有地图上展开更少节点。
- 每次原生 SVG 更新时，用同一份新快照重算比较。报告与 SVG 纳入发布哈希校验，发布前再次运行搜索并重建 SVG，对比结果一致后才复制文件。
- 深浅色和减少动态效果均有处理；静态模式保留原始日历及真实统计。数据不可达时显示不可达，不补造路径。

[算法实现](scripts/search_race.py) · [JSON 搜索轨迹](assets/arcade/search-comparison.json) · [原始日历](assets/arcade/heatmap-snapshot.json) · [交叉校验测试](tests/test_search_race.py)

本地复现（Python 标准库，无额外依赖）：

```sh
python -X utf8 -m unittest discover -s tests -v
python -X utf8 -m scripts.preview_search --output .rotation-preview/search
```

第二条命令只用仓库已有快照生成预览并打印比较结果，不抓取在线数据，也不修改主页。测试用独立 Bellman–Ford 实现交叉检查 200 张加权、含障碍的地图。

## Account state that survives asynchronous work

[Codex Subscription for DSH](https://github.com/WSL043/dsh-codex-subscription) 的一个核心问题是：请求发出后，用户可能已经切换了账号。旧响应不能覆盖当前账号的状态；失败也不应该悄悄改走另一条付费路由。

项目目前公开记录了账号状态对账、超时与旧响应隔离、可重试的读取，以及不包含凭据和账号标识的支持报告。查看[项目说明中的「核心优势」和「功能」](https://github.com/WSL043/dsh-codex-subscription#核心优势)以及[测试工作流](https://github.com/WSL043/dsh-codex-subscription/actions/workflows/ci.yml)。

## A portable runtime with a separate data lifecycle

[DSH Portable](https://github.com/WSL043/DSH-Portable) 将桌面壳与上游内核作为独立版本维护。可再生的程序组件参与更新，会话、设置、插件与工作区有自己的保留边界。便携性也有条件：完整退出后移动，同系统同架构继续使用。

具体边界可见[更新与修复](https://github.com/WSL043/DSH-Portable#更新与修复)和[跨电脑迁移指南](https://github.com/WSL043/DSH-Portable/blob/main/docs/move-between-computers.md)。

## LoudEase: a complete local audio path

[LoudEase](https://github.com/WSL043/loudease) 从用户授权的 Chrome 标签页采集音频，在本地 AudioWorklet 中完成处理。K 加权门控测量建立节目响度基线，安静细节提升有明确上限，快速保护与 5 ms 前瞻限幅处理突发响声。播放器静音和零音量仍然是硬边界。

项目同时维护商店发行包与开发诊断包，两者共用音频核心；商店包移除开发诊断入口。它目前是公开 Beta，各站点的验证范围和待社区测试范围分开记录。继续阅读 [Audio DSP](https://github.com/WSL043/loudease/blob/main/docs/AUDIO_DSP.md)、[架构](https://github.com/WSL043/loudease/blob/main/docs/ARCHITECTURE.md)和[测试矩阵](https://github.com/WSL043/loudease/blob/main/docs/TEST_MATRIX.md)。

## Updated Again: playful content, a verifiable update protocol

[Updated Again](https://github.com/WSL043/updated-again) 把每日内容胶囊与客户端核心版本分成两条时间线。胶囊经 Ed25519 签名，安装前验证签名与内容哈希，安装时保存本地快照以支持回滚；Web、PWA 与 Tauri 客户端共用协议和能力注册表。

错峰调度、末班保底与断档回填维护日更账本；受限社区内容有独立的自动验证和恢复边界。桌面产物仍标为 Developer Preview。继续阅读[架构](https://github.com/WSL043/updated-again/blob/main/docs/ARCHITECTURE.md)和[每日发布契约](https://github.com/WSL043/updated-again/blob/main/docs/DAILY_RELEASE_CONTRACT.md)。

## Agent Skills Neutral: maintaining reasoning workflows

[Agent Skills Neutral](https://github.com/WSL043/agent-skills-neutral) 维护一个常驻思考核心与可选工作流。创作、来源研究和演化评估留在维护仓库，任务执行只消费紧凑的运行时包。语义选择是默认路径，词法选择脚本只是离线辅助。

候选改进需要基线比较、留出任务、回归和明确的保留决策；演化运行器记录验证状态，并不自动生成或晋升候选。这些是项目定义的评估机制，不等同于已经证明对所有模型和任务都有收益。继续阅读[运行时包](https://github.com/WSL043/agent-skills-neutral/blob/main/docs/RUNTIME_BUNDLE.md)、[学习循环](https://github.com/WSL043/agent-skills-neutral/blob/main/docs/LEARNING_LOOP.md)和[演化运行器](https://github.com/WSL043/agent-skills-neutral/blob/main/docs/EVOLUTION_RUNNER.md)。

项目说明依据 2026-09-12 的公开仓库内容整理；具体支持状态以各项目当前文档和 Release 为准。

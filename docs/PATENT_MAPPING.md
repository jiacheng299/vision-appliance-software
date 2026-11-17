# 交底书对照表（答辩用一页式）

本文把《一种基于时效语义画像与有效观察校验的视频分析模型组合路由方法及系统》的
要素逐条对到代码位置、测试与实现状态，用于答辩、开题与论文的"系统实现"章节。
逐轮改动细节见 [验收记录](ACCEPTANCE_PATENT.md)，设计与不可实现清单见
[设计文档](superpowers/specs/2026-11-17-patent-framework-design.md)。

**一句话结论**：交底书的四个方法要素（时效画像、需求图与组合求解、有效观察三态、
漂移与版本化切换）都已经在这套系统里跑起来并有测试兜底；**没做到的**是
"让候选组合真的并行推理"与"用观察结论改变业务报警"，以及多智能体强化学习本体。

## 一、模块对照（M1–M9）

| 模块 | 交底书职责 | 代码位置 | 关键测试 | 状态 |
| --- | --- | --- | --- | --- |
| M1 | 自然语言任务解析、结构校验、待确认项 | 复用 `modules/agent_templates`、`modules/models/planning.py` | `test_task_modes.py`、`test_template_matching.py` | 复用既有实现 |
| M2 | 抽样与画面物理指标 | `modules/semantics/metrics.py`（127 行） | `test_semantic_profile.py`、`test_executor_observation.py` | 完成（遮挡不可测） |
| M3 | 时效语义画像（固有/动态/运行三层） | `modules/semantics/profile.py`、`models.py` | `test_semantic_profile.py`、`test_semantics_api.py` | 完成 |
| M4 | 任务需求图与四类依赖边、反向索引 | `modules/routing/graph.py`（122 行） | `test_requirement_graph.py` | 完成 |
| M5 | 模型能力管理（观察前提/分桶质量/资源） | `modules/routing/capability.py`（145 行） | `test_route_solver.py` | 完成（质量为示例值） |
| M6 | 组合求解：可修复性过滤 + 式(2) | `modules/routing/solver.py`（290 行） | `test_route_solver.py`、`test_routing_api.py` | 完成 |
| M7 | 版本化配置发布 | `RevisionConfig` + `RunDTO.profile_version/route_version` + `route_states` | `test_agent_workflow.py`、`test_routing_state.py` | 完成（未下发给执行器） |
| M8 | 有效观察校验（五门禁 + 三态） | `modules/semantics/observe.py`（113 行）、`window.py` | `test_observation_gate.py`、`test_observation_window.py` | 完成 |
| M9 | 漂移判断与局部重路由 | `modules/routing/drift.py`、`hysteresis.py`、`state.py` | `test_drift_hysteresis.py`、`test_routing_state.py` | 完成 |

## 二、流程对照（S1–S14）

| 步骤 | 交底书动作 | 落点 | 状态 |
| --- | --- | --- | --- |
| S1 | 接收任务与摄像头信息 | `/agents/{id}/run-groups` + 自然语言匹配 | 完成 |
| S2 | 初始抽帧、建立分层画像 | `POST .../semantic-profile/bootstrap`：固有层取设备字段，录像源从影片前 1/10 取一帧写入保守的 `lighting`；其余动态属性由运行中的观察或人工写入 | 完成（摄像头源不做首帧取图，已说明） |
| S3 | 生成任务需求图 | `routing.graph.build(rule, duration_seconds)` | 完成 |
| S4 | 过滤并求解组合 | `solver.evaluate / solve`（硬过滤 + 式(2)） | 完成 |
| S5 | 发布带版本的组合配置 | `route_states.active_version` + 观察记录按版本盖章 | 部分：不向执行器下发组合 |
| S6 | 运行并采集观察指标 | `local_execution/service.py` + `semantics/window.py` | 完成 |
| S7 | 判定有效观察 | `semantics/observe.evaluate`（五门禁） | 完成 |
| S8 | 输出结果（三态） | `observation_records.verdict` = `detected / not_detected / insufficient` | 完成（记录层） |
| S9 | 输出观察不足 | 同上 + `reasons` 逐条原因 | 完成 |
| S10 | 判断更新条件 | `drift.detect`（只认新证据，过期不算反向变化） | 完成（属性层） |
| S11 | 定位受影响子图 | `graph.affected_requirements` + `solver.solve_local` | 完成 |
| S12 | 求解替换组合 | `solver.solve_local`（无法局部化则退化为全图重算） | 完成 |
| S13 | 判定是否进入候选验证 | `hysteresis.decide`（ε_in/ε_out/最短驻留/L 窗口） | 完成 |
| S14 | 影子运行、预热、原子切换 | `state.advance_window`（计数与原子切换版本）+ `routing/preheat.py`（并存成本：+85 MB / ~90 ms / 逐帧 ±2 ms）+ `routing/shadow.py`（同一批帧两个会话逐帧比对） | **部分：资源与逐帧对照都已有实测，但两个会话加载的是同一份产物，仍未接真实第二模型** |

## 三、公式对照

| 公式 | 实现 | 验证 |
| --- | --- | --- |
| 式(1) `r_a(t)=q_a·exp(−(t−t_a)/τ_a)·I(t_a≤t<T_a)` | `semantics/profile.attribute_strength` | `test_semantic_profile.py`：衰减值、硬失效置 0、未来时刻拒绝、冲突态 |
| 式(2) `J(K)=C+αH−βX−γR−δS` | `routing/solver.evaluate` | `test_route_solver.py`：**复现交底书实施例一，0.675 / 0.905 / 0.725 完全一致** |
| 式(3) 进入/取消候选与滞回 | `routing/hysteresis.decide` | `test_drift_hysteresis.py`：双阈值、最短驻留、L 个有效窗口、硬失效旁路 |

## 四、五项必要技术特征（F1–F5）

| 特征 | 实现要点 | 证据 |
| --- | --- | --- |
| F1 属性级时效证据结构 | 每项动态属性带来源类型、来源帧时刻、ROI、观测时刻、置信度、衰减常数、硬失效时刻、状态、版本；过期转"未知"而非相反事实 | `test_semantic_profile.py`、`test_expiry_yields_unknown_never_the_opposite_fact` |
| F2 任务需求与能力依赖 | 需求节点 + 串联/联合/替代/时序四类边；能力不止记类别，还记观察前提与分桶质量 | `test_requirement_graph.py`、`test_route_solver.py` |
| F3 真实帧窗口的有效观察 | 五门禁（帧时间/ROI/画质/路径/版本）+ 三态；**未检出比检测到要求更严**：未测定项只阻止"未检出" | `test_observation_gate.py`（13 项） |
| F4 有效观察驱动的局部更新 | 属性→需求反向索引定位子图，固定未受影响部分只重算替换部分 | `test_lighting_drift_only_reroutes_the_detector` |
| F5 与观察记录联动的版本化切换 | 候选需累计 L 个有效窗口才切换 `route_version`，旧窗口保持自己的版本 | `test_switching_requires_the_configured_number_of_valid_windows` |

## 五、新增数据库表（6 张，全部为新增，可单独回滚）

| 表 | 作用 |
| --- | --- |
| `semantic_profiles` | 每个视频源的画像（固有层/运行层/版本/视场版本） |
| `profile_events` | 画像版本事件（固有层更新/属性写入/属性删除，含变更前后取值），供时间线交叉引用 |
| `profile_attributes` | 动态属性，含来源帧、ROI、时刻、置信度、衰减常数、硬失效、状态、版本 |
| `observation_records` | 窗口级观察记录：五元组绑定 + 指标 + 门槛 + 五门禁明细 + 三态结论 |
| `route_states` | 每个任务通道×视频源的当前组合、活动版本、候选、有效窗口计数、漂移游标 |
| `route_decisions` | 追加式决策审计（基线/刷新/漂移/进入/取消/切换/阻塞） |

迁移链：`0009_semantic_observation` → `0010_route_state`，均为纯新增。

## 六、新增接口（17 个）

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/sources/{id}/semantic-profile` | 读取分层画像，按 `at` 计算强度 |
| PUT | `/sources/{id}/semantic-profile` | 写入固有层 |
| PUT | `/sources/{id}/semantic-profile/attributes/{key}` | 写入/刷新动态属性 |
| DELETE | `/sources/{id}/semantic-profile/attributes/{key}` | 删除属性 |
| POST | `/agents/{id}/observations` | 提交窗口观察，返回三态 |
| GET | `/agents/{id}/observations` | 观察记录（筛选 + 游标分页 + 统计） |
| GET | `/agents/{id}/observations/{observation_id}` | 单条观察记录（含门禁逐项明细） |
| GET | `/sources/{id}/routes?rule=` | 路由评估：需求图 + 能力表 + 候选评分 + 排除原因 |
| GET | `/agents/{id}/routing` | 路由状态（当前版本/候选/漂移/受影响子图） |
| GET | `/agents/{id}/routing/decisions` | 决策审计 |
| POST | `/agents/{id}/routing/propose` | 评估并提议候选 |
| POST | `/agents/{id}/routing/cancel` | 取消候选 |
| GET | `/tracking/policies` | 追踪策略注册表（含未安装的 MARL 槽位） |
| POST | `/routing/preheat` | 实测并存第二份会话的内存与延迟代价 |
| POST | `/sources/{id}/semantic-profile/bootstrap` | 按设备记录初始化画像（只填缺项） |
| GET | `/sources/{id}/semantic-profile/events` | 画像版本事件 |
| GET | `/agents/{id}/routing/timeline` | 画像事件与路由决策合并后的时间线 |

## 七、界面落点

| 界面 | 位置 | 展示内容 |
| --- | --- | --- |
| 侧栏分组 | 左侧主导航 | 四组对应流程：采集（S1–S6）→ 运行与观察（S6–S9）→ 结果（S8–S9）→ 管理与诊断；路径未变 |
| 任务视图页签 | 智能体管理 → 任务 → 查看画面与报警 | 四个页签按交底书链路排列：画面（S6 采集）→ 有效观察（S7–S9）→ 路由候选（M6/S13）→ 事件（结果）；模拟数据源只显示画面与事件 |
| 有效观察 | 任务视图 → 有效观察 | 三态徽标、帧窗口、实际帧率、过曝比例、路由版本、失效原因、结论统计与筛选；每行可打开**门禁逐项明细**（门禁/结果/实测/门槛/说明 + 实测指标 + 三类版本），也可跳到路由 |
| 路由候选 | 任务视图 → 路由候选 | 当前路由版本与成员、候选与增益、有效窗口进度、漂移与受影响子图、可行/被排除候选及原因、**画像与路由合并时间线**（同来源版本变更才标绿）、关联策略、未标定口径提示 |
| 时效语义画像 | 视频源详情下方 | 固有层编辑、动态属性表（状态/强度/有效期）、写入与删除、"按设备记录初始化" |

## 八、五步演示脚本（答辩现场约 5 分钟）

0. **一条命令复现**（可选）：`deploy/scripts/routing_smoke.py`、`deploy/scripts/preheat_measure.py`、`deploy/scripts/shadow_compare.py`。
1. **看能力边界**：打开 `运行状态`，指出 `GPU 采集器 unavailable`、`MediaMTX ready`——系统不伪造未接入能力。
2. **建立画像**：进入某个视频源 → `时效语义画像` → 填写固有层 → 写入 `lighting = daylight`（有效期 600 秒）。刷新页面可看到强度与剩余秒数。
3. **看路由选择**：任务的 `路由候选` 页签 → 显示 `评估首选：YOLO11n ... 综合评分 1.6225`，以及 7 条"未安装"的排除原因、最近路由决策与"质量数字是示例值"的口径提示。
4. **制造漂移**：把 `lighting` 改成 `strong_glare` → 再点 `评估并提议` → 分桶变为 glare、`没有可行组合`、原因含"低于必需质量：person_detect 0.45 < 0.60"；决策审计新增一条 `blocked`。
5. **看有效观察**：启动一个真实任务 40 秒以上 → 切到 `有效观察` 页签出现三态记录；人为遮挡或强光时会出现 `insufficient` 而不是 `not_detected`。点某行的"路由"可跳到该视频源的路由页签。

## 九、明确未实现（论文必须如实写）

| 未实现 | 影响 | 说明位置 |
| --- | --- | --- |
| 候选组合真实并行推理 | 已实测并存成本（+85 MB / ~90 ms），但执行器仍只加载一项能力 | 验收记录第 9 节第 2 条 |
| 观察结论改变业务报警 | 观察目前只记录，不抑制报警 | 第 1 条 |
| 能力质量分桶标定 | 质量数字是保守示例值，不是准确率 | 第 3 条 |
| 遮挡比例测量 | 单帧不可测，保持"未测定" | 第 5 条 |
| 设备报文推理服务 | 无真实设备平台 | 第 7 条 |
| 摄像头源的自动建画像 | 只做固有层；动态层需运行中的观察或人工写入 | S2 行 |
| 跨模型的影子对照 | 两次加载的是同一份 ONNX，只能证明确定性与代价 | 验收记录第 2 条 |
| 多智能体强化学习追踪本体 | 只有可插拔接口与契约，无训练与权重 | 第 12 条 |

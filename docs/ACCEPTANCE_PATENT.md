# 专利框架落地验收记录

本文件随每一轮实现增量更新，用于说明"改了什么、怎么验证、什么还没做、哪些做不了"。设计依据见 [专利框架设计](superpowers/specs/2026-11-17-patent-framework-design.md)，分阶段任务见 [实施计划](superpowers/plans/2026-11-17-patent-framework.md)。

当前基线：`92ecfa1` 之上共 37 个提交，全部只提交未 push。

> 需要一页纸看"交底书哪一条落在哪段代码"时，直接看 [交底书对照表](PATENT_MAPPING.md)；
> 需要直接写进论文的成稿章节时，看 [系统实现（章节初稿）](THESIS_IMPLEMENTATION.md)。

## 一、总体路线与状态

| 阶段 | 内容 | 对应交底书 | 状态 |
| --- | --- | --- | --- |
| 一 | 时效语义画像、画面指标、有效观察三态、持久化与接口 | F1/M3、F3/M8、式(1) | **已完成（第 1 轮）** |
| 二 | 执行器影子接入，`RunDTO` 补版本字段，前端"有效观察"面板 | M2、M7、S6–S9 | **已完成（第 2 轮）** |
| 三 | 需求图、能力表扩展、组合求解 | F2/M4–M6、式(2) | **已完成（第 3 轮）** |
| 四 | 漂移判定、局部重路由、式(3) 滞回与路由版本切换 | F4/F5/M9、式(3) | **已完成（第 4 轮）** |
| 五 | 前端信息架构改造 | M1–M9 | **已完成（第 5、6、9、11、12、13 轮）**：侧栏按「采集 → 运行与观察 → 结果 → 管理与诊断」四组重排，任务详情四个页签、画像编辑、观察↔路由互跳、画像与路由合并时间线、门禁逐项明细全部上线 |
| 六 | 追踪策略接口（为多智能体强化学习预留） | — | **接口、界面展示与外部装载位完成（第 5–6、14 轮）**；MARL 本体与权重不在本仓库，接入方式见 [MARL 追踪接入契约](MARL_TRACKING_CONTRACT.md) |

## 二、提交记录

| 提交 | 说明 |
| --- | --- |
| `2cba084` | `docs: 新增专利框架落地设计与实施计划`：差距对照、方案选型、M1–M9 映射、7 项不可实现清单、六阶段排期 |
| `b63ac67` | `feat(semantics): 落地时效语义画像与有效观察三态判定`：18 个文件，+6259 / −1963（其中 `contracts/openapi.json` 与 `generated.ts` 为重新生成） |
| `4600070` | `docs: 新增专利框架验收记录并在 README 标注改造进度` |
| `218d2ce` | `feat(semantics): 执行器影子接入有效观察，不改动报警行为`：17 个文件，+715 |
| `25d386f` | `docs: 更新验收记录至第 2 轮（执行器影子接入）` |
| `5ce3726` | `feat(routing): 需求图、能力表与式(2) 组合求解`：13 个文件 |
| `9bf20a0` | `docs: 更新验收记录至第 3 轮（需求图与组合求解）` |
| `cdd9137` | `feat(routing): 漂移判定、局部重路由、式(3) 滞回与路由版本切换`：19 个文件，+2843 / −37 |
| `1d4c4c7` | `docs: 更新验收记录至第 4 轮（漂移与切换）` |
| `5f04d21` | `feat(tracking): 抽出可替换的追踪策略接口，并预留多智能体强化学习位置`：21 个文件 |
| `e18b996` | `docs: 更新验收记录至第 5 轮（追踪接口与画像面板）` |
| `8f28b1c` | `feat(ui): 观察与路由互跳、决策历史与关联策略展示，并新增交底书对照表`：7 个文件，+236 / −7 |
| `9426040` | `docs: 更新验收记录至第 6 轮（界面收口与对照表）` |
| `4eebadc` | `feat(routing): 实测影子运行的第二会话成本，并把冒烟脚本固化`：8 个文件，+881 / −4 |
| `8ed0bf7` | `docs: 更新验收记录至第 7 轮（影子成本实测）` |
| `d1e7352` | `feat(semantics,routing): 空画像可按设备记录初始化，影子通道可做逐帧对照`：11 个文件，+881 / −4 |
| `f976646` | `docs: 更新验收记录至第 8 轮（画像初始化与影子对照）` |
| `16afacb` | `feat(ui): 任务详情按交底书链路重排为「画面 → 有效观察 → 路由候选 → 事件」`：3 个文件，+143 / −32 |
| `1f68643` | `docs: 更新验收记录至第 9 轮（任务视图按链路重排）` |
| `a13807f` | `feat(ui): 路由页签内的版本时间线`：4 个文件，+166 / −20 |
| `038ec6b` | `docs: 更新验收记录至第 10 轮（版本时间线）` |
| `5c22fc2` | `feat(semantics,routing): 画像版本事件与画像/路由合并时间线`：18 个文件，+1189 / −116 |
| `37afcc9` | `docs: 更新验收记录至第 11 轮（画像事件与合并时间线）` |
| `ee74996` | `feat(semantics,ui): 单条观察记录接口与门禁逐项明细`：7 个文件，+431 / −5 |
| `e3d63b8` | `docs: 更新验收记录至第 12 轮（门禁逐项明细）` |
| `41e6e85` | `feat(ui): 左侧导航按交底书链路分组`：4 个文件，+89 / −9 |
| `7109b8c` | `docs: 更新验收记录至第 13 轮（侧栏按链路分组）` |
| `15dcd30` | `feat(tracking): 外部策略装载位与 MARL 接入契约文档`：7 个文件，+292 / −4 |
| `0804c53` | `docs: 更新验收记录至第 14 轮（外部策略装载与 MARL 契约）` |
| `1eedb60` | `feat(tracking): 策略状态接口回显"实际装载的是什么"`：8 个文件，+302 / −7 |
| `cfa9d18` | `docs: 更新验收记录至第 15 轮（策略状态回显）` |
| `93f3d95` | `docs(tracking): 契约文档同步策略状态接口的 resolved 字段` |
| `2bfb0ba` | `feat(ui): 侧栏当前分组高亮与任务可观察性摘要`：7 个文件，+194 / −8 |
| `7ea78da` | `docs: 更新验收记录至第 16 轮（分组高亮与可观察性摘要）` |
| `6557fef` | `docs: 新增《系统实现》章节初稿，供毕业材料直接引用`：3 个文件，+238 / −2 |
| `11ab175` | `docs: 更新验收记录至第 17 轮（章节初稿）` |
| `364152d` | `feat(routing): 路由评估标明场景证据来自哪一窗、该窗是否有效`：8 个文件，+189 / −6 |

### 第 18 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/routing/service.py` | 修改 | `_latest_metrics` 返回记录本身；输出 `evidence`；无效窗口追加口径提示 |
| `backend/app/modules/routing/schemas.py` | 修改 | 新增 `EvidenceView`、`RouteView.evidence` |
| `backend/app/modules/routing/state.py` | 修改 | 适配新的返回签名（修复解包错误） |
| `frontend/src/modules/agents/RoutePanel.vue` | 修改 | 新增"场景证据来源"一行（有效/无效/无记录三种状态） |
| `tests/backend/test_routing_api.py` | 修改 | 新增 3 项证据来源测试 |
| `frontend/tests/route-panel.test.ts` | 修改 | 新增 2 项 |

### 第 17 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `docs/THESIS_IMPLEMENTATION.md` | 新增 | 九节章节初稿：定位、架构、四条关键设计、数据模型、五组实测数据、质量保证、六条局限、复现步骤、图表建议 |
| `docs/PATENT_MAPPING.md`、`docs/ACCEPTANCE_PATENT.md` | 修改 | 顶部互链到章节初稿 |

### 第 16 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `frontend/src/app/navigation.ts` | 修改 | 新增 `activeGroupLabel(path)`：按最长前缀匹配分组 |
| `frontend/src/app/App.vue`、`style.css` | 修改 | 侧栏组标题按当前路由高亮 |
| `frontend/src/modules/agents/TaskSummaryStrip.vue` | 新增 | 画像版本 / 三态计数 / 当前路由版本与模式的摘要条 |
| `frontend/src/modules/agents/MonitorPanel.vue` | 修改 | 在页签上方挂载摘要条 |
| `frontend/tests/task-summary.test.ts` | 新增 | 4 项：摘要内容、取不到数据、模拟源不请求、前缀匹配 |
| `frontend/tests/observation-panel.test.ts` | 修改 | 断言改为"页签未开时列表不渲染、打开后请求数增加" |

### 第 15 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/tracking/registry.py` | 修改 | `describe_active(spec)`：解析结果缓存、外部策略只构造一次；`forget()` 供测试与重载 |
| `backend/app/modules/tracking/routes.py` | 修改 | `/tracking/policies` 增加 `resolved`（spec/available/name/kind/external/detail/reason），notice 分三种情况 |
| `frontend/src/modules/agents/RoutePanel.vue` | 修改 | 关联策略区块新增"实际装载"一行（可用/不可用两种样式）+ 配置项原文 |
| `tests/backend/test_tracking_status.py` | 新增 | 6 项：默认内置、目录完整、未安装槽位、外部策略、坏 spec、缓存不重复构造 |
| `frontend/tests/route-panel.test.ts`、`agent-tabs.test.ts` | 修改 | 新增 1 项不可用场景；补 `resolved` 字段 |

### 第 14 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/tracking/registry.py` | 修改 | `create()` 支持 `module:attribute` 外部装载；协议校验与四种失败错误码 |
| `backend/app/shared/config.py` | 修改 | 新增 `tracker_policy`（默认 `heuristic-iou`） |
| `backend/app/modules/local_execution/intrusion.py` | 修改 | `IntrusionRule` 增加 `policy_name`，默认值不变 |
| `backend/app/modules/local_execution/service.py` | 修改 | 把配置里的策略名传给入侵规则 |
| `docs/MARL_TRACKING_CONTRACT.md` | 新增 | 九节接入契约（边界、契约、示例、装载、训练建议、指标、验收、衔接、红线） |
| `.env.example` | 修改 | 增加 `VISION_TRACKER_POLICY` |
| `tests/backend/test_tracker_plugin.py` | 新增 | 7 项装载与协议校验测试 |

### 第 13 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `frontend/src/app/navigation.ts` | 修改 | 新增 `navigationGroups` 四组（含流程段说明与每条 hint）；`navigation` 改为分组的扁平视图；`permittedRoutes` 未改 |
| `frontend/src/app/App.vue` | 修改 | 侧栏按组渲染；移除"稍后接入"禁用分支与 NTooltip 依赖 |
| `frontend/src/app/style.css` | 修改 | 新增 `.nav-group` 组标题样式 |
| `frontend/tests/navigation.test.ts` | 新增 | 5 项：分组顺序、流程段说明、入口完整性、路由校验、图标与提示 |

### 第 12 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/semantics/service.py`、`routes.py` | 修改 | `GET /agents/{id}/observations/{observation_id}`（404 = `observation_not_found`） |
| `frontend/src/modules/agents/ObservationPanel.vue` | 修改 | 每行"门禁"按钮 + 明细区：逐门禁表、实测指标、三类版本、路径；门禁与原因代码中文化 |
| `frontend/tests/observation-panel.test.ts` | 修改 | 新增 1 项：打开明细、通过/未测定状态、未测定指标、版本行与关闭 |
| `tests/backend/test_semantics_api.py` | 修改 | 新增 1 项：单条记录字段完整性 + 404 错误码 |

### 第 11 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/semantics/models.py` | 修改 | 新增 `profile_events`（追加式版本事件） |
| `backend/alembic/versions/0011_profile_events.py` | 新增 | 纯新增迁移 |
| `backend/app/modules/semantics/service.py` | 修改 | 三个写入口各追加一条事件；修正属性事件 previous 的读取顺序 |
| `backend/app/modules/semantics/routes.py`、`schemas.py` | 修改 | `GET /sources/{id}/semantic-profile/events` 与 `ProfileEventView` |
| `backend/app/modules/routing/state.py`、`routes.py`、`schemas.py` | 修改 | `GET /agents/{id}/routing/timeline`：合并画像事件与路由决策，按时间倒序 |
| `frontend/src/modules/agents/RouteTimeline.vue` | 修改 | 消费合并条目，来源徽标 + 同来源版本变更才标绿 |
| `frontend/src/modules/agents/RoutePanel.vue`、`api.ts` | 修改 | 改取 timeline 接口 |
| `tests/backend/test_profile_events.py` | 新增 | 6 项 |
| `frontend/tests/route-timeline.test.ts`、`route-panel.test.ts` | 修改 | 改为合并条目形状 |

### 第 10 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `frontend/src/modules/agents/RouteTimeline.vue` | 新增 | 从旧到新的决策时间线；改变路由版本的节点用绿点标出，并展开属性变化/受影响子图/候选 |
| `frontend/src/modules/agents/RoutePanel.vue` | 修改 | 用时间线替换"最近路由决策"列表，删除失效的映射与样式 |
| `frontend/tests/route-timeline.test.ts` | 新增 | 4 项：排序与版本变更标记、漂移行、候选与 ΔJ、空态 |
| `frontend/tests/route-panel.test.ts` | 修改 | 选择器改为 `aria-label="路由版本时间线"` |

### 第 9 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `frontend/src/modules/agents/MonitorPanel.vue` | 修改 | 任务详情改为四个页签：画面 / 有效观察 / 路由候选 / 事件；模拟数据源只保留画面与事件；切页签卸载旧面板 |
| `frontend/tests/agent-tabs.test.ts` | 新增 | 4 项：页签顺序与选中态、事件页非紧凑、切页签卸载旧面板、模拟源只有两个页签 |
| `frontend/tests/observation-panel.test.ts` | 修改 | 关闭方式由"再点一次"改为"切到画面页签" |

### 第 8 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/semantics/bootstrap.py` | 新增 | 首次运行画像初始化：固有层取设备字段（不含地址凭据），动态层仅在拿到一帧时写入一项保守 `lighting` |
| `backend/app/modules/routing/shadow.py` | 新增 | 同一批帧喂给两个会话并逐帧比对（完全相同帧数 / IoU 匹配帧数 / 平均 IoU / 双方检测数与时延） |
| `backend/app/modules/semantics/routes.py`、`schemas.py` | 修改 | `POST /sources/{id}/semantic-profile/bootstrap` 与 `BootstrapView` |
| `deploy/scripts/shadow_compare.py` | 新增 | 影子对照 CLI（可用 `--video` 指定本地录像，缺省用确定性合成帧） |
| `frontend/src/modules/sources/ProfilePanel.vue`、`profileApi.ts` | 修改 | "按设备记录初始化"按钮与结果列表 |
| `tests/backend/test_bootstrap_shadow.py` | 新增 | 10 项：固有层不含凭据、亮度分档、幂等不覆盖、影子确定性、空帧被拒等 |
| `frontend/tests/profile-panel.test.ts` | 修改 | 新增初始化按钮 1 项 |

### 第 6 轮改动

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `docs/PATENT_MAPPING.md` | 新增 | 一页式对照表：M1–M9、S1–S14、式(1)(2)(3)、F1–F5 的落点与证据，5 张表 / 12 个接口 / 3 个界面落点，5 步演示脚本，未实现清单 |
| `frontend/src/modules/agents/ObservationPanel.vue` | 修改 | 增加"路由版本"列与逐行"路由"入口 |
| `frontend/src/modules/agents/RoutePanel.vue` | 修改 | 新增"最近路由决策"与"关联策略"两段只读信息；标题带视频源名 |
| `frontend/src/modules/agents/api.ts` | 修改 | `trackerPolicies()` 与类型 |
| `frontend/src/modules/agents/MonitorPanel.vue` | 修改 | 承接 `openRoute` 事件，把观察面板与路由面板连起来 |
| `frontend/tests/observation-panel.test.ts`、`route-panel.test.ts` | 修改 | 新增 3 项测试 |

### 第 5 轮新增/修改文件

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/tracking/policy.py` | 新增 | 观测/动作/轨迹契约与 `TrackerPolicy` 协议 |
| `backend/app/modules/tracking/runtime.py` | 新增 | `TrackerRuntime`：轨迹状态归框架，策略只提交 `Decision` |
| `backend/app/modules/tracking/heuristic.py` | 新增 | 启发式关联策略（原规则内实现的搬出，作为学习型基线） |
| `backend/app/modules/tracking/registry.py` | 新增 | 策略注册表：已安装/未安装如实标注，未安装不可创建 |
| `backend/app/modules/tracking/routes.py` | 新增 | `GET /tracking/policies` |
| `backend/app/modules/local_execution/intrusion.py` | 修改 | 规则改用 `TrackerRuntime` 适配器，状态机一行未改 |
| `backend/app/main.py` | 修改 | 注册 tracking 路由 |
| `frontend/src/modules/sources/profileApi.ts` | 新增 | 画像读写封装 |
| `frontend/src/modules/sources/ProfilePanel.vue` | 新增 | 固有层编辑 + 动态属性表格 + 写入/删除 |
| `frontend/src/modules/sources/SourcesPage.vue` | 修改 | 视频源详情下方挂载画像面板 |
| `tests/backend/test_tracking_policy.py` | 新增 | 策略契约 8 项（含 120 步随机序列等价性） |
| `frontend/tests/profile-panel.test.ts` | 新增 | 画像面板 5 项 |
| `contracts/openapi.json`、`generated.ts` | 重新生成 | 同步 `/tracking/policies` |

### 第 4 轮新增/修改文件

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/routing/drift.py` | 新增 | 漂移判定：只有游标之后的新证据 + 标签变化才算确认；过期只报 expired |
| `backend/app/modules/routing/hysteresis.py` | 新增 | 式(3) 状态机：进入/取消阈值、最短驻留、有效窗口计数、硬失效旁路 |
| `backend/app/modules/routing/models.py` | 新增 | `route_states`（当前组合与候选）与 `route_decisions`（决策审计） |
| `backend/app/modules/routing/state.py` | 新增 | 把漂移、局部重路由、评价与滞回接成一条链，并落库审计 |
| `backend/app/modules/routing/solver.py` | 修改 | 新增 `solve_local`：只重路由受影响子图，必要时退化为全图重算 |
| `backend/app/modules/routing/routes.py` | 修改 | 路由状态、决策审计、提议与取消四个接口 |
| `backend/app/modules/routing/schemas.py` | 修改 | `RouteStateView`、`RouteDecisionView`、`DriftView`、`ProposeInput`、`CancelInput` |
| `backend/alembic/versions/0010_route_state.py` | 新增 | 纯新增迁移，回滚只删两张新表 |
| `backend/app/modules/local_execution/service.py` | 修改 | 运行开始读路由版本、窗口按该版本盖章、每窗口喂状态机一步、失败隔离 |
| `frontend/src/modules/agents/RoutePanel.vue` | 修改 | 路由状态区块：版本/成员/候选/窗口进度/漂移/受影响子图 + 提议与取消按钮 |
| `frontend/src/modules/agents/api.ts` | 修改 | 路由状态、决策、提议、取消四个调用 |
| `tests/backend/test_drift_hysteresis.py` | 新增 | 漂移与滞回 19 项测试 |
| `tests/backend/test_routing_state.py` | 新增 | 状态机 12 项测试 |
| `frontend/tests/route-panel.test.ts` | 修改 | 新增路由状态与提议 2 项测试 |
| `contracts/openapi.json`、`generated.ts` | 重新生成 | 同步新接口 |

### 第 3 轮新增/修改文件

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/routing/graph.py` | 新增 | 需求节点、四类依赖边、可执行性校验与拓扑序、属性反向索引 |
| `backend/app/modules/routing/capability.py` | 新增 | 能力表（观察前提/分桶质量/资源/冲突/安装与标定状态）与场景分桶推导 |
| `backend/app/modules/routing/solver.py` | 新增 | 式(2) 评分、硬约束过滤、可修复性判定、候选枚举与穷举求解 |
| `backend/app/modules/routing/service.py` | 新增 | 画像 + 最近观察记录 → 一次路由评估 |
| `backend/app/modules/routing/routes.py` | 新增 | `GET /sources/{id}/routes` |
| `backend/app/modules/routing/schemas.py` | 新增 | 路由响应契约 |
| `frontend/src/modules/agents/RoutePanel.vue` | 新增 | 路由候选面板（选择/评分分项/可行/被排除/口径提示） |
| `frontend/src/modules/agents/MonitorPanel.vue` | 修改 | "路由候选"入口，按任务绑定的视频源与规则取数 |
| `frontend/src/modules/agents/api.ts` | 修改 | `routes()` 与相关类型 |
| `tests/backend/test_requirement_graph.py` | 新增 | 需求图 7 项测试 |
| `tests/backend/test_route_solver.py` | 新增 | 求解器 12 项测试（含交底书实施例一复现） |
| `tests/backend/test_routing_api.py` | 新增 | 路由接口 6 项测试 |
| `frontend/tests/route-panel.test.ts` | 新增 | 面板 3 项测试 |
| `backend/app/main.py` | 修改 | 注册 routing 路由 |
| `contracts/openapi.json`、`generated.ts` | 重新生成 | 新增 506 / 241 行，无重排 |

### 第 2 轮新增/修改文件

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/app/modules/semantics/window.py` | 新增 | 观察窗口聚合（帧率/最大间隔/最差画面质量/命中计数） |
| `backend/app/modules/local_execution/service.py` | 修改 | 每帧入窗、采样点测质量、窗口闭合落盘、失败隔离 |
| `backend/app/modules/semantics/metrics.py` | 修改 | `measure_regions` 与 `combine`（多区域取最差） |
| `backend/app/modules/semantics/observe.py` | 修改 | `time_continuous` 门禁与"帧时间不连续"原因 |
| `backend/app/modules/semantics/schemas.py` | 修改 | `ObservationMetrics.time_continuous` |
| `backend/app/modules/semantics/service.py` | 修改 | 门槛默认值、`thresholds_for`、`profile_version_for` |
| `backend/app/shared/config.py` | 修改 | `observation_records`、`observation_window_seconds` |
| `backend/app/modules/agents/contracts.py` | 修改 | `RunDTO.profile_version`、`RunDTO.route_version` |
| `frontend/src/modules/agents/ObservationPanel.vue` | 新增 | 有效观察面板（三态/窗口/帧率/过曝/原因/统计/筛选） |
| `frontend/src/modules/agents/MonitorPanel.vue` | 修改 | "有效观察"入口，仅真实数据源可用 |
| `frontend/src/modules/agents/api.ts` | 修改 | `observations()` 与相关类型 |
| `frontend/tests/observation-panel.test.ts` | 新增 | 面板与入口的 3 项测试 |
| `tests/backend/test_observation_window.py` | 新增 | 窗口聚合 8 项测试 |
| `tests/backend/test_executor_observation.py` | 新增 | 真实执行器 4 项测试（含"报警不变""记录失败不打断监测"） |
| `.env.example` | 修改 | 两个新增环境变量说明 |

## 三、第 1 轮新增文件

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `backend/app/modules/semantics/models.py` | 64 | 三张新表：`semantic_profiles`、`profile_attributes`、`observation_records` |
| `backend/app/modules/semantics/profile.py` | 70 | 式(1) 衰减、状态语义（valid/expired/unknown/conflict）、可用性筛选 |
| `backend/app/modules/semantics/metrics.py` | 128 | 画面指标：ROI 几何裁剪、过曝、亮度、清晰度、帧率与最大间隔 |
| `backend/app/modules/semantics/observe.py` | 134 | 五道门禁与三态结论 |
| `backend/app/modules/semantics/schemas.py` | 173 | 请求/响应契约（`extra='forbid'`、数值范围校验） |
| `backend/app/modules/semantics/service.py` | 249 | 画像读写、属性 upsert、观察记录落盘与游标分页 |
| `backend/app/modules/semantics/routes.py` | 52 | 6 个接口 |
| `backend/alembic/versions/0009_semantic_observation.py` | 68 | 纯新增迁移，回滚只删新表 |
| `deploy/scripts/semantics_smoke.py` | 125 | 对运行中的应用做真实冒烟 |
| `tests/backend/test_semantic_profile.py` | 82 | 式(1) 与状态语义 |
| `tests/backend/test_observation_gate.py` | 114 | 五门禁逐项与三态 |
| `tests/backend/test_semantics_api.py` | 154 | 接口契约、版本自证防护、游标与筛选 |

修改：`backend/app/main.py`（注册路由）、`contracts/openapi.json`、`frontend/src/shared/api/generated.ts`、`tests/backend/test_agents.py` 与 `test_agent_workspace_migration.py`（迁移头部断言由 0008 改为 0009）。

## 四、数据库变更

新增三张表，不改动任何既有表：

- `semantic_profiles`：`(source_id, view_version)` 唯一；`intrinsic` 固有层、`runtime` 运行层、`version` 版本。
- `profile_attributes`：`(profile_id, key)` 唯一；每项带 `source_kind`、`source_frame_ts`、`roi`、`observed_at`、`confidence`、`tau_seconds`、`hard_expiry_at`、`state`、`version`。
- `observation_records`：自增 `sequence` 供分页；绑定 `agent_id/run_id/source_id/task_key/roi/window_start/window_end/route_version/profile_version/model_version`；存 `metrics`、`thresholds`、`gates`、`reasons`、`verdict`。

`var/vision.db` 已升级到 `alembic_version=0009_semantic_observation`，三张表实际存在。

## 五、新增接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/sources/{source_id}/semantic-profile?at=` | 读取分层画像，按 `at` 计算各项当前强度 |
| PUT | `/api/v1/sources/{source_id}/semantic-profile` | 写入固有层（键白名单校验），版本递增 |
| PUT | `/api/v1/sources/{source_id}/semantic-profile/attributes/{key}` | 写入/刷新一项动态属性 |
| DELETE | `/api/v1/sources/{source_id}/semantic-profile/attributes/{key}` | 删除一项属性 |
| POST | `/api/v1/agents/{agent_id}/observations` | 提交一次窗口观察，返回三态结论 |
| GET | `/api/v1/agents/{agent_id}/observations` | 观察记录列表，支持按视频源/结论/运行/任务筛选与游标分页 |

响应示例（已在小节七实测）：

```json
{
  "source_id": "1c53f839-…",
  "view_version": "v1",
  "version": 3,
  "intrinsic": {"resolution": "960x540"},
  "runtime": {},
  "attributes": [{"key": "lighting", "state": "valid", "strength": 0.786721,
                  "usable": true, "source_kind": "frame", "source_frame_ts": 3.5}],
  "evaluated_at": 1794912684.7
}
```

## 六、语义规则（答辩时可直接讲的三条）

**1. 属性会过期，过期只变成"未知"（式 1）**

`r_a(t) = q_a · exp(−(t − t_a)/τ_a) · I(t_a ≤ t < T_a)`

- 观测时刻在未来的记录直接拒绝，不钳制：错误的时钟不能悄悄变成新鲜证据。
- 到达硬失效时刻 `T_a` 后强度置 0、状态 `expired`，对外只表示"不再知道"，**不得解释为相反事实成立**。
- 语言推断与画面实测冲突时保留 `conflict` 态且不可用，不静默取其一。

**2. 五道门禁决定"这次结果能不能算数"**

帧时间（帧数、实际帧率、最大帧间隔、窗口长度）、ROI 覆盖、画面质量（过曝、清晰度、遮挡、最小可辨目标尺度）、路径完整、版本一致。

**3. 三态输出，且"未检出"比"检测到"要求更严**

- 任一门禁不通过 → `insufficient`（观察不足），附原因，不得用于删除属性、撤销任务或证明事件不存在。
- 全通过且有目标 → `detected`。
- 全通过且为空 → `not_detected`，只在本次窗口与 ROI 内成立，不外推。
- 关键设计：某门槛**未测定**时只阻止 `not_detected`，不阻止 `detected`。空结果必须有完整证据，这是"难以观察"与"没有事件"的分界线。

未检出的作用域由 `observe.conclusion_scope()` 显式返回，含文案"仅在本次窗口与监测区域内未检出，不外推到其他时段或区域"。

## 七、验证证据（本机实测）

环境：Python 3.13.15（项目 `.venv`）、Node 24.19.0、Windows x64、CPU 推理。

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
394 passed in 201.90s
```

```
$ cd frontend && npm test
Test Files  32 passed (32)
     Tests  158 passed (158)
```

```
$ cd frontend && npm run build
vue-tsc --noEmit 通过；✓ built in 10.76s
```

```
$ .venv\Scripts\python.exe -m unittest discover -s tests/deploy
Ran 12 tests
OK
```

迁移与真实应用冒烟：

```
alembic version: [('0009_semantic_observation',)]
semantic_profiles exists / profile_attributes exists / observation_records exists

$ .venv\Scripts\python.exe deploy\scripts\semantics_smoke.py
camera: 模拟摄像头—夜间街道（录像循环） | task: 人员在岗监测任务
[1] 画像可读且不臆造属性            ok   画像结构完整（当前版本 4）
[2] 固有层写入使版本递增            ok   版本 4 -> 5
[3] 动态属性必须带来源、时刻与有效期 ok   属性有效并可用于路由
                                   ok   到期后转为未知，不转成相反事实
[4] 三态结论                       ok   detection_count=2 -> detected
                                   ok   detection_count=0 -> not_detected
                                   ok   过曝 0.62      -> insufficient
                                   ok   清晰度未测定    -> insufficient
[5] 观察记录可筛选与分页             ok   分页游标可用
                                   ok   按结论筛选生效
全部通过
```

新增测试的 31 项覆盖：衰减公式与边界、未来时刻拒绝、非有限值、零置信度、冲突态、可用性筛选、变化检测；五道门禁逐项单独触发、未测定只阻止未检出、无解码帧无结论、执行路径与版本不一致、协议有效空集合法；接口层的版本自证防护（画像版本由服务端掌握，窗口不能自报）、游标防篡改、筛选与分页、未知视频源/任务返回 404 而不是新建。

### 第 2 轮（执行器接入）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
406 passed in 191.48s        # 第 1 轮 394 项 + 本轮 12 项，旧用例零回归

$ cd frontend && npm test
Test Files  33 passed (33)
     Tests  161 passed (161)   # 第 1 轮 158 项 + 本轮 3 项

$ cd frontend && npm run build
✓ built in 9.77s               # vue-tsc 无错误
```

真实执行器验证（运行中的应用 + 真实 RTSP 摄像头，任务连续跑 75 秒）：

```
task: 人员在岗监测任务 | revision: v1 (published) | rule: absence
start: 202 running
observations: 200 items 20 summary {'detected': 8, 'insufficient': 9, 'not_detected': 4}
  1108948.05-1108978.97s detected      route=local-r1 profile=8 fps=8.31 glare=0.0 frames=257 reasons=[]
  1108947.84-1108978.04s detected      route=local-r1 profile=None fps=8.25 glare=0.0 frames=249 reasons=[]
  1108917.95-1108948.05s detected      route=local-r1 profile=8 fps=9.17 glare=0.0 frames=276 reasons=[]
profile runtime: {"observation":{"verdict":"detected","window_end":1108978.97,"reasons":[],"route_version":"local-r1"}}
```

要点：帧率、帧数、过曝比例全部来自实际解码帧；`profile=None` 的那一路视频源
本身还没有画像，如实记录为无版本而不是借用另一路；画像运行层被回写为最近一次
结论与路由版本。同一任务的两路视频源各写各的记录，互不干扰。

执行器侧 4 项测试（`test_executor_observation.py`）用真实 `LocalAgentServices`
与 numpy 帧验证：

| 场景 | 期望 | 结果 |
| --- | --- | --- |
| 正常纹理帧 + 无人 | 每条记录 `not_detected`，缺岗事件照旧产生 | 通过 |
| 检测到人 | 每条记录 `detected`，且记录下目标像素高度 | 通过 |
| 全饱和白帧 | 每条记录 `insufficient` 且原因是过曝；报警逻辑不变 | 通过 |
| 记录写入抛异常 | 监测仍 `completed`，事件照旧，不产生记录 | 通过 |

### 第 3 轮（路由评估）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
431 passed in 192.01s        # 第 2 轮 406 项 + 本轮 25 项，旧用例零回归

$ cd frontend && npm test
Test Files  34 passed (34)
     Tests  164 passed (164)   # 第 2 轮 161 项 + 本轮 3 项

$ cd frontend && npm run build
✓ built in 9.52s               # vue-tsc 无错误
```

**复现交底书实施例一**（`test_scores_reproduce_the_worked_example_in_the_patent`）：
用该实施例的离线能力示例值构造三个候选组合，按 α=1、β=0.2、γ=0.3、δ=0.2 计算

| 候选组合 | 覆盖 C | 依赖 H | 资源 R | 综合评分 J | 是否通过 0.80 质量门槛 |
| --- | --- | --- | --- | --- | --- |
| 通用检测+通用跟踪 | 0.685 | 0.05 | 0.200 | **0.675** | 否 |
| 雪地检测+跟踪+去眩光 | 0.890 | 0.12 | 0.350 | **0.905** | 是 |
| 通用多任务模型 | 0.770 | 0 | 0.150 | **0.725** | 否 |

三个数字与交底书完全一致，说明式(2) 的实现与文档口径相同，不是另起的公式。

真实应用验证（运行中的应用 + 真实摄像头 + 真实观察记录）：

```
[夜间街道] 分桶=default 目标尺度=83.1 画像版本=8
  chosen: YOLO11n COCO 人员检测（CPU ONNX） score=1.6225 C/H/R=0.72/1.0/0.325
  可行 1 条 / 排除 7 条
    排除：中心区域裁剪放大（未安装）+ 去眩光预处理（未安装）+ YOLO11n -> 未安装：…
[行人广场] 分桶=default 目标尺度=132.4 画像版本=0
  chosen: 同上
入侵规则：person_detect -[serial]-> person_track -[temporal]-> zone_intersect
  chosen: 跟踪 + 检测 + 区域规则  score=1.6341
```

写入一条 `strong_glare` 属性后的行为（测试后已删除该属性）：

```
分桶: glare | chosen: 无
  - 中心区域裁剪放大（未安装）+ YOLO11n => 未安装：…；不在适用场景分桶：glare；
    低于必需质量：person_detect 0.45 < 0.60
放宽质量门槛（min_quality=0）：chosen=YOLO11n，score 降到 1.3525，分桶=glare
删除属性后：分桶恢复 default，score 回到 1.6225
```

要点：目标尺度 83 像素与 132 像素来自**真实观察记录**而不是配置值；眩光场景下
系统不是"随便选一个"，而是明确报告"没有可行组合"并列出每条原因——这正是交底书
F3 与 M6 想要的行为：宁可不选，也不假装能看。

### 第 4 轮（漂移与切换）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
461 passed in 199.73s        # 第 3 轮 431 项 + 本轮 30 项，旧用例零回归

$ cd frontend && npm test
Test Files  34 passed (34)
     Tests  166 passed (166)   # 第 3 轮 164 项 + 本轮 2 项

$ cd frontend && npm run build
✓ built in 9.72s
```

本轮的关键断言（全部在单元测试里，可逐条复核）：

| 断言 | 测试 |
| --- | --- |
| 只有游标之后的新证据且标签变化才算确认漂移 | `test_new_evidence_with_a_different_label_confirms_drift` |
| 旧证据不产生新闻 | `test_evidence_older_than_the_cursor_carries_no_news` |
| 过期只报 expired，理由是"补充抽帧" | `test_expiry_is_reported_as_needing_new_frames_not_as_a_reversed_scene` |
| 首次观测是基线不是漂移 | `test_first_observation_is_a_baseline_not_a_drift` |
| 进入候选需同时满足增益与最短驻留 | `test_entry_needs_both_the_gain_threshold_and_the_dwell_time` |
| 增益回落取消候选 | `test_a_falling_gain_cancels_the_candidate` |
| 切换需累计规定数量的有效窗口 | `test_switching_requires_the_configured_number_of_valid_windows` |
| 无效窗口不计数 | `test_an_insufficient_window_does_not_count_towards_the_switch` |
| 硬失效绕过收益等待但仍等一个窗口 | `test_a_hard_failure_bypasses_the_gain_wait_but_still_waits_one_window` |
| 光照漂移只重路由检测节点 | `test_lighting_drift_only_reroutes_the_detector` |
| 遮挡漂移扩到检测+跟踪但保留区域规则 | `test_occlusion_drift_widens_to_detection_and_tracking_but_keeps_the_zone_rule` |
| 单需求图退化为全图重算 | `test_a_single_requirement_graph_escalates_to_a_full_solve` |
| 没有可行替代时保持原样并说明 | `test_a_hard_failure_without_an_alternative_stays_put_and_says_so` |

真实应用验证（真实画像 + 真实观察记录，清空路由表后重放）：

```
--- 1) 建立基线 ---
propose: 版本=route-v1 模式=stable 当前=['yolo11n-person'] 候选=None ΔJ=0.0
   漂移 lighting: None -> daylight (baseline)

--- 2) 同一场景再次提议（无漂移） ---
propose: 版本=route-v1 模式=stable 当前=['yolo11n-person'] ΔJ=0.0

--- 3) 新帧确认眩光 → 没有可行替代 ---
propose: 版本=route-v1 模式=stable ΔJ=None
   漂移 lighting: daylight -> strong_glare (confirmed)
   说明：无法局部修复，已退化为全图重算：漂移覆盖全部需求

--- 4) 恢复常规场景 ---
propose: 版本=route-v1 模式=stable ΔJ=0.0
   漂移 lighting: strong_glare -> daylight (confirmed)

--- 5) 决策审计 ---
   [drift   ] hold    当前组合仍处于最短驻留时间（0/120 秒）
   [blocked ] hold    没有可行组合：当前组合失效时保持原状，观察记录输出观察不足
   [refresh ] hold    当前组合仍处于最短驻留时间（0/120 秒）
   [baseline] hold    当前组合仍处于最短驻留时间（0/120 秒）
```

要点：眩光被**确认为漂移**，但因为没有任何已安装的替代能力，系统记录 `blocked`
并保持原组合——不制造虚假切换；恢复后确实记了一条 `drift`，却因最短驻留时间
未到而 `hold`，这正是式(3) 的作用：不该动的就不动。

### 第 5 轮（追踪接口与画像面板）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
469 passed in 198.17s        # 第 4 轮 461 项 + 本轮 8 项，旧用例零回归

$ cd frontend && npm test
Test Files  35 passed (35)
     Tests  171 passed (171)   # 第 4 轮 166 项 + 本轮 5 项

$ cd frontend && npm run build
✓ built in 9.58s
```

本轮最关键的一条证据：**把追踪器换成策略之后，规则行为零变化**。
`test_the_policy_runtime_reproduces_the_previous_tracker_exactly` 在一个
120 步随机序列上（随机帧间隔 0.2–6 秒、随机 0–3 个目标）逐帧比对旧实现与
新运行时的输出（轨迹 id 与框），完全一致；既有 41 项入侵与执行器用例也全绿。

其余断言：

| 断言 | 测试 |
| --- | --- |
| 启发式策略满足 `TrackerPolicy` 协议 | `test_the_heuristic_policy_is_a_member_of_the_protocol` |
| 未安装的 MARL 策略无法被创建（503） | `test_enrolment_of_a_learned_policy_is_refused_while_it_is_not_installed` |
| 注册表如实列出"已声明未安装"及其前提 | `test_the_registry_states_plainly_what_is_missing` |
| 非法检测在入口处被丢弃 | `test_the_observation_contract_drops_invalid_detections_at_the_boundary` |
| 策略提交的非法关联被框架忽略 | `test_a_policy_only_proposes_and_the_framework_owns_the_tracks` |
| 策略涂改视图不会污染框架状态 | `test_a_policy_cannot_mutate_its_way_into_the_track_table` |

真实应用验证：

```
GET /api/v1/tracking/policies
active=heuristic-iou
name              kind       installed  calibrated
heuristic-iou     heuristic     True       True
marl-association  learned       False      False
notice: 关联策略可替换；多智能体强化学习策略尚未安装，本机仍使用固定机位 IoU/中心距关联。
```

### 第 6 轮（界面收口与对照表）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
469 passed in 197.33s        # 本轮无后端逻辑改动，回归确认

$ cd frontend && npm test
Test Files  35 passed (35)
     Tests  174 passed (174)   # 第 5 轮 171 项 + 本轮 3 项

$ cd frontend && npm run build
✓ built in 9.60s

产物核对：dist/AgentDetailPage 含"关联策略""最近路由决策""查看该视频源的路由"，
dist/SourcesPage 含"时效语义画像"；运行中的应用返回 200。
```

本轮交付的重点是**文档**：`docs/PATENT_MAPPING.md` 把交底书的 M1–M9、S1–S14、
式(1)(2)(3)、F1–F5 逐条对到代码位置、关键测试与状态，并附一份 5 步演示脚本，
答辩时可以直接照着走。

### 第 7 轮（影子成本实测与脚本固化）补充证据

交底书 S14 一直有个说不清的地方：**多开一份推理会话到底要多少资源？** 本轮实测：

```
$ .venv\Scripts\python.exe deploy\scripts\preheat_measure.py --frames 10   # 跑两次
                       第 1 次        第 2 次
第二个会话边际内存      85.0 MB        84.4 MB
两个会话总增量         181.2 MB       181.1 MB
会话加载时间           94.5 ms        86.3 ms
基线单帧耗时           64.07 ms       63.21 ms
影子单帧耗时           63.21 ms       65.25 ms
逐帧延迟差             −0.87 ms       +2.04 ms
预算判定（1024MB/200ms） 可容纳        可容纳
```

结论（论文可直接引用，需注明环境）：**在本机（Windows x64 / CPU / 应用同时运行）
条件下，并存第二份 YOLO11n 会话的代价约为 +85 MB 常驻内存、约 90 毫秒加载时间，
逐帧延迟差异落在噪声量级（±2 毫秒）；相对默认过渡预算（1024 MB / 200 毫秒）是可容纳的。**

这解决了"S14 的影子运行到底可不可行"的一部分疑问：**资源上可行**。仍未解决的是
"候选模型与当前模型不同"的情形——本机只有一份可信 ONNX，两次加载的是同一模型，
因此只能证明并存成本，不能证明"换模型会更准"。

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
474 passed in 212.18s        # 第 6 轮 469 项 + 本轮 5 项，旧用例零回归

$ cd frontend && npm test
Test Files  35 passed (35)
     Tests  174 passed (174)

$ cd frontend && npm run build
✓ built in 10.70s

$ .venv\Scripts\python.exe deploy\scripts\routing_smoke.py
task: 人员在岗监测任务 | channel: 4709f75c… | source: 4a959e34…
[1] 建立基线        → route-v1 stable ['yolo11n-person'] 漂移 lighting: None -> daylight
[3] 眩光确认        → 漂移 daylight -> strong_glare（confirmed），保持 stable
[5] 决策审计        → 建立基线 / 无漂移刷新 / 无可行组合 / 确认漂移 四条记录齐全
全部通过
```

本轮还把两个演示脚本固化进仓库，答辩现场一条命令即可复现：

| 脚本 | 用途 |
| --- | --- |
| `deploy/scripts/semantics_smoke.py` | 画像版本递增、到期转未知、三态判定、游标与筛选 |
| `deploy/scripts/routing_smoke.py` | 基线 → 刷新 → 眩光被阻塞 → 恢复 → 决策审计 → 状态 |
| `deploy/scripts/preheat_measure.py` | 影子运行的会话并存成本实测 |

### 第 8 轮（画像初始化与影子对照）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
484 passed in 202.38s        # 第 7 轮 474 项 + 本轮 10 项，旧用例零回归

$ cd frontend && npm test
Test Files  35 passed (35)
     Tests  175 passed (175)   # 第 7 轮 174 项 + 本轮 1 项

$ cd frontend && npm run build
✓ built in 9.66s
```

**影子通道的逐帧对照**（`deploy/scripts/shadow_compare.py`，用 `plaza.mp4` 均匀取 6 帧）：

```
available=True  mode=file  frames=6  identical_artifact=True
exact_frames=6  iou_frames=6  mean_iou=1.0
detections_a=33  detections_b=33
latency_a_ms=70.94  latency_b_ms=69.28
```

结论：同一份产物下的影子通道**逐帧完全一致**（6/6 帧、33 个目标全对、平均 IoU 1.0），
两次推理时延几乎相同。这证明了影子通道的确定性与代价，**不证明跨模型更准**。

**空画像初始化**（真实应用的两个视频源）：

```
录像源 bootstrap：
  created: 固有层 device_id=… | 固有层 stream=file | 固有层 resolution=640x480
           | 动态层 lighting=daylight（单帧置信度 0.5，1800 秒后失效）
  画像版本 2 → 属性 lighting / valid / strength≈0.50 / confidence 0.5

摄像头源 bootstrap：
  created: 固有层 device_id=… | 固有层 stream=camera
  notices: 摄像头源不做首帧取图，动态层需由运行中的观察或人工写入。
           没有可用画面帧，动态层保持为空：亮度类属性必须由实测画面写入。
```

要点：初始化**只填缺项**（第二次调用 created 为空），固有层**不含地址与凭据**
（有测试断言 secret 与内网 IP 不出现），动态层只写一项**置信度 0.5** 的亮度属性，
并在 1800 秒后自动转为"未知"——避免一次初始化就把"白天"当成长期事实。

### 第 9 轮（任务视图按链路重排）补充证据

```
$ cd frontend && npm test
Test Files  36 passed (36)
     Tests  179 passed (179)   # 第 8 轮 175 项 + 本轮 4 项

$ cd frontend && npm run build
✓ built in 9.66s
```

页签顺序与后端语义的对应关系（可直接放进论文的系统截图说明）：

| 页签 | 对应交底书 | 内容 |
| --- | --- | --- |
| 画面 | S1–S6（接入与采集） | 监控墙/单画面、播放器、通道卡片、失败运行、模型防护开关、紧凑事件 |
| 有效观察 | S7–S9（五门禁与三态） | 三态徽标、帧窗口、实测帧率、过曝比例、**路由版本**、失效原因、结论统计与筛选 |
| 路由候选 | M6 + S13（组合与门禁） | 当前路由版本与成员、候选与增益、有效窗口进度、漂移与受影响子图、可行/被排除候选、最近决策、关联策略 |
| 事件 | 结果输出 | 完整事件列表（画面页只是紧凑侧栏） |

两处刻意的取舍：**模拟数据源只显示「画面」「事件」两个页签**（延续"不把模拟当真实"）；
**从观察记录点"路由"会切换页签**，而不是弹出浮层，保证"证据→组合"的路径是连贯的。

### 第 10 轮（版本时间线）补充证据

```
$ cd frontend && npm test
Test Files  37 passed (37)
     Tests  183 passed (183)   # 第 9 轮 179 项 + 本轮 4 项

$ cd frontend && npm run build
✓ built in 10.81s
```

时间线的四个要点（对应 F5「切换前后结果按版本隔离」的界面表达）：

| 要点 | 表现 |
| --- | --- |
| 顺序 | 从旧到新，与阅读方向一致 |
| 版本变更 | 该节点绿点 + 光晕，一眼看出"哪一次决策真的换了版本" |
| 依据 | 展开该次决策的属性变化（旧 → 新）与受影响子图 |
| 动作 | 保持 / 进入候选 / 取消候选 / 切换版本 + 种类（基线/刷新/漂移/过期/阻塞/人工取消/观察窗口） |

真实数据核对（运行中的应用，`/routing/decisions`）：每条记录带 `kind`、`action`、
`reason`、`delta_j`、`route_version`、`created_at` 与 `payload.drift/affected/candidate`，
时间线所需的字段齐全，无需新增接口。

### 第 11 轮（画像版本事件与合并时间线）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
490 passed in 270.34s        # 第 10 轮 484 项 + 本轮 6 项，旧用例零回归

$ cd frontend && npm test
Test Files  37 passed (37)
     Tests  183 passed (183)

$ cd frontend && npm run build
✓ built in 10.85s

alembic_version = 0011_profile_events（profile_events 表已建）
```

真实应用验证（写一条属性 + 提议一次后取合并时间线）：

```
origin  kind            version   摘要                              属性变化
route   refresh         route-v1  评分增益未达到进入阈值（ΔJ=0.000）
profile attribute_write v5        写入动态属性 lighting             lighting: →daylight
route   drift           route-v1  当前组合仍处于最短驻留时间（0/120 秒）
route   blocked         route-v1  没有可行组合：当前组合失效时保持原状，观察记录输出观察不足
route   baseline        route-v1  当前组合仍处于最短驻留时间（0/120 秒）
```

两个版本终于在同一条轴上：**画像 v5 与路由 route-v1 并列可见**，且每条都带
"为什么"——这正是交底书「时效语义画像 → 有效观察 → 局部重路由」闭环的界面表达。

一处实现细节值得记录：属性事件里"变更前取值"必须在赋值**之前**读，最初的实现
把它放在赋值之后，测出来的 previous 永远是 null；新加的 `test_attribute_writes_keep_the_previous_label`
就是为这个顺序问题准备的。

### 第 12 轮（门禁逐项明细）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
491 passed in 269.26s        # 第 11 轮 490 项 + 本轮 1 项，旧用例零回归

$ cd frontend && npm test
Test Files  37 passed (37)
     Tests  184 passed (184)

$ cd frontend && npm run build
✓ built in 16.74s
```

真实应用取一条 `insufficient` 记录后的明细（界面与接口一致）：

```
结论: insufficient | 原因: 画面质量指标未测定，不足以支撑未检出结论。

门禁                 结果        实测    门槛    说明
actual_fps           pass        1.0     0.9
max_gap_seconds      pass        1.1     1.5
window_seconds       pass       30.0    20.0
roi_visible_ratio    pass        1.0     0.9
overexposure_ratio   pass       0.03     0.2
blur_score           unverified           50.0   unverified_quality
occlusion_ratio      pass        0.0     0.3
target_scale_px      pass       48.0    24.0
path_complete        pass          1       1
version_consistency  pass

版本: route=route-1  profile=8  model=smoke
不存在的记录 → 404 observation_not_found
```

这一段就是"有效观察"最硬的证据：**同一窗口里 9 道门禁通过、1 道未测定，
因此系统判观察不足而不是未检出**。答辩时可以直接指着这十行解释"为什么这窗不算数"。

### 第 13 轮（侧栏按链路分组）补充证据

```
$ cd frontend && npm test
Test Files  38 passed (38)
     Tests  189 passed (189)   # 第 12 轮 184 项 + 本轮 5 项

$ cd frontend && npm run build
✓ built in 15.53s

产物核对：dist/index 含「运行与观察」「管理与诊断」，DashboardPage 含「事件记录」
```

侧栏现在的结构与交底书的对应：

| 分组 | 说明 | 条目 |
| --- | --- | --- |
| 采集 | S1–S6 接入视频源并建立任务 | 视频源管理、任务创建 |
| 运行与观察 | S6–S9 实际帧窗口的观察判定 | 快速监控看板、智能体管理 |
| 结果 | S8–S9 检测到、未检出与观察不足 | 事件记录（此前有页面但不在侧栏） |
| 管理与诊断 | 能力、资源与运行环境 | 运行状态、模型管理、系统设置 |

**路径一律未改**，`permittedRoutes` 的正则一字未动，既有链接与书签继续可用；
`navigation` 仍以扁平列表导出（由分组 flatMap 得到），因此既有测试无需改动。

### 第 14 轮（外部策略装载位与 MARL 契约）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
498 passed in 264.15s        # 第 13 轮 491 项 + 本轮 7 项，既有追踪/入侵用例零回归
```

真实进程验证（临时模块放在 PYTHONPATH 上，模拟"训练工程产出的策略包"）：

```
$ .venv\Scripts\python.exe -c "from app.modules.tracking import registry; \
    p = registry.create('demo_policy:Demo'); print('loaded:', p.name, p.describe())"
loaded: demo-external {'name': 'demo-external'}
```

装载失败的情形都给出明确错误码，**不会静默回退到启发式**：

| 情形 | 错误码 | HTTP |
| --- | --- | --- |
| 模块无法导入 / 缺属性 / 初始化抛错 | `tracker_policy_unavailable` | 503 |
| 对象不满足 `TrackerPolicy` 协议 | `tracker_policy_incompatible` | 503 |
| 注册表里的未安装槽位 `marl-association` | `tracker_policy_not_installed` | 503 |
| 完全未知的名字 | `tracker_policy_unknown` | 404 |

接入方式只有一行配置：`VISION_TRACKER_POLICY=module:attribute`；回滚同理
（改回 `heuristic-iou` 即可）。完整约定见 [MARL 追踪接入契约](MARL_TRACKING_CONTRACT.md)。

### 第 15 轮（策略状态回显）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
504 passed in 276.55s        # 第 14 轮 498 项 + 本轮 6 项，旧用例零回归

$ cd frontend && npm test
Test Files  38 passed (38)
     Tests  190 passed (190)

$ cd frontend && npm run build
✓ built in 14.86s
```

真实应用（默认配置）：

```
active=heuristic-iou  available=True  name=heuristic-iou  external=False
notice: 关联策略可替换；多智能体强化学习策略尚未安装，本机仍使用内置策略 heuristic-iou。
```

`resolved` 字段把"配置写的"与"实际装载的"分开，三种情况各有明确输出：

| 配置 | resolved | 界面表现 |
| --- | --- | --- |
| `heuristic-iou`（默认） | available=true，external=false | 绿色"实际装载：heuristic-iou（内置策略）" |
| `module:attribute`（已装载） | available=true，external=true，带策略 describe | 绿色"实际装载：<策略名>（外部策略）" |
| `marl-association` 或坏 spec | available=false，带原因 | 红色"实际装载：不可用 —— <原因>" |

外部策略的描述在**每个进程内只构造一次**（有测试用计数替身验证第二次请求
不再调用装载逻辑），避免每次打开面板都重新加载一遍权重。

### 第 16 轮（分组高亮与可观察性摘要）补充证据

```
$ cd frontend && npm test
Test Files  39 passed (39)
     Tests  194 passed (194)   # 第 15 轮 190 项 + 本轮 4 项

$ cd frontend && npm run build
✓ built in 16.98s
```

摘要条显示三段内容，全部来自既有接口，且**取不到就说未知**：

| 段 | 数据来源 | 取不到时 |
| --- | --- | --- |
| 画像版本 | `GET /sources/{id}/semantic-profile` | 「未知」 |
| 最近观察 | `GET /agents/{id}/observations` 的 `summary` | 「未知」，不显示 0 |
| 当前路由 | `GET /agents/{id}/routing` | 「尚未建立」 |

侧栏分组按**最长前缀**匹配，因此 `/dashboard/events` 归到「结果」而不是
「运行与观察」，`/agents/task/live` 归到「运行与观察」——这两条都有测试钉住。

一处既有断言的更新值得记录：原用例断言"打开页签前不发生任何观察请求"，
但摘要条按设计会在挂载时取一次结论分布。契约变了，断言随之改成
"页签未打开时观察列表不渲染、打开后请求数增加"，而不是放宽或删除断言。

### 第 17 轮（章节初稿）补充证据

本轮是文档轮，代码零改动。新增的 [系统实现（章节初稿）](THESIS_IMPLEMENTATION.md)
把前 16 轮的实现按学位论文结构整理成九节，其中引用的数字全部来自本机实测，
并逐处标注了"能证明什么、不能证明什么"：

| 文中数据 | 来源 | 是否可复现 |
| --- | --- | --- |
| 式(2) 0.675 / 0.905 / 0.725 | 交底书实施例一复现测试 | 单元测试 |
| 三态分布 8 / 9 / 4，帧率 8.2–9.2 | 真实任务 75 秒运行 | `routing_smoke.py` 同类流程 |
| +85 MB / ~90 ms / ±2 ms | 三次影子会话实测 | `preheat_measure.py` |
| 6/6 帧、33 目标、IoU 1.0 | plaza.mp4 取 6 帧 | `shadow_compare.py` |
| 120 步等价性 | 追踪策略重构测试 | 单元测试 |

文档之间已互链：对照表与验收记录顶部都指向这份初稿，避免出现"三份文档各说一套"。

### 第 18 轮（场景证据来源）补充证据

```
$ .venv\Scripts\python.exe -m pytest tests/backend -q
507 passed in 270.03s        # 第 17 轮 504 项 + 本轮 3 项，旧用例零回归

$ cd frontend && npm test
Test Files  39 passed (39)
     Tests  196 passed (196)

$ cd frontend && npm run build
✓ built in 14.31s
```

真实应用（两路摄像头，各自指向自己最近的窗口）：

```
[夜间街道] 证据=detected usable=True 窗口=1108948.0–1108979.0 目标尺度=83.1
[行人广场] 证据=detected usable=True 窗口=1108947.8–1108978.0 目标尺度=132.4
```

三态在界面上分别是：绿色"场景证据来自有效观察窗口 x–y 秒"、
红色"场景证据来自观察不足窗口 …（只能作为提示，不能当作已成立的场景条件）"、
灰色"该视频源还没有观察记录，场景条件按未测定处理"。

这一改动把 F3（有效观察）与 M6（组合求解）真正连起来：**用于选模型的场景条件，
现在必须说明它来自哪一窗、那一窗算不算数**。

实现过程中出现一次回归：`_latest_metrics` 改成返回二元组后，`routing/state.py`
的 `_scenario` 仍在按字典使用返回值，导致 12 项路由状态用例失败。定位后改为解包，
路由状态机 21 项用例全绿——这也是为什么每次改动都要跑全量回归。

## 八、自查方法

```powershell
cd C:\Users\陈宇鑫\Desktop\vision-appliance-software
$env:PYTHONPATH="$PWD\backend;$PWD"

# 1. 后端全量
.\.venv\Scripts\python.exe -m pytest tests/backend -q

# 2. 只跑本轮相关
.\.venv\Scripts\python.exe -m pytest tests/backend/test_semantic_profile.py `
    tests/backend/test_observation_gate.py tests/backend/test_semantics_api.py `
    tests/backend/test_observation_window.py tests/backend/test_executor_observation.py -q

# 3. 前端
cd frontend; npm test; npm run build; cd ..

# 4. 起应用后跑真实冒烟（画像与三态接口）
.\.venv\Scripts\python.exe deploy\scripts\semantics_smoke.py

# 5. 验证执行器真的在写记录：起一个真实任务 ≥ 40 秒后查接口
#    GET http://127.0.0.1:8000/api/v1/agents/<任务ID>/observations?limit=20

# 6. 看路由评估（换 source id 即可；rule 取 absence 或 intrusion）
#    GET http://127.0.0.1:8000/api/v1/sources/<视频源ID>/routes?rule=absence

# 7. 只跑本轮新增的路由测试
.\.venv\Scripts\python.exe -m pytest tests/backend/test_requirement_graph.py `
    tests/backend/test_route_solver.py tests/backend/test_routing_api.py `
    tests/backend/test_drift_hysteresis.py tests/backend/test_routing_state.py -q

# 8. 看路由状态与决策审计（换 agent id）
#    GET  http://127.0.0.1:8000/api/v1/agents/<任务ID>/routing
#    GET  http://127.0.0.1:8000/api/v1/agents/<任务ID>/routing/decisions
#    POST http://127.0.0.1:8000/api/v1/agents/<任务ID>/routing/propose
#         {"channel_id":"...","source_id":"...","rule":"absence"}

# 9. 看接口文档（浏览器）
#    http://127.0.0.1:8000/api/docs  → tags: semantics / routing

# 10. 界面：智能体管理 → 对应任务 → 查看画面与报警 → 有效观察 / 路由候选
```

## 九、明确未做或做不了（写论文时必须如实标注）

1. **执行器已由观察结论和业务人数口径共同约束业务事件**：缺岗接受有效的 `not_detected` 窗口，也接受有效但窗口人数低于 `min_count` 的 `detected` 窗口；在岗恢复仍要求 `detected` 且人数达到 `min_count`，入侵只接受 `detected`。`insufficient`、观察保存失败或摄像头异常重连时丢弃待发布事件并复位窗口与规则，避免失效前后连续计时拼接。事件会等待对应窗口关闭后发布；`observation_records=False` 时不伪造观察记录，也不发布没有可判定窗口的业务事件。这里的原子性仅是**窗口级兼容筛选原子性**：任一待发布事件不兼容就整窗不进入发布；兼容事件仍按既有独立事务逐个持久化，部分持久化失败沿用既有错误语义，**不是数据库批量写入原子**。
2. **路由版本会切换，但真正加载的模型不会变**：本轮实现了当前组合、候选验证、式(3) 滞回、`route_version` 递增，以及**并存第二份会话的资源实测**（+85 MB / 约 90 ms / 逐帧 ±2 ms）；但**执行器仍只加载任务配置里那一项能力**，不会因为路由切换就真的预热并切换到候选组合。所谓"影子运行"目前是"重复评估 + 成本实测"，不是让候选与当前组合并行跑推理。这是与交底书 S14 最实质的差距，论文里必须明确写出。
3. **质量表是示例值**：除跟踪器与区域规则外，所有能力质量都标注 `calibrated=false`，是保守示例值而非分桶验证结果。论文中必须声明这张表不是准确率，实验章节需要单独做分桶标定。
4. **切换路径无法在实机重现**：本机只安装了 YOLO11n 一项检测能力，因此真实环境里只能观察到基线、漂移、阻塞与"未达驻留"四种结果；`switch` 分支由单元测试用"另一项已安装能力"的替代表覆盖，需要在论文中注明是构造场景。
5. **遮挡比例不可测**：单帧无法可靠判断遮挡，该指标保持"未测定"，只有外部传入（人工标注或未来的分割模型）时才参与门禁。论文中不能把遮挡当作已实现能力。
6. **最小可辨目标尺度依赖检测框**：无目标时不可测，因此缺省只阻止"未检出"，不阻止"检测到"；若要用几何标定替代，需要额外的参考物标定流程，本轮未做。
7. **设备报文推理服务**：本机没有真实设备平台，仅有规则（报文缺失不得作为连续未检出证据），未验收。
8. **独立低频多模态探针**：未接入外部探针服务，用本地图像统计与设备状态替代，属弱探针。
9. **预处理器只建模了"分桶修复"**：去眩光与裁剪在表里声明了修复关系与不可恢复饱和上限，但既未安装也未标定；裁剪带来的等效像素增益没有建模（需要真实标定才能写），因此目标尺度不足只能靠换模型解决。
10. **漂移只看属性层**：设备事件（PTZ 转动、断电、断流）目前只通过 `source_identity` 变化间接体现，没有进入 `drift.py`；视场版本切换也还没有自动触发。
11. **前端是"基本完成"**：任务详情已按链路重排为四个页签，画像编辑、有效观察、路由候选、决策历史、关联策略与观察↔路由互跳都已上线；但**左侧七导航仍是原样**（快速监控看板/运行状态/视频源/任务创建/智能体/模型/设置），没有按 M1–M9 重新分组，版本时间线也还没做。
12. **影子对照不是跨模型对照**：`shadow.py` 让两个会话跑同一批帧并逐帧比对，但两者加载的是**同一份 ONNX**，因此只能证明影子通道的确定性与代价；真正"换个模型是否更准"需要第二份已标定的产物。
13. **画像初始化只做了一半**：录像源能从影片前 1/10 取一帧写入一项保守 `lighting`；摄像头源不做首帧取图，动态层仍需运行中的观察或人工写入。初始化只填缺项，不会覆盖已有属性。
14. **多智能体强化学习追踪只有接口，没有能力**：`modules/tracking` 固定了观测（归一化检测框 + ROI + 可选画面指标）、动作（关联/入场/丢失）与轨迹状态归属，`marl-association` 在注册表里标记 `installed=False`、`calibrated=False`，界面上也如实显示"未安装"；**本仓库不含训练循环、仿真环境与策略权重**，创建它会直接 503。论文里只能说"预留了可插拔的策略接口"，不能说"已实现 MARL 追踪"。
15. **观察节奏是"30 秒观察 + 条件静默"**：观察窗口仍为 30 秒；关窗判定有效且本次没有发布业务事件时，静默 `observation_quiet_seconds`（默认 600 秒，`VISION_OBSERVATION_QUIET_SECONDS`）后再采下一窗；判定观察不足则立即下一窗。静默期内业务规则照常逐帧运行，但待发布业务事件要等下一窗关窗才发布，**报警延迟最长约静默时长加一个窗口**。配置为 0 时回到连续的窗接窗节奏（测试与旧行为用）。

另有两条**已知的展示性噪音**，不影响正确性：`contracts/openapi.json` 的整段重排（FastAPI 的 schema 排序基于集合迭代顺序，新增 schema 时会重排，只加字段则不会）；`var/logs`、`dist`、`.venv` 等运行产物不入 Git。

## 十、下一轮（第 19 轮）计划

1. 定义"无有效证据时的保守取值"：目前观察不足窗口的指标仍参与分桶与质量读取，只是被标注；下一步可让无效窗口完全退出计算，改用固有层与保守默认值，并给出显式提示。
2. 运行状态页增加"画像 / 观察 / 路由"三项就绪度，未就绪如实显示（延续"不伪造绿色"的约定）。
3. 观察记录详情页：点开一条 `insufficient` 可看到当时的组合成员、门禁逐项数值与当时的漂移，而不只是原因文本。
4. 把"画像为空"的常见路径补上自动初始化：首次运行时按设备字段与首帧图像统计写入固有层与一项动态属性（仍需人工确认后才用于路由）。
5. 若拿到第二份已标定的 ONNX，把 `shadow.py` 的对照从"同产物确定性"推进到"跨模型质量对比"，并回填能力表的分桶质量。

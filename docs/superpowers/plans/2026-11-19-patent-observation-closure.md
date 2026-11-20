# 专利可信观察与业务表达实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让有效观察真正约束路由输入和业务事件，并用不带专利内部编号的业务界面准确呈现多视频运行状态。

**Architecture:** 沿用现有模块化单体。先在隔离 worktree 审核并落定当前证据补丁，再让无效观察退出求解；随后把业务事件改为窗口关闭后发布，无效窗口不得留下事件或连续状态；最后修正界面术语与多视频上下文。真实候选模型影子运行、加载回执和原子接管属于下一依赖计划，不在本计划中虚假宣称完成。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy、SQLite、Vue 3、TypeScript、Naive UI、Vitest、Pytest。

**Spec:** 用户提供的 `交底书_系统框图优化版.docx`；只读提取文本 `.artifacts/patent-disclosure/document.txt`；既有设计 `docs/superpowers/specs/2026-11-17-patent-framework-design.md`。

## Global Constraints

- 每个任务只产生一个功能提交；提交前必须由未实现该任务代码的另一名智能体明确批准精确补丁。
- 审批记录写入 `docs/reviews/<change-id>.json`，包含基线、补丁 SHA-256、验证结果、审查者、结论和限制；代码变化后原批准失效。
- 保留原工作区已有改动；所有新工作在独立 worktree 中进行，不 push、不强制推送。
- 界面不得出现 `S1`–`S14`、`M1`–`M9`、`F1`–`F5`、`ΔJ` 等专利内部编号或公式符号；内部代码标识可保留。
- 界面优化使用 Anthropic `frontend-design` skill 与已安装的 `frontend-design-direction`；复用现有组件和设计体系，不新增视觉依赖。
- 不把数据库版本变化描述成真实模型切换；本计划完成时仍需如实保留这一边界。

## Review Focus

- 无效或无法保存的观察：不得产生业务事件，也不得把失效前后的计时拼成连续证据；Task 3 的执行器测试固定此行为。
- 只有无效观察的视频源：界面可展示该记录，但其指标不得进入场景求解；Task 2 同时覆盖接口与状态机口径。
- 多视频任务：观察、画像摘要和模型组合必须指向同一视频源；Task 5 用第二路视频测试固定。
- 后端生成的时间线摘要：同样不得泄露公式符号；Task 4 同时检查前端渲染与后端摘要。
- 审查后补丁任何变化：必须重新计算哈希并重新批准；每个任务的提交步骤都执行该检查。

---

### Task 1: 审核并落定当前有效证据选择补丁

**Files:**
- Modify: 当前已有的 8 个修改文件，主要是 `backend/app/modules/routing/service.py`、`schemas.py`、`state.py`、`frontend/src/modules/agents/RoutePanel.vue` 及对应契约和测试。
- Create: `docs/reviews/2026-11-19-route-evidence.json`

**Interfaces:**
- Produces: `EvidenceView.confidence: str`；`_latest_evidence(...) -> (metrics, evidence, fell_back)`；后续任务沿用这三个返回值。

- [ ] 将原工作区当前补丁完整复制到隔离 worktree，确认 8 个文件与原工作区一致，不夹带其他文件。
- [ ] 运行 `PYTHONPATH="$PWD/backend:$PWD" ./.venv/Scripts/python.exe -m pytest tests/backend/test_routing_api.py tests/backend/test_routing_state.py -q`，预期全部通过。
- [ ] 运行 `npm --prefix frontend test -- route-panel` 与 `npm --prefix frontend run build`，预期全部通过。
- [ ] 独立审查者检查“最近有效窗口优先、只有无效窗口时标为未证实、界面状态一致”及测试；发现问题则实现者修复并重跑。
- [ ] 对精确实现补丁计算 SHA-256，取得独立审查者明确批准，写入审批记录；再运行上述测试和完整后端/前端回归。
- [ ] 仅在本任务全部文件审批后提交：`feat(routing): 优先采用有效观察作为场景证据`。

### Task 2: 无效观察退出场景求解

**Files:**
- Modify: `backend/app/modules/routing/service.py`、`backend/app/modules/routing/state.py`
- Modify: `frontend/src/modules/agents/RoutePanel.vue`
- Test: `tests/backend/test_routing_api.py`、`tests/backend/test_routing_state.py`、`frontend/tests/route-panel.test.ts`
- Create: `docs/reviews/2026-11-19-invalid-evidence-exclusion.json`

**Interfaces:**
- Consumes: Task 1 的 `_latest_evidence` 三元组与 `EvidenceView.confidence`。
- Produces: 无有效窗口时返回 `metrics={}`、最近无效记录仍作为 `evidence` 供提示；求解与状态机只看到空指标。

- [ ] 先写失败测试：只有一条 `insufficient` 且 `target_scale_px=8` 时，`scenario.target_px is None`；证据仍为 `unverified`，提示限定为“当前监测规则尚无有效观察窗口”。
- [ ] 增加状态机测试，证明 `_scenario` 同样不读取无效窗口指标；增加“旧有效窗 + 新无效窗”回归，仍采用旧有效窗指标。
- [ ] 运行上述测试，确认新断言在当前实现上失败。
- [ ] 最小修改 `_latest_evidence` 的回退分支：保留证据记录但返回空指标；同步前端提示范围。
- [ ] 重跑定点测试至通过，再跑 `pytest tests/backend -q`、`npm --prefix frontend test`、`npm --prefix frontend run build`。
- [ ] 独立审查者批准精确补丁与审批记录后提交：`fix(routing): 无效观察不再参与场景求解`。

### Task 3: 业务事件仅由有效观察窗口发布

**Files:**
- Modify: `backend/app/modules/local_execution/service.py`
- Modify: `backend/app/modules/local_execution/presence.py`、`intrusion.py`（仅在统一保守重置入口确有必要时）
- Test: `tests/backend/test_executor_observation.py`；新增 `tests/backend/test_business_observation_gate.py`
- Modify: `docs/ACCEPTANCE_PATENT.md`、`docs/PATENT_MAPPING.md`、`docs/THESIS_IMPLEMENTATION.md` 中“观察只记不用”的旧边界。
- Create: `docs/reviews/2026-11-19-business-observation-gate.json`

**Interfaces:**
- Consumes: `semantics.record_observation(...) -> ObservationView`，其 `verdict` 为 `detected / not_detected / insufficient`。
- Produces: 执行器内部的待发布事件队列；窗口关闭后按结论发布或丢弃。缺岗事件只接受 `not_detected`，入侵与在岗恢复只接受 `detected`；`insufficient` 或观察保存失败时清空待发布事件并调用 `rule.mark_unavailable()`。

- [ ] 先把全饱和缺岗测试改为期望零事件，并新增观察保存失败时零事件测试；运行确认当前实现因仍产生 `person_absence` 而失败。
- [ ] 新增入侵负例：无效窗口不发布入侵、不推进布防/清除状态；新增分段序列“有效 11 秒 → 无效 1 秒 → 有效 11 秒”，不得按 22 秒连续缺岗发布事件。
- [ ] 新增正常路径对照：有效空窗口仍发布缺岗，有效人员窗口仍发布在岗恢复，有效入侵仍发布入侵；事件只携带其实际窗口与运行版本。
- [ ] 在 `_execute` 中最小实现待发布事件缓存：采样可更新临时规则状态和运行画面，但 `_record_*` 只在窗口判定兼容后调用；窗口失效或记录异常时丢弃缓存并重置规则，防止跨失效窗口连续计时。
- [ ] 窗口尚未关闭或运行异常退出时不得泄漏待发布事件；证据帧只在内存中保留到对应窗口关闭，不新增持久化文件。
- [ ] 重跑定点测试至通过，再跑完整后端、前端和部署测试；更新文档为“观察结论约束业务事件”，不得声称候选模型已真实切换。
- [ ] 独立审查者重点检查报警延迟、重复报警、恢复事件和失效重置；批准精确补丁后提交：`feat(execution): 业务事件仅由有效观察窗口发布`。

### Task 4: 界面改用业务语言表达运行闭环

**Files:**
- Modify: `frontend/src/app/navigation.ts`、`frontend/src/modules/agents/MonitorPanel.vue`、`ObservationPanel.vue`、`RoutePanel.vue`、`RouteTimeline.vue`
- Modify: `backend/app/modules/routing/hysteresis.py`（仅替换返回给界面的 `ΔJ` 摘要）
- Test: `frontend/tests/navigation.test.ts`、`agent-tabs.test.ts`、`observation-panel.test.ts`、`route-timeline.test.ts`、`route-panel.test.ts`、`tests/backend/test_drift_hysteresis.py`
- Create: `docs/reviews/2026-11-19-business-ui-language.json`

**Interfaces:**
- Produces: 面向用户的“模型组合 / 观察条件 / 评分增益 / 需要调整的部分”等业务词汇；API 字段名保持不变。

- [ ] 安装并加载 Anthropic 官方 `frontend-design` skill，结合 `frontend-design-direction` 记录界面契约：中文本地监测工具、桌面与 390px、信息密集但安静、首屏突出实际运行状态。
- [ ] 先写失败测试：所有导航说明、任务页签和时间线渲染不得匹配专利内部编号或 `ΔJ`；后端时间线摘要使用“评分增益”。
- [ ] 替换内部编号和研发术语，不更改路由路径、API 字段或操作流程；调整组合页信息顺序时先显示当前状态、证据与首选，再放次级审计信息。
- [ ] 运行相关前后端测试至通过；在真实浏览器检查 1440px 与 390px、长中文、键盘焦点、空/错/部分数据状态，保存截图与检查记录。
- [ ] 跑完整回归和生产构建；独立审查者检查术语、界面证据与无内部编号的断言，批准后提交：`feat(ui): 用业务语言呈现专利运行链路`。

### Task 5: 修复多视频观察与模型组合上下文

**Files:**
- Modify: `frontend/src/modules/agents/MonitorPanel.vue`、`TaskSummaryStrip.vue`
- Test: `frontend/tests/observation-panel.test.ts`、`agent-tabs.test.ts`、`task-summary.test.ts`
- Create: `docs/reviews/2026-11-19-multisource-context.json`

**Interfaces:**
- Consumes: `ObservationPanel` 已发出的 `open-route` 事件及其 `sourceId`。
- Produces: 共享的当前 `{channelId, sourceId, rule, duration}` 目标；观察跳转、模型组合和摘要读取同一对象。

- [ ] 先写两路视频失败测试：从第二路观察打开模型组合后，请求参数、标题、画像版本和当前组合均属于第二路。
- [ ] 保存观察事件携带的视频/通道目标，不再由 `routeTarget` 永远取第一通道第一绑定；无显式选择时保留第一路默认。
- [ ] 摘要明确“任务累计”或按当前视频过滤，并区分加载失败、无记录和尚未建立；不得用 0 或空态掩盖请求失败。
- [ ] 运行定点测试、完整前端测试和构建；浏览器实测两路切换、刷新后的状态、窄屏与接口失败。
- [ ] 独立审查者批准精确补丁后提交：`fix(ui): 保持多视频观察与执行方案上下文一致`。

## Verification

每个任务都必须有本任务的红→绿证据、全量回归和独立审批。涉及界面的任务还必须有真实浏览器证据，不能用 jsdom 代替。完成本计划只宣称“有效观察已约束路由输入与业务事件、界面业务表达和多视频上下文已修正”；真实候选影子运行与原子模型接管留给下一计划。

## Assumptions

- 团队中的独立审查智能体满足“其他人同意”的要求；主代理不能在审查者未明确批准时提交。
- 为遵守“无效观察不能形成业务结论”，业务事件可延迟到对应观察窗口关闭；这是有意的行为变化，必须在文档和界面中可解释。
- 当前 8 个未提交文件属于本目标的一部分，经独立审查和验证后才可作为 Task 1 提交。

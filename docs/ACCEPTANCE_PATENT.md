# 专利框架落地验收记录

本文件随每一轮实现增量更新，用于说明"改了什么、怎么验证、什么还没做、哪些做不了"。设计依据见 [专利框架设计](superpowers/specs/2026-11-17-patent-framework-design.md)，分阶段任务见 [实施计划](superpowers/plans/2026-11-17-patent-framework.md)。

当前基线：`92ecfa1` 之上共 3 个提交，全部只提交未 push。

## 一、总体路线与状态

| 阶段 | 内容 | 对应交底书 | 状态 |
| --- | --- | --- | --- |
| 一 | 时效语义画像、画面指标、有效观察三态、持久化与接口 | F1/M3、F3/M8、式(1) | **已完成（第 1 轮）** |
| 二 | 执行器影子接入，`RunDTO` 补版本字段，前端"有效观察"面板 | M2、M7、S6–S9 | 未开始 |
| 三 | 需求图、能力表扩展、组合求解 | F2/M4–M6、式(2) | 未开始 |
| 四 | 漂移判定、局部重路由、影子运行与原子切换 | F4/F5/M9、式(3) | 未开始 |
| 五 | 前端信息架构改造（画像/观察/路由） | M1–M9 | 未开始 |
| 六 | 追踪策略接口（为多智能体强化学习预留）与验收汇总 | — | 未开始 |

## 二、第 1 轮提交

| 提交 | 说明 |
| --- | --- |
| `2cba084` | `docs: 新增专利框架落地设计与实施计划`：差距对照、方案选型、M1–M9 映射、7 项不可实现清单、六阶段排期 |
| `b63ac67` | `feat(semantics): 落地时效语义画像与有效观察三态判定`：18 个文件，+6259 / −1963（其中 `contracts/openapi.json` 与 `generated.ts` 为重新生成） |

## 三、新增文件

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

## 八、自查方法

```powershell
cd C:\Users\陈宇鑫\Desktop\vision-appliance-software
$env:PYTHONPATH="$PWD\backend;$PWD"

# 1. 后端全量
.\.venv\Scripts\python.exe -m pytest tests/backend -q

# 2. 只跑本轮新增
.\.venv\Scripts\python.exe -m pytest tests/backend/test_semantic_profile.py `
    tests/backend/test_observation_gate.py tests/backend/test_semantics_api.py -q

# 3. 前端
cd frontend; npm test; npm run build; cd ..

# 4. 起应用后跑真实冒烟
.\.venv\Scripts\python.exe deploy\scripts\semantics_smoke.py

# 5. 看接口文档（浏览器）
#    http://127.0.0.1:8000/api/docs  → tags: semantics
```

## 九、明确未做或做不了（写论文时必须如实标注）

1. **执行器尚未接入**：观察记录目前由调用方提交，运行中的 YOLO 任务还不会自动产生记录。第 2 轮补上，且先以影子模式接入、不改报警。
2. **遮挡比例不可测**：单帧无法可靠判断遮挡，该指标保持"未测定"，只有外部传入（人工标注或未来的分割模型）时才参与门禁。论文中不能把遮挡当作已实现能力。
3. **最小可辨目标尺度依赖检测框**：无目标时不可测，因此缺省只阻止"未检出"，不阻止"检测到"；若要用几何标定替代，需要额外的参考物标定流程，本轮未做。
4. **设备报文推理服务**：本机没有真实设备平台，仅有规则（报文缺失不得作为连续未检出证据），未验收。
5. **独立低频多模态探针**：未接入外部探针服务，用本地图像统计与设备状态替代，属弱探针。
6. **组合求解、局部重路由、影子切换**：全部未实现。
7. **多智能体强化学习追踪**：未实现，第 6 轮只做策略接口预留。

另有两条**已知的展示性噪音**，不影响正确性：`contracts/openapi.json` 的重排（FastAPI 的 schema 排序基于集合迭代顺序，新增任何 schema 都会整段重排）；`var/logs`、`dist`、`.venv` 等运行产物不入 Git。

## 十、下一轮（第 2 轮）计划

1. 执行器在业务采样窗口结束时生成观察记录：影子模式，只写记录不改报警，失败降级为诊断。
2. `metrics.py` 接入真实帧：过曝、亮度、清晰度在 ROI 掩膜上实测；帧率与最大间隔来自实际收到的帧。
3. `RunDTO` 增 `profile_version`、`route_version`；运行状态页显示画像与观察就绪状态。
4. 前端任务详情页新增"有效观察"面板：三态徽标、失效原因、门禁明细。
5. 用一段真实录像做对照：人为遮挡/过曝时产生 `insufficient` 而不是 `not_detected`。

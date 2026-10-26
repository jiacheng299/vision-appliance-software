# 成员 A：任务创建与模型管理

2026-10-26。基于 `e6cb3dd` 的 Vue 3 / TypeScript / Naive UI、FastAPI / SQLite 实现。

## 已确认范围

用户确认暂时没有真实模型服务，模型与文件格式尚未确定，沿用现有“智能体 → 监测组 → 多个视频源”结构。A 负责配置创建、模型/模板、公开能力校验与本地大模型用途选择。B 保持 Agent/Revision 所有权；真实 Run/Event、推理、视频网关、证据与调度依然由公共提供方负责。

模型文件作为惰性二进制保存，不根据扩展名声称支持 ONNX/PyTorch，不解压、不导入 Python、不反序列化 pickle。上传计算 SHA-256；算法验证需提供方确认运行接口、文件、模板声明与自检。正式模式没有适配器时保留 pending，不能进入可用目录。模拟通过仅存在显式隔离演示模式。

## 启动与演示

保持原安装命令与依赖，运行时不需要 CDN、云模型或新账户。安装后 `start.cmd` 正常启动，进入 `/create` 或 `/models`。新安装正式模式下本地大模型部署列表为空，解析与完整执行能力如实不可用；草稿与模型管理正常可用。

运行 `start-agents-demo.cmd` 使用现有隔离演示目录与 8004 端口，无需新启动脚本：

1. 在“模型管理 → 本地大模型”选择模拟解析器，点击应用用途选择。也可绑定模拟多模态部署用于展示用途切换。
2. 进入“任务创建”，点击“加载模拟素材”。此按钮复用 B 的公开演示种子 API，也会创建 B 的示例智能体。
3. 输入任务名，选择一个或多个模拟源；分别点至少三个边界点、点击起点闭合并保存区域。录像可填写起止秒数；实际提交为毫秒。
4. 输入“有人在区域内停留超过30秒时报警”，解析并核对目标 person、规则 dwell、时长 30。也可手工填写。未写时长不会默认填 30。
5. 选择模拟人员模型与绑定模板，核对全部条件，保存并验证。
6. 查看可执行性、缺项与限制，勾选最终确认并启动。页面查询异步 operation，只有 succeeded 后跳转对应智能体实时详情；每个源拥有独立 runId。
7. 将时长留空、使用不支持的规则、移除其中一源的区域，验证应阻止启动。修改任何字段会使旧评估失效。
8. 模型页可选择任意**测试用非私密文件**，填写名称、版本、运行接口与模板。示例目标 person，规则 dwell，需区域 dwell，需时长 dwell。模拟校验通过后该配对同步出现在 A/B 目录中；不会执行该文件。
9. 详情可查看全部配置引用，运行中的模型归档由后端拒绝；停止后核对历史影响、勾选确认才能归档。

模拟素材、画面、关键词解析、校验和运行均不代表真实识别效果；模拟运行/事件由 B 的内存提供方维护，重启后重置，配置/模型管理项保留。

## 页面与代码

- `frontend/src/modules/task-create/`：四步创建页与本模块状态规则；只消费 SDK，不操作 B 私有 Store。
- `frontend/src/modules/model-management/`：小模型/模板管理、本地大模型用途选择、A SDK。
- `frontend/src/shared/media/RegionEditor.vue`、`regionGeometry.ts`：共用划区与几何校验。B 原导出路径保留兼容包装，不改变既有交互。
- `backend/app/modules/models/`：A 的数据库、校验、接口和算法接入端口。
- `backend/alembic/versions/0005_member_a_models.py`：在既有单一迁移链尾部增加模型文件、配对版本、幂等记录和 LLM 用途表。
- `tests/backend/test_member_a.py`、`frontend/tests/task-create.test.ts`：成员 A 的主要验收自动化。

草稿由 B 服务持久化，保存后 URL 带 `?draft=<agentId>`；用户可保存该地址继续编辑。新任务从已有配置复制时生成新的实例/首版 Revision 和监测组标识，原配置不变。模型业务编辑创建新版本；同 modelId 的模型版本与模板版本都不得重复，旧版本配对和文件保留。

## 接口约定

沿用仓库已冻结的 **snake_case、裸 DTO、row_version、Idempotency-Key**；附件中的 camelCase/统一封装/路径是建议，不另造第二套不兼容合同。最终 OpenAPI 位于 `contracts/openapi.json`，前端类型由它生成。UTC ISO8601、归一化区域、cursor 分页、统一公共错误保持不变。

| 接口 | 行为 |
| --- | --- |
| POST `/api/v1/model-files?filename=` | 原始二进制流式上传，返回文件 ID/大小/SHA-256；不返回服务器路径 |
| GET/POST `/api/v1/models` | 查询各模型版本（q/validation/cursor/limit）或创建模型与唯一模板配对；写入须幂等键 |
| GET `/api/v1/models/{id}?version=` | 查询指定版本；省略 version 返回最新创建版本 |
| POST `/api/v1/models/{id}/versions` | 创建新配对版本，旧版本不可覆盖；可沿用原 file_id |
| POST `/api/v1/models/{id}/versions/{version}/verify` | 接受 row_version；完整性 + 算法适配校验；返回 pending/passed/failed |
| POST `/api/v1/models/{id}/versions/{version}/archive` | 引用检查后软归档；row_version + acknowledge_history |
| GET `/api/v1/capabilities/models` | 只返回通过校验、未归档且来源匹配的模型/模板，支持 cursor |
| GET `/api/v1/capabilities/models/{id}?version=` | 指定版本能力；存在多个可用版本时必须指定 version |
| POST `/api/v1/capabilities/validate` | 校验 capability_ref、target、rule，返回 valid、unsupported_conditions、fingerprint |
| GET `/api/v1/llm/deployments` | 提供方声明的本地部署/健康状态、用途绑定及 row_version |
| PUT `/api/v1/llm/selections/{usage}` | deployment_id + row_version；只允许健康且支持用途的部署 |
| POST `/api/v1/requirements/parse` | requirement_text；返回结构化建议、缺项、限制、实际部署 ID/版本和 data_origin |
| POST `/api/v1/requirements/evaluate` | config；即时评估，不生成可启动凭据；启动必须走 B 的持久化 validation/confirmation |

任务创建复用现有 `/agents`、`/revisions/{id}`、`/validations`、`/confirmations`、`/run-groups`、`/operations/{id}`。A 查询引用时经 B 的公开 `/agent-services/references` API（同进程 ASGI HTTP，分页完整拉取），不导入 B 的数据库模型。归档保留历史文件、配置与事件。运行状态不可查询且有已发布引用时，后端拒绝归档。

`RegistryAgentServices`/`RegistryDemoServices` 在组合入口实现 B 公布的能力端口，因此 B 的目录、验证和发布使用与 A 相同的 fingerprint。显式传入的既有 `agent_services` 不被替换；接入新公共服务时应将 A 的 catalog/assess 与其运行端口组合，而非继续使用独立能力目录。

## 真实算法适配

在 `create_app(model_services=...)` 注入 `ModelServices` 实现：

- `verify(definition, path, checksum)`：受信算法适配器核验完整文件与声明模板，返回 passed/failed 和说明。不得因为用户表单填写了规则就确认能力；不能加载不可信 Python 对象。
- `deployments()`：由服务端配置本地部署，返回公开显示信息和健康状态；不得暴露带凭据 URL。
- `parse(text, deployment)`：使用请求开始时选定的部署，返回符合 ParseResult 的结构化结果；必须准确回传部署 ID/版本和 data_origin。
- `evaluate(config, sources, catalog, deployment)`：对原始需求、逐源证据条件和执行能力做真实判断，返回 Assessment（包含相同 fingerprint 与全部 chosen_capabilities）。

生产适配器 data_origin 必须 real；非 testing/显式 demo 模式不允许注入 mock。`verify` 的路径只传给服务端可信适配器，不提供浏览器任意文件访问。

大模型用途切换仅修改绑定表，既有 AgentRevision、Run 和解析响应不会回写。正式模式默认 runtime 仍未接入，不因模型导入而变成可运行。运行适配器仍须在提交时原子检查活动范围、最新能力目录/资源并保证幂等。

## 文件与并发

上传上限 `VISION_MAX_MODEL_FILE_BYTES` 默认 1 GiB；请求流写随机 UUID `.part`，成功后原子改名，异常清理半成品，数据库只记文件引用。额外保留 32 MiB 磁盘余量。不信任文件名路径。新建模型幂等回执与数据同事务提交；模型版本变更/校验/用途切换/归档都进行服务端校验与冲突保护。

任务保存、确认、启动使用 B 的幂等与版本合同。创建/确认/启动请求键在当前浏览器会话保留，用于丢失响应时重试。启动只轮询服务器操作结果；网络断开不会显示伪成功，可恢复查询或进入智能体详情。

## 验证与当前限制

测试命令沿用根 README；新增自动化覆盖 A-01 的录像范围验证、A-02/A-03 缺项与逐源 ROI、A-04 不支持、A-05 旧结论失效、A-06 无效模板/文件不进入目录、A-07 活动引用保护、A-08 用途绑定切换、A-09 幂等及 A-10 依赖未接入降级。

当前限制：真实模型包格式/执行器、解析与多模态评估、模型效果与硬件性能均未确定，不属于本次虚构实现。可用条件来自算法确认或显式模拟声明。没有原生矩形专用工具，四点多边形可表达矩形；划区基于源原始宽高比例。模型上传为单次流式请求，可显示进度但暂不支持断点续传。模型历史不物理删除，未绑定的上传文件当前也保留，需后续受控清理策略。草稿冲突保留输入并提示刷新，尚无自动合并界面。

## 本轮实测记录

- 后端完整回归：107 项通过（含新增 12 项 A 验收测试）。
- 前端完整回归：16 个测试文件、61 项通过；新增任务页 8 项、模型页 2 项。
- 部署检查：10 项通过。
- TypeScript 检查与生产构建通过；保留现有 HLS 分包体积提示。
- 本轮未完成浏览器人工验收：云浏览器无法连接当前本地服务，环境内 Chromium 安装包下载也未成功；不将组件测试说成浏览器端到端测试。
- 一次初始完整回归在既有后台资源采样器中出现 SQLite 锁竞争；对应单项及其后两轮完整回归通过。本次未调整公共资源采样逻辑，审查时建议关注高并发长事务场景。

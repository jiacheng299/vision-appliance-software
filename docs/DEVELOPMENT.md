# 开发与模块交接

2026-10-20 增量：智能体B端管理工作流、0003迁移、公开服务端口及独立演示已完成，见 `AGENTS_API.md`；初学者见 `AGENTS_BEGINNER_GUIDE.md`。真实推理、Run/Event存储、网关和报告引擎仍需团队接入，验收边界见 `AGENTS_IMPLEMENTATION.md`。

本轮实现范围和完整产品范围分别见 `superpowers/specs/2026-10-18-foundation-design.md` 与 `MASTER_SPEC.md`。原型保存在 `reference/`。

## 公共技术边界

前端为 Vue3/TypeScript/Naive UI，模块消费公开DTO/API，不操作别的模块的 Pinia 私有状态。七导航固定；智能体、任务创建和模型管理均已启用。成员 A 的服务适配与边界见 `MEMBER_A.md`。媒体HLS按需加载本地hls.js，无CDN。

后端模块化单体：API → service → repository/domain，公共 DTO 和 OpenAPI 见 `contracts/`。耗时媒体探测/预览在独立 Worker 中执行。所有文件位于 `VISION_VAR_ROOT` 下，返回 storage_key 或同源授权地址，不将绝对文件路径暴露给浏览器。

`docs/FOUNDATION_API.md` 为本轮冻结联调约定；修改字段时同步更新后端 Schema、OpenAPI、前端类型和契约测试。不能用 `any` 或双份私有契约掩盖不一致。

## A/B 接入

| 成员 | 后续模块 | 应复用的基础 |
| --- | --- | --- |
| 新人 A | 任务创建、模型管理 | source resolver、公共错误、上传/媒体、版本契约和状态组件 |
| 新人 B | 智能体管理、实况/历史/配置等 | agent/revision/run DTO、事件查询、媒体适配器和 WS |
| 集成负责人 | 看板、状态、来源、设置、迁移和联调 | 保持公共接口单一来源和模块边界 |

接入时才把对应侧栏项启用并注册路由；当前不要增加空壳页面占位。不要复用“草稿 Store”承载运行状态。历史 Run 绑定不可变已发布版本，保存草稿不能改动运行。

## 后续完整产品能力

本轮媒体预览和连接测试不等于模型推理、任务启动或验证准确率。完整产品的本地语言/多模态模型、专用模型配对、独立多路推理、需求确认与版本、反馈/漏报、复测和报告导出仍须按 MASTER_SPEC 的 FR/AC 实现与验收。

MediaMTX、GPU 和模型运行时缺失时必须如实显示未就绪；不要为了匹配原型示例而硬编码绿色状态。摄像头联调需要明确配置允许网段及真实设备，不能把不可达的地址报成已验证。

## 开发约定

使用工作分支与 PR；Schema 变更先沟通，Alembic 只维护单一迁移序列。不得提交 `.venv`、`node_modules`、客户媒体、凭据和 `var` 数据。公共仓库提交参考材料前应确认适合公开。

`.env.example` 仅说明可用环境变量，启动器不自动读取 `.env`；请在终端设置变量或使用部署工具传入。应用无需账号或登录；不创建默认管理员，也不保留可选登录模式。


## 整合版执行汇总

看板、运行概况及最近事件通过 `AgentServices.summary(actor_id)` 获取 `ExecutionSummary`，由运行/事件所有者负责授权及一致性。未实现或暂不可用的计数返回 null，不能返回伪造的零；运行与事件状态可独立未知。响应保留 data_origin，最近事件含 agent_id 以回到智能体详情。模拟实现与逐智能体查询共享同一份运行、事件状态；正式实现仍待公共执行器接入。参见 [整合预览](INTEGRATION_PREVIEW.md)。

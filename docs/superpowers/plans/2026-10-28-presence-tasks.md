# 人员在岗任务实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已发布模板创建可配置的真实 YOLO 在岗任务，支持 DeepSeek API 自动选择模板。

**Architecture:** 复用 AgentTemplate/Revision、ModelPair 与 AgentServices 合同。模板匹配只负责选择已有版本；本机独立执行模块负责真实视频推理、缺岗事件与统计。

**Tech Stack:** Vue 3、TypeScript、FastAPI、SQLite、httpx、YOLO11n ONNX、CPU 推理。

**Spec:** `docs/superpowers/specs/2026-10-28-presence-tasks-design.md`

## Global Constraints

- 默认最少一人、无人 30 秒、置信度 0.5；DeepSeek 阈值 0.8。
- 不上传视频；不提交 Key、数据库、模型文件；不伪造真实推理。
- 中文小步提交，每项 feat/fix 对应单独变更点；暂不 push。

### Task 1: DeepSeek 已发布模板匹配

- [ ] 先在 tests/backend/test_template_matching.py 写缺 Key、足够匹配、不足匹配、额外需求、未知 ID、超时与恶意响应测试，运行并记录失败。
- [ ] agent_templates/matching.py 实现 `DeepSeekTemplateMatcher(config).match(requirement_text, candidates)`；候选不含文件或凭据。现有 routes.py 新增 `POST /agent-templates/match` 与 `GET /agent-template-matcher`。
- [ ] 返回 `{status, template_id, template_revision_id, confidence, reason, uncovered_requirements, provider, model}`；status 仅 matched/no_match。Config 添加 SecretStr Key、模型名和阈值。
- [ ] 用 httpx MockTransport 证明响应校验，跑邻近模板测试，独立提交 `feat(模板): 接入DeepSeek已有模板匹配`。

### Task 2: 任务创建两种入口

- [ ] frontend/tests/template-task-create.test.ts 增加手动/自然语言匹配、拒绝不足匹配、默认参数、默认视频与无默认视频必选、修改失效测试，先复现失败。
- [ ] templatesApi.ts 增加上述 match/status DTO；TemplateTaskCreatePage.vue 实现选择方式和后续视频参数表单，保留原校验、确认、草稿、幂等请求。
- [ ] 任务模型只读展示，模板可新建修改模型；未匹配时链接智能体模板创建，不调用旧多模态规划接口。
- [ ] 跑前端专项与全量，独立提交 `feat(任务): 重写模板选择与参数配置流程`。

### Task 3: 真实 YOLO 模型准备与登记

- [ ] tests/backend/test_yolo_detector.py 验证 letterbox/person 过滤/NMS/坐标还原及模型错误；tests/deploy 验证安装注册幂等和校验失败。
- [ ] models/yolo.py 提供 `YoloPersonDetector(path, confidence=.5).detect(frame)`，返回归一化 person box 列表。
- [ ] deploy/scripts/setup_presence.py 从官方权重生成 ONNX，通过现有 model-files/models/verify 与 agent-templates API 注册真实模型及默认在岗模板；保持历史数据不变。
- [ ] 推理依赖锁定、来源和校验记录，真实图片及录像运行证明，独立提交 `feat(模型): 接入YOLO11n人员检测模型`。

### Task 4: 真实在岗任务执行

- [ ] backend/app/modules/local_execution/ 独立拥有 Run、Operation、Event、事件证据与线程/进程生命周期，迁移新增表；测试读帧失败不报、无人计时、恢复重置、停止、幂等与重启回收。
- [ ] 实现 AgentServices 公开 runtime/events/media/summary，组合入口保留 RegistryCapabilities 与模型目录，mock 模式仍独立。
- [ ] 模板默认视频字段、默认在岗参数与固定模型版本保护用迁移/合同兼容方式实现；证据使用原受控媒体路径，摄像头遵守网段和网关限制。
- [ ] 真实人员录像验证至少 person>0；无人录像越阈值产生 real 事件，断流不产生缺岗，独立提交 `feat(监测): 执行人员在岗检测与缺岗报警`。

### Task 5: 整体交付

- [ ] 重新生成 OpenAPI/TypeScript 类型，后端与部署全量、前端全量及生产构建。
- [ ] 本机 DeepSeek Key 配置与真实匹配；没有 Key 时保留此项未完成，不使用 Mock 替代。
- [ ] 浏览器验证手动/自动选模板、模型可见、默认视频、参数、运行和真实事件，保存忽略目录截图。
- [ ] 更新 README、部署文档和逐提交验收记录；独立中文 docs 提交，保持工作区干净，不 push。

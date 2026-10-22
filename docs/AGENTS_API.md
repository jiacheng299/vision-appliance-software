# 智能体管理 API 与公共服务交接

更新：2026-10-22。字段以 `contracts/openapi.json` 为准，前端类型由它生成。使用 snake_case、UTC、UUID 和统一错误信封。工作台无账号与角色，页面、API、媒体和事件订阅无需登录、Cookie 或 CSRF Token；写入保留同源来源校验。

## 当前版本功能门禁

人工核查暂未开放：前端入口置灰，事件详情只读，反馈和人工漏报写端点默认503 `feature_not_available`。历史数据及只读接口保留。Config.manual_review_enabled默认false；测试仅为保留延期实现的回归覆盖而显式打开，不表示生产可用。

区域采用标准闭合多边形顶点列表，首点不重复附在末尾；编辑器必须点击起点完成闭合才可保存，约10个屏幕像素内的相邻误点吸附合并。后端保留简单多边形、面积、范围和重复点校验，不用固定归一化容差擅自改写历史区域。

## 数据所有权

B拥有 Agent、AgentRevision、AgentValidation、AgentConfirmation、AgentCommand。配置为受校验 channels[] JSON，稳定channel_id，最多16路。Run、Event、Feedback、MissedAnnotation、Model、MediaSession、ExportJob 由公共服务拥有；B不写其数据库。

latest_revision是最新编辑版本，desired_revision_id是最后确认发布的期望版本；每路Run.revision_id才是实际运行版本。应用部分失败允许混合版本。0003_agent_workflow增量升级原库，不清空旧配置；发布快照只读，归档可恢复。

## REST接口

省略 `/api/v1`。写操作无需账号凭据；幂等写操作的Idempotency-Key以OpenAPI声明为准。同一工作空间同键同请求沿用原结果，异请求409；PATCH和归档使用row_version防覆盖。

| 方法/路径 | 行为 |
|---|---|
| GET/POST /agents | 分页搜索、源/场景/状态/归档/排序过滤，创建 |
| GET/PATCH /agents/{id} | 详情、更新名称/说明 |
| POST /agents/{id}/revisions | 克隆草稿 |
| GET/PATCH /revisions/{id} | 读取/保存；已发布拒改 |
| POST /revisions/{id}/validations | 评估并保存不可变结果 |
| GET /validations/{id} | 结果、限制、hash、有效期 |
| POST /revisions/{id}/confirmations | 明确确认限制、发布，不启动 |
| GET /agents/{id}/workspace | 实际每路Run、服务可用性和聚合状态 |
| POST /agents/{id}/run-groups | 启动所选通道，202返回作业 |
| POST /agents/{id}/revision-applications | 按通道停旧启新，202返回作业 |
| POST /agents/{id}/runs/{run_id}/stop | 停止/取消Run，202返回作业 |
| GET /agents/{id}/operations/{operation_id} | 每路处理进度和结果 |
| POST /agents/{id}/archive、/restore | 归档/恢复，活动及待启动工作阻止归档 |
| GET /agents/{id}/events | 历史/筛选/分页及增量游标 |
| GET /agents/{id}/event-stream | SSE增量、重放、resync |
| GET /agents/{id}/events/{event_id} | 事件、证据及反馈历史 |
| POST /agents/{id}/events/{event_id}/feedback | 按row_version追加正确/误报和理由 |
| GET/POST /agents/{id}/missed-annotations | 人工漏报，绑定实际Run |
| POST /agents/{id}/runs/{run_id}/playback | 申请受保护播放会话 |
| DELETE /agents/{id}/playback-sessions/{session_id} | 释放播放资源 |
| POST /agents/{id}/events/{event_id}/evidence/{evidence_id}/access-sessions | 申请证据会话 |
| POST /agents/{id}/retests | 从基准Run复制对应通道到草稿 |
| GET /agents/{id}/comparisons | 原始计数与可比性限制 |
| POST /agents/{id}/exports | 冻结Run/内容快照，创建异步导出 |
| GET /agents/{id}/exports/{export_id} | 进度与下载入口 |
| POST /agents/{id}/exports/{export_id}/cancel、/retry | 取消/按原快照新建重试 |
| GET /agents/{id}/exports/{export_id}/download | 鉴权下载成功的浏览器作业 |
| GET /agent-services/capabilities | 模型/模板版本、规则、限制、指纹 |
| GET /agent-services/export-destinations | 允许的主机目录别名，不暴露真实路径 |
| GET /agent-services/references | 按source_id或model_id/model_version分页查引用 |
| GET /agent-environment | 真实/演示标识，直接可读 |

请求示例见 `/api/docs`。配置支持requirement_text、target、rule、duration_seconds、source_id、capability_ref、regions及录像区间。允许不完整草稿，执行前必须验证。ROI为0–1归一化多边形，拒绝退化、自交、越界；录像区间必须成对且不超过已知时长。

## 验证、确认与执行

1. 保存取得Revision.row_version。
2. 验证使用row_version，返回executable / clarification_required / unsupported / insufficient_evidence，含完整缺失项、限制、模型、配置hash、能力指纹及10分钟有效期。
3. 确认传row_version、validation_id、config_hash、limitations_acknowledged=true。再次检查源快照、配置、模型指纹，保存确认与发布时间。
4. 启动/应用传revision_id、channel_ids、expected_active_run_ids。Run变化时执行服务应返回冲突，刷新后重新确认。
5. 查询Operation，实际Run状态才决定是否运行，排队不算运行中。

能力调用在写锁外，保存前复核版本防竞态。保存草稿使旧验证失效。过期发布版需克隆再评估。操作回执可在能力服务下线时取回；执行提供方须独立幂等，覆盖跨进程崩溃间隙。

## 提供方接入

接口类：backend/app/modules/agents/integrations.py::AgentServices，DTO在contracts.py。组合根注入：

```python
from app.main import create_app
from app.modules.agents.integrations import AgentServices

class ProjectAgentServices(AgentServices):
    # 按团队真实服务实现 catalog/assess/runs/submit/...。
    pass

app = create_app(agent_services=ProjectAgentServices())
```

这是接线示例，不是真实推理实现。生产可新增factory，启动指向它。默认提供方明确503，各服务可独立故障，页面保留配置和已取得的历史。

联调约定：

- 能力：不可变模型/模板版本、指纹、支持范围、真实评估，不能默认支持所有需求。
- 执行：工作空间归属、通道原子锁、expected_active_run_ids比较、幂等、资源队列、停旧启新、心跳/进度/结束原因。Run必须带与发布版一致的config_snapshot/source_snapshot。停旧失败保留旧Run；新启失败如实报告。
- 归档：set_archived原子拒绝活动和待启动工作并阻止未来启动，恢复解禁，不能无锁先查后归档。
- 事件：绑定实际Run/版本/源/通道，稳定历史及单调增量游标、row_version、重放/resync、追加反馈与冲突、真实证据状态。人工漏报不计系统检出数；无录像摄像头不能接受假回放区间。
- 媒体：同源/api/v1下鉴权文件/HLS/WHEP WebRTC，会话过期续期与释放；ROI、目标框及观测时间。media_origin_ms映射播放位置，recording_available和边界须真实。过时目标框隐藏；hls.js本地打包，无CDN。
- 导出：冻结快照、真实内容/进度、取消、原快照重试、鉴权下载、有限目录别名。不能接受任意主机路径，缺证据/失败不能包装为完整正式报告。
- 权限：所有方法收到actor_id，提供方验证源、Run、事件、会话、证据、导出的资源访问权。B网关的Agent/版本关联检查不能替代该权限检查。

引用查询runtime_checked=false、active_run_ids=null表示运行未知，不能当作零活动引用；归档/删除方仍需要公共运行服务的原子保护。

SSE先REST快照，再用stream_cursor订阅；支持after游标、心跳、会话过期和重放。前端按ID/row_version去重，resync重新REST。历史为动态视图，筛选变化重置游标。

## 演示隔离

只有VISION_AGENT_DEMO=true启用DemoServices，数据库根自动附加agent-demo。普通模式不接受Mock提供方注入（测试例外），/agent-demo/seed和/scenario普通模式404。演示脚本另选独立根及8004端口。

Run/Event/反馈/作业仅内存，重启清空；配置/确认持久化。返回data_origin=mock，常驻UI标识。下载仅带警告JSON，不是正式报告；主机模拟不实际写文件。测试独立临时库，凭据和产物不入Git。

## 免登录整合与迁移

`actor_id` 使用固定工作空间标识 `workspace`，仅供提供方关联和幂等收据使用，不代表用户、角色或认证凭据。迁移 `0004_workspace_actors` 移除智能体表到旧 users 表的外键，保留历史标识、版本、确认和回执；不创建账号，不删除旧数据。升级前备份数据库。未产生无账号新记录时可降级；产生新记录后回滚应恢复升级前备份，降级会明确拒绝丢弃记录。

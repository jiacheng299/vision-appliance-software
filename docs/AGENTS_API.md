# 智能体草稿 API：第一轮实现与协作草案

日期：2026-10-20。继承 `FOUNDATION_API.md` 的 Cookie、CSRF、snake_case、UTC、UUID 和错误格式。
这是已实现的草稿 API；完整执行契约仍需 A/B 和负责人评审。接口 Schema 以生成的 `contracts/openapi.json` 为准。

## 范围与数据所有权

- B 拥有 `Agent`、`AgentRevision`、幂等回执 `AgentCommand`。
- 一个 Agent 的配置包含 `channels[]`，首轮支持配置多路，但不代表真实并发推理已支持。
- 每个 channel 有稳定 `channel_id`；克隆配置保留 channel_id，新增通道生成新 UUID。
- 首轮通道配置保存在带 `schema_version` 的受校验 JSON 内。没有提前创建 Run、Event、Model 等其他模块的权威数据。
- 视频源通过 sources 模块公开只读查询解析，不读凭据、不写 Source 表；绑定不存在/已归档新源返回 422。旧配置保留已归档源引用，仍可查看和继续编辑其他字段。
- 本轮没有 active/desired revision 指针，`latest_revision` 仅表示编号最大的草稿版本，不表示生效版本。

## 已实现接口

所有路径带 `/api/v1`。登录账号可以读；admin/operator 可以写，viewer 不可写。写操作必须有 `X-CSRF-Token`。

| 方法与路径 | 内容 |
|---|---|
| GET `/agents?q=&source_id=&cursor=&limit=24` | 名称/说明搜索、最新版本的视频源过滤；按 updated_at DESC、id DESC 排序；limit 1–100 |
| POST `/agents` | 原子创建 Agent + v1 草稿，返回 201 和 AgentDetail |
| GET `/agents/{id}` | 详情、最新版本、全部版本（新到旧）及明确的能力限制 |
| PATCH `/agents/{id}` | `{name,description,row_version}` 更新非执行元数据 |
| POST `/agents/{id}/revisions` | `{base_revision_id,row_version}` 克隆版本，返回 201 和 RevisionDTO；row_version 来自 Agent |
| GET `/revisions/{id}` | 读取某个版本 |
| PATCH `/revisions/{id}` | `{config,row_version}` 整体替换该草稿的配置；row_version 来自 Revision |
| POST `/revisions/{id}/validations` | 已授权用户收到明确 503 `capability_service_unavailable`，不伪造验证成功 |

创建和克隆都必须传 `Idempotency-Key`（1–128 字符）。同一用户同键同请求返回首次响应；异请求返回 409。
回执和创建动作同事务保存，短事务加 SQLite 写锁。首轮回执不自动过期；后续需制定保留策略。
重复操作仍返回首次 201。一次真正的新创建应生成新的键。克隆回执的重试可以绕过旧 row_version 检查以返回原结果。

分页采用 `(updated_at,id)` 不透明游标，筛选变更应丢弃旧游标。列表是动态列表，不承诺跨页快照；更新后可刷新重新排序，前端追加时按 id 去重。

## 最小创建示例（同学 A 可调用）

```http
POST /api/v1/agents
Content-Type: application/json
X-CSRF-Token: <当前会话 CSRF>
Idempotency-Key: <为此次创建生成的 UUID>
```

```json
{
  "name": "北门监测",
  "description": "现场验证草稿",
  "config": {
    "schema_version": "1.0",
    "channels": [{
      "name": "北门",
      "source_id": "替换为真实视频源ID",
      "requirement_text": "有人停留超过30秒时报警",
      "duration_seconds": 30
    }]
  }
}
```

也允许 config.channels 为空，保存未完成草稿。`channel_id` 可由调用方提供或由后端生成。
返回 `id`、`latest_revision.id` 后跳 `/agents/{id}/config`。
**不要在创建返回后宣称任务已启动。** 首轮无 confirmations/run-groups/operations 接口。

SDK 位于 `frontend/src/modules/agents/api.ts`，导出类型直接引用 OpenAPI 生成类型。A 可先依赖 REST/OpenAPI，不引用 B 页面内部状态。
智能体写请求使用标准 JSON Unicode 转义编码，解码后的 DTO 不变；用于兼容本地浏览器/代理的中文传输。JSON 之外不发送媒体内容。

## 配置字段

`RevisionConfig`：schema_version 固定 1.0，channels 最多 16 路（配置数量限制，不是硬件性能承诺）。

每一路包含：

- channel_id、name、source_id（可空）。
- requirement_text、target、rule：未完成草稿允许空值，不据此宣称支持某场景。
- duration_seconds：可空，1–86400 整数秒，拒绝 bool。
- start_media_ms/end_media_ms：必须成对，整数毫秒，开始早于结束，仅可用于已知时长录像，不能越界。
- regions：最多 32 个，每个 id 唯一；3–64 个归一化点，坐标 0–1，不能重复顶点、共线零面积、自交或边重叠。
- capability_ref：可空，或包含 model_id/model_version/template_id/template_version。首轮只保存待校验引用，不能据此发布执行。

全层 schema 拒绝未知字段。禁止传入凭据、任意执行代码或任意开放参数字典作为配置扩展。

## 版本与冲突

草稿 `draft` 可以编辑；`published` 的写保护已实现，但首轮没有发布接口。发布只能由未来的验证+确认流程完成。
复制新版本不修改原版本的配置。未发布的旧草稿仍允许显式编辑；已发布快照永久只读。
PATCH 必须传最新 row_version；发生冲突返回 409 `revision_conflict`，不执行覆盖。
保存任一版本会递增 Agent.row_version，版本自身的 row_version 独立递增。
克隆需要 Agent 的最新 row_version，可从详情 GET 获取。
运行中的编辑/应用功能尚未接入；未来增加验证、确认和指针前，不能复用 `latest_revision` 充当实际运行版本。

## 错误与降级

沿用 `{error:{code,message,details,retryable,request_id}}`，无成功 data 包装。
401 未登录；403 权限/CSRF；404 资源缺失；409 冲突/不可变/幂等键冲突；422 格式、源或区间错误；503 未接入校验。
源、媒体服务异常不会删除已有智能体和配置；页面可保存未绑定源的草稿。
前端在请求结果确认前不切换成功状态。发生网络超时应保留创建/克隆幂等键重试；不要无限重试 409。

## 后续契约工作（本轮未实现）

- 模型能力目录、模型/模板校验、requirements 评估的公开服务接口。
- 验证 hash/有效期、Confirmation、发布和不可变模型/源快照。
- RunController、run-groups、revision-applications、operations，逐路锁、幂等控制和失败补偿。
- agent/run 的 WS topic、真实事件、证据和反馈/漏报 API。
- 媒体会话刷新与回收、WebRTC/HLS 播放器、检测框/区域叠加。
- 复测、导出、归档及真实源/模型被引用时的跨模块保护。
- 大规模数据时将当前 JSON 草稿通道规范化，避免列表按源过滤需要读取配置；分页列表还需优化当前逐 Agent 读取版本的查询。

数据库升级为 `0001_foundation -> 0002_agents`，不修改或重建已有基础表。迁移仍为单链。

# Foundation API：联调约定 v1

2026-10-20：在不改变现有基础端点的前提下新增智能体草稿 API，详见 `AGENTS_API.md` 和生成的 OpenAPI。原 `/runs`、`/events` 仍为空列表扩展点，没有真实监测执行。

实现者遇到缺项可增字段，不擅自改已有字段；变更先更新此文件并通知集成人。

所有路径以 `/api/v1` 开头。同源 Cookie `vision_session`；CSRF Cookie `vision_csrf` 可被 JS 读取，所有已登录写操作加 `X-CSRF-Token`。初始化/登录除外。响应错误 `{error:{code,message,details,retryable,request_id}}`。ISO8601 UTC 时间，ID 为字符串 UUID。

## Auth

- GET `/auth/setup-status` → `{initialized:boolean}`。
- POST `/auth/setup` body `{username,password}` → User，首次建立管理员并登录。密码至少 12 字符。
- POST `/auth/login` 同 body → User；POST `/auth/logout` → 204。
- GET `/auth/me` → User `{id,username,role:'admin'|'operator'|'viewer'}`。

## Sources

Source：`{id,name,kind:'file'|'camera',status,created_at,updated_at,row_version,observed_at:null|string,address:null|string,width:null|number,height:null|number,fps:null|number,duration_ms:null|number,size_bytes:null|number,sha256:null|string,preview_url:null|string,thumbnail_url:null|string,error_code:null|string,error_message:null|string}`。address 必须脱敏，绝不返回密码。状态 file 为 uploading/probing/transcoding/ready/failed/canceled，camera 为 unverified/connecting/online/disconnected/reconnecting/failed。

- GET `/sources?q=&kind=&status=&limit=100` → `{items:Source[],next_cursor:null|string}`。
- POST `/sources` body `{name,kind:'camera',address,username?:string,password?:string}` → Source。
- GET `/sources/{id}` → Source。
- PATCH `/sources/{id}` body `{name?,address?,username?,password?,row_version}` → Source；旧版本 409。
- 凭据原样保留首尾空白；PATCH 未提供 username/password 表示保留，显式空字符串表示清空。单独提供的凭据字段覆盖 URL userinfo；新 address 不带 userinfo 时保留既有凭据，带 userinfo 时以其替换相应字段，随后再应用显式字段。前端普通保存不提交未修改的空密码；清除凭据须显式动作。
- POST `/sources/{id}/archive` → 204（主规格使用归档，页面不宣称物理删除）。
- POST `/uploads` JSON `{filename,size_bytes}` → Upload。
- PUT `/uploads/{id}/chunks/{n}` body 原始 bytes，`Content-Type:application/octet-stream` → Upload；首块 n=0，重传同字节幂等。
- POST `/uploads/{id}/complete` JSON `{name?:string}` → Upload，后台探测，未完成不得显示成功。
- GET `/uploads/{id}` → Upload `{id,state,received_bytes,size_bytes,source_id:null|string,error_code:null|string,error_message:null|string}`。
- Upload.state 固定为 uploading/probing/transcoding/ready/failed/canceled；每块最多 8 MiB，前端默认使用 4 MiB。按 n=0 递增，重复同块同内容允许，异内容冲突。只有 ready 才显示导入完成；complete 返回 source_id 或异步受理不能当作成功。上传时以 received_bytes/size_bytes 显示传输进度，探测/转码不编造进度百分比。
- DELETE `/uploads/{id}` → 204。
- POST `/sources/{id}/tests` → `{id,state,source_id}`；GET `/source-tests/{id}` → `{id,state,source_id,error_code?,message?}`。测试不得假报鉴权原因。
- POST `/sources/{id}/preview-sessions` → `{session_id,protocol:'file'|'hls'|'webrtc',playback_url,expires_at}`。缺少网关时 503。
- GET `/sources/{id}/media` 与 `/sources/{id}/thumbnail` 同会话保护；预览 URL 返回本地 API 相对 URL。

## Dashboard / Runtime / Logs / Events

- GET `/dashboard` → `{counts:{sources_total,sources_online,active_runs,today_events},sources:Source[],recent_events:Event[],task_summary:{running,completed,waiting}}`。
- GET `/runtime/overview` → `{observed_at,cpu_percent,memory_percent,gpu_percent:null|number,disk:{used_bytes,total_bytes,free_bytes},sources:{total,online},runs:{running,completed,failed},services:Service[],models:[],workers:[],history:RuntimeSample[]}`。Service `{key,name,status:'ready'|'unavailable'|'degraded',message,observed_at}`；RuntimeSample `{observed_at,cpu_percent,memory_percent,gpu_percent:null|number}`。
- GET `/logs?level=&q=&limit=100` → `{items:Log[],next_cursor:null}`；Log `{id,occurred_at,level,module,message}`（脱敏）。
- GET `/events` → `{items:Event[],next_cursor:null}`。Event 公共形状 `{id,event_type,source_id,source_name,run_id,revision_id,occurred_at:null|string,start_media_ms:null|number,reason,evidence_status,review_status}`。本轮无推理创建者，空列表合法。
- GET `/runs` → `{items:[],next_cursor:null}`（留给 A/B 接入；本轮不伪造运行）。
- GET `/health/live` → `{status:'ok'}`，GET `/health/ready` 展示各依赖状态，不要求模型未注册就将 API 本身判死。
- WebSocket `/ws`：同 Cookie 验权。接收 `{type:'subscribe',topics:['runtime'],last_sequence?:number}`；消息 `{schema_version:'1.0',event_id,sequence,type,occurred_at,aggregate_id,payload}`。本轮 runtime/source 通知，补偿不足返回 resync_required，前端重新 REST 拉快照。不得用 WS 发送视频帧。

## Settings

GET `/settings/{section}` → `{section,values:Record<string,unknown>,row_version}`；PATCH 同路径 body `{values,row_version}` → 同形状。校验并发旧版本 409，未知字段拒绝。管理员可写。

section 与值：
- general：`system_name`、`timezone`（默认 Asia/Shanghai）、`auto_reconnect:boolean`、`language:'zh-CN'`、`theme:'light'`。
- storage：`retention_days:number`、`max_upload_mb:number`、`export_formats:string[]`。目录位置只读由后端有效配置提供，不接受用户任意服务主机路径。
- resources：`max_concurrent_jobs:number`、`connection_timeout_seconds:number`、`reconnect_attempts:number`。
- security：`session_timeout_minutes:number`、`camera_allowed_networks:string[]`（可控私网 CIDR，默认仅本机，不静默放通所有地址）。
- diagnostics：只读 `{version,media_gateway_configured:boolean,ffmpeg_available:boolean,worker_online:boolean}`。

全局配置通过环境变量/部署配置，记录来源；前端不把未接入许可证/模型运行时显示成已授权/已加载。

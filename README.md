# 视觉一体机应用软件

> 2026-10-27 最新结构：智能体卡片代表可复用的业务模板；任务选择已发布模板并固定原版本，每个新任务选择一路视频。配置项由开发者维护，用户只能从已有目录选择。详见 [模板与任务操作说明](docs/AGENT_TEMPLATES_GUIDE.md)。历史多通道与多视频任务完整保留。


本地部署的视觉监测工作台，采用 Vue 3 + TypeScript + Naive UI 与 FastAPI + SQLite。已有快速监控看板、运行状态、视频源管理、系统设置及公共基础；智能体管理包含配置、验证发布、分路操作、事件核查、复测与导出工作流及独立演示。

任务创建（`/create`）支持手动选择已发布模板，或由 DeepSeek API 将自然语言需求匹配到已有模板；匹配不足时明确提示创建/定制模板。真实模板“人员在岗监测”和“人员区域入侵监测”固定绑定经过校验的 YOLO11n CPU ONNX 能力，并提供持久化 Run/Event、断流重连与截图证据。安装与测试见 [人员在岗监测接入说明](docs/PRESENCE_MONITORING.md) 和 [人员区域入侵接入说明](docs/INTRUSION_MONITORING.md)。正式报告引擎仍待接入。

2026-10-22 更新：详情顶部使用分层概览与卡片导航；人工核查当前版本暂未开放，系统事件仍可只读查看。配置抽屉支持遮罩关闭；划区须点击起点闭合，相邻约10像素误点自动合并。

初学者先看 **[智能体操作与代码入门](docs/AGENTS_BEGINNER_GUIDE.md)**；协作接口见 [智能体 API 与接入约定](docs/AGENTS_API.md)，验证与限制见 [开发记录](docs/AGENTS_IMPLEMENTATION.md)。

练习完整流程：安装完成后双击 **start-agents-demo.cmd**，打开 http://127.0.0.1:8004/agents ，点击“创建模拟火灾模板”，再使用模板创建任务。演示库独立、全程标识模拟；下载仅为带警告的JSON操作快照，不能当正式报告。重启后模拟运行/事件重置，配置保留。

## 安装与启动（Windows x64）

1. 安装 Python **3.13 64 位**和 Node.js **22.12+ 或 24 LTS**。
2. 克隆仓库或完整解压 ZIP，放到自己有写权限的目录。
3. 双击 `setup.cmd`。它创建项目 `.venv`、安装后端锁定依赖及前端 npm 锁定依赖，构建静态页面，并下载/校验本地 FFmpeg、FFprobe。首次安装需要联网；下载失败不会作为成功继续。
4. 在项目根目录运行 `python app.py`，自动启动网页、媒体 Worker 和三个本地测试视频源，打开 **http://127.0.0.1:8000**。保持终端开启，按 Ctrl+C 统一停止。首次准备测试视频需要联网，公开直播可用性取决于上游。`start.cmd` 仍可仅启动应用；`start-camera-lab.cmd` 可单独启动视频源。
5. 打开后直接进入工作台，无需注册、创建账号或登录。应用不设置用户、角色和登录模式。

网页、API 和媒体同源，独立 Worker 处理文件探测、预览转码和连接诊断。关闭启动窗口或按 Ctrl+C 会停止本次启动的进程。日志在 `var/logs/`，数据库在 `var/vision.db`，用户文件和凭据均在受控 `var/`，不入 Git。

资源设置中的并发数保存后，检测调度器会在下一次调度检查（最多约 3 秒）自动应用，无需重启；已有排队任务也会重新调度。降低上限不会强行停止正在运行的任务，而是等待其结束后按新上限启动后续任务。

任务详情和智能体模板的关联任务列表提供“删除任务”。确认后先停止该任务的检测，再永久删除任务配置、运行历史、告警和证据截图；所属模板、共用模型、视频源与原始录像不受影响。正在停止的任务若未能及时退出，会拒绝删除，避免后台仍在写入已删除任务。模板自身的归档功能保留。

换端口启动：

```powershell
.\start.cmd --port 8002
```

系统环境有自备 FFmpeg/FFprobe 时可设置 `VISION_FFMPEG` 和 `VISION_FFPROBE`。`deploy/components.json` 固定本轮媒体工具来源与哈希；本地组件许可随解压保留。可把 `.env.example` 中需要的变量复制到 Git 忽略的 `.env.local`；应用会自动读取它。

前端生产资源由 API 服务本地提供，无运行时 CDN 和外部字体。视频与 YOLO 推理留在本机；只有用户主动选择“自然语言匹配”时，需求文本和已发布模板的公开摘要会发送到 DeepSeek，视频、视频地址、模型文件和凭据不会发送。手动选模板与本地推理可断网使用。

## 整合版本

整合版本包含视频源与看板、智能体创建/播放优化，以及成员 A 的双模式任务与模型管理。整合来源、冲突处理、公共汇总端口和验证边界见 [整合交付说明](docs/INTEGRATION_PREVIEW.md)。运行方式沿用下文。

## 成员 A：任务创建与模型管理

`/create` 可手动选择已发布模板，也可输入自然语言由 DeepSeek 匹配。匹配结果固定到当时的发布版本；没有足够匹配的模板时不会启动其他模型。选择模板后配置视频源、区域、录像范围及模板开放的条件值，验证通过后确认启动。模板发布新版本不更新旧任务。`?draft=<agentId>` 可继续编辑原任务。

`/models` 提供本地惰性文件导入与 SHA-256、模型/模板一一绑定、新版本、校验及引用保护归档。YOLO11n 只有在官方权重摘要、固定导出清单、ONNX 摘要、能力声明和黑图推理自检全部通过后才显示为可用；任意上传文件不会自动获得执行资格。

沿用 `start-agents-demo.cmd` 可练习模拟流程；真实人员在岗与区域入侵流程分别按 [在岗接入说明](docs/PRESENCE_MONITORING.md) 和 [入侵接入说明](docs/INTRUSION_MONITORING.md) 准备并登记模型。两项能力可复用同一份受控 YOLO11n ONNX 文件，但使用独立的模型能力引用和业务模板。模拟数据继续使用独立目录，不会混入真实运行记录。

## 当前可验收内容

- 无账号工作台：页面、业务 API、媒体和 WebSocket 直接可用；保留浏览器同源写入检查、路径限制及摄像头凭据保护。
- 真实 CPU、内存和磁盘指标；YOLO11n CPU ONNX 就绪后显示本地模型运行时可用，GPU 和未接入服务仍显示未知/未就绪。
- 本地录像分块上传、真实信息探测、SHA-256、预览转码、筛选、编辑、归档和同名文件隔离。
- 摄像头配置、凭据加密和脱敏、网段限制及连接诊断；仅 RTSP 响应不作为解码/上线证明，网关未就绪时明确不能播放。
- 分类设置保存、字段校验和版本冲突保护；重启与刷新保留数据。
- 七导航与响应式界面；新安装没有虚构的运行、告警或授权数字。
- 智能体列表、详情、多路配置、版本复制、验证确认发布、归档；刷新持久化、冲突保护及幂等。
- 人员在岗和人员区域入侵任务真实执行、分路启停、播放、缺岗/入侵事件及截图证据；反馈、历史复测和正式报告仍按功能状态明确提示。

具体验收步骤、运行记录与限制见 **[验收文档](docs/ACCEPTANCE.md)**。开发和另外两位成员接入请看 [开发交接](docs/DEVELOPMENT.md) 与 [API 约定](docs/FOUNDATION_API.md)。

## 开发

### 摄像头测试资源

需要真实直播或模拟摄像头时，在项目已启动后双击 `start-camera-lab.cmd`。它准备并运行两路 MOT17 录像循环与一路大学公开直播，提供本机 RTSP 输入和独立网页播放器，并通过 API 登记视频源。录像循环有明确模拟名称，不代表模型推理。地址、重启方式、当前工作台预览边界及代码说明见 [摄像头资源准备](docs/CAMERA_LAB.md)。

后端（仓库根目录）：

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
```

独立 Worker（另开终端，同样设置 PYTHONPATH 和媒体工具环境变量）：

```powershell
.\.venv\Scripts\python.exe -m worker.supervisor
```

前端开发：

```powershell
cd frontend
npm ci
npm run dev
```

前端开发服务在 5173，把 `/api/v1` 和 WebSocket 代理到 8000；生产运行用 `start.cmd` 同源服务。API 文档在 `/api/docs`，OpenAPI 在 `/api/openapi.json`。

## 验证命令

实时任务稳定性验证：先在网页启动任务，再运行以下命令（替换任务 ID）。脚本固定跟踪同一运行至少十分钟，检查推理观测是否更新、实际 HLS 分片是否可读，并在运行中触发两次摄像头连接检测；失败即停止，不会重启任务掩盖异常。结果写入本机 `var/`，不提交用户运行数据。

```powershell
python deploy/scripts/soak_monitoring.py --agent <任务ID> --seconds 600 --output var/monitoring-soak.json
```

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
.\.venv\Scripts\python.exe -m pytest tests/backend -q
.\.venv\Scripts\python.exe -m unittest discover -s tests/deploy -v
cd frontend
npm test
npm run build
```

真实媒体测试需设置 `VISION_FFMPEG` 和 `VISION_FFPROBE`，验收文档会区分已执行和依赖未具备的检查。契约变更后先用 `contracts/generate.py` 导出 OpenAPI，再在前端运行 `npm run generate:api` 更新公共类型。

## 目录

```text
frontend/       # Vue 页面、智能体工作流、路由、API、媒体和实时状态公共组件
backend/        # FastAPI 模块、数据模型、持久层和 Alembic 迁移
worker/         # 独立媒体作业处理器和心跳
contracts/      # OpenAPI、生成器和契约示例
deploy/         # 本地组件清单、安装和启动管理脚本
tests/          # 后端与部署测试；前端测试位于 frontend/tests
docs/           # 主规格、原型、设计、计划、API、开发和验收说明
var/            # 数据库、媒体、机密、日志及工具，仅运行时生成
```

新成员按 [CONTRIBUTING.md](CONTRIBUTING.md) 使用分支/PR 协作，不修改其他模块的私有 Store 或跨模块裸写表。仓库公开，真实视频、运行数据和密钥不提交。

### 看板视频墙

快速监控看板最多显示 4 路视频，自动静音播放摄像头直播与已就绪录像，录像循环播放。未就绪录像及断开的摄像头显示状态占位，恢复在线后自动加载。视频源详情保留手动打开预览；离开页面时播放器释放视频与 HLS 连接。

验证：前端全量 44 项测试通过，生产构建成功；本机浏览器实测录像和 RTSP 转 HLS 直播均自动播放。

本次接入、状态验证及视频墙修复的逐次提交说明与验证结果见 [摄像头变更记录](docs/CAMERA_CHANGELOG.md)。

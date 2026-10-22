# 视觉一体机应用软件

本地部署的视觉监测工作台，采用 Vue 3 + TypeScript + Naive UI 与 FastAPI + SQLite。已有快速监控看板、运行状态、视频源管理、系统设置及公共基础；智能体管理包含配置、验证发布、分路操作、事件核查、复测与导出工作流及独立演示。

任务创建和模型管理仍保留禁用入口。智能体已完成 B 端页面、持久化配置与公开服务适配器；真实模型、Run/Event、媒体网关和正式报告引擎需由团队公共服务接入。默认真实模式缺服务时明确不可用。完整需求保存在 [主规格](docs/MASTER_SPEC.md)。

初学者先看 **[智能体操作与代码入门](docs/AGENTS_BEGINNER_GUIDE.md)**；协作接口见 [智能体 API 与接入约定](docs/AGENTS_API.md)，验证与限制见 [开发记录](docs/AGENTS_IMPLEMENTATION.md)。

练习完整流程：安装完成后双击 **start-agents-demo.cmd**，打开 http://127.0.0.1:8004/agents ，点击“加载双路模拟样例”。演示库独立、全程标识模拟；下载仅为带警告的JSON操作快照，不能当正式报告。重启后模拟运行/事件重置，配置保留。

## 安装与启动（Windows x64）

1. 安装 Python **3.13 64 位**和 Node.js **22.12+ 或 24 LTS**。
2. 克隆仓库或完整解压 ZIP，放到自己有写权限的目录。
3. 双击 `setup.cmd`。它创建项目 `.venv`、安装后端锁定依赖及前端 npm 锁定依赖，构建静态页面，并下载/校验本地 FFmpeg、FFprobe。首次安装需要联网；下载失败不会作为成功继续。
4. 双击 `start.cmd`，打开 **http://127.0.0.1:8000**。
5. 打开后直接进入工作台，无需注册、创建账号或登录。应用不设置用户、角色和登录模式。

网页、API 和媒体同源，独立 Worker 处理文件探测、预览转码和连接诊断。关闭启动窗口或按 Ctrl+C 会停止本次启动的进程。日志在 `var/logs/`，数据库在 `var/vision.db`，用户文件和凭据均在受控 `var/`，不入 Git。

换端口启动：

```powershell
.\start.cmd --port 8002
```

系统环境有自备 FFmpeg/FFprobe 时可设置 `VISION_FFMPEG` 和 `VISION_FFPROBE`。`deploy/components.json` 固定本轮媒体工具来源与哈希；本地组件许可随解压保留。`.env.example` 为变量示例，不会自动读取。

前端生产资源由 API 服务本地提供，无运行时 CDN、外部字体和云模型调用。依赖安装完成后的本轮页面与本地媒体流程可断网使用；完整产品的离线模型包和现场安装验收另按主规格完成。

## 当前可验收内容

- 无账号工作台：页面、业务 API、媒体和 WebSocket 直接可用；保留浏览器同源写入检查、路径限制及摄像头凭据保护。
- 真实 CPU、内存和磁盘指标；GPU、模型或媒体网关未接入时显示未知/未就绪。
- 本地录像分块上传、真实信息探测、SHA-256、预览转码、筛选、编辑、归档和同名文件隔离。
- 摄像头配置、凭据加密和脱敏、网段限制及连接诊断；仅 RTSP 响应不作为解码/上线证明，网关未就绪时明确不能播放。
- 分类设置保存、字段校验和版本冲突保护；重启与刷新保留数据。
- 七导航与四页响应式界面；新安装没有虚构的运行、告警或授权数字。
- 智能体列表、详情、多路配置、版本复制、验证确认发布、归档；刷新持久化、冲突保护及幂等。
- 分路启停/应用、播放、事件/反馈/漏报、历史复测、异步导出的B端工作流，可在独立模拟模式练习。真实执行与结果依赖公共提供方；保存或发布均不表示已启动。

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

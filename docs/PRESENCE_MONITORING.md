# 人员在岗监测接入说明

## 能力边界

首个真实业务模板为“人员在岗监测”：指定区域内至少 1 人；连续无人 30 秒报警；默认置信度 0.5；重复报警间隔 60 秒；每秒采样一次。任务创建时可调整时长、人数、置信度、重复报警间隔和采样间隔。

模板固定绑定一个模型四元引用（模型 ID/版本、能力模板 ID/版本）。发布新模板或模型版本不会改写旧任务。执行前再次核对模型文件摘要、视频源行版本、文件摘要和任务发布版本；断流、解码失败或应用重启会清空连续缺岗证据，不能制造缺岗报警。

YOLO11n 只检测 COCO `person`。人员脚点落在任一监测区域内才计数，重叠区域不重复计数。不识别身份、工服、安全帽或行为；这些需求会返回“无足够匹配的模板”。

## 首次准备

`setup.cmd` 会安装基础依赖、CPU ONNX Runtime、OpenCV 和 NumPy。模型首次准备另执行：

```powershell
.\.venv\Scripts\python.exe deploy\scripts\prepare_yolo.py
```

脚本只下载摘要固定的 Ultralytics 官方 YOLO11n 权重，使用 `var/tools/yolo-export` 中的隔离 PyTorch 环境导出固定 ONNX，并生成 `var/models/yolo11n/manifest.json`。这些运行产物不提交 Git。

启动 `start.cmd` 后，通过公开 API 登记模型和模板：

```powershell
.\.venv\Scripts\python.exe deploy\scripts\setup_presence.py --api-url http://127.0.0.1:8000
```

脚本幂等执行，不直接写数据库。登记完成后，YOLO11n 在“模型管理”可见，“人员在岗监测”在任务模板列表可见。可加 `--source-id <视频源ID>` 给模板配置全画面默认视频；未指定时，每个任务必须选择视频源并划区。

## DeepSeek 模板匹配

在 Git 忽略的仓库根目录 `.env.local` 中配置：

```dotenv
VISION_DEEPSEEK_API_KEY=在本机填写
VISION_DEEPSEEK_MODEL=deepseek-flash
VISION_DEEPSEEK_MATCH_THRESHOLD=0.8
```

任务创建页的“自然语言匹配”仅发送用户需求、已发布模板标题/摘要和公开能力条件。模型引用、视频源、文件路径、地址、凭据和 API Key 不进入提示词。返回模板 ID 仍会在本地重新核对发布状态；匹配度不足、存在未覆盖条件或版本已变化时返回 `no_match`，不会回退到未登记模型执行。

## 真实执行链路

```text
已发布模板 → 创建固定版本任务 → 验证/确认 → 本机 FFmpeg 采样
→ YOLO11n ONNX 人员框 → 区域人数/连续缺岗计时 → 持久化事件与截图
```

录像使用媒体时间，摄像头使用单调时间。文件读取完所选范围后运行变为“已完成”；摄像头持续运行并在断流时按资源设置重连。运行、操作和事件写入 `0008_local_execution` 表，应用异常退出后的活动运行会恢复为“失败/执行中断”，由用户明确重新启动。

针对性验证：

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
.\.venv\Scripts\python.exe -m pytest tests/backend/test_yolo_detector.py tests/backend/test_yolo_services.py tests/backend/test_local_reader.py tests/backend/test_local_execution.py -q
.\.venv\Scripts\python.exe -m pytest tests/deploy/test_prepare_yolo.py tests/deploy/test_setup_presence.py -q
```

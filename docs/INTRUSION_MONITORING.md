# 人员区域入侵监测接入说明

## 能力与固定逻辑

“人员区域入侵监测”复用经过来源、摘要和 ONNX 自检的 YOLO11n COCO `person` 检测结果，并绑定独立的 `person + intrusion` 模型能力和业务模板。默认规则为：

- 启动时区域内已有人员不报警；区域连续清空 10 秒后才布防。
- 人员进入区域并累计 8 秒有效、连续的可见观察后报警。
- 目标短暂遮挡最多保留本地跟踪编号 5 秒，遮挡时间不计入 8 秒确认。
- 同一次区域占用只报警一次；区域连续无人 10 秒后结束本次事件并重新布防。
- 视频断流、读取失败或应用重启会清空全部入侵状态；恢复后重新等待区域清空 10 秒。

模板默认每秒采样一次，置信度为 0.5。任务创建时可以在模型声明范围内调整确认时长、置信度、跟踪超时、离开确认和采样间隔；采样间隔必须小于跟踪超时，跟踪超时必须小于离开确认时间。

当前跟踪器面向固定摄像头，使用相邻检测框的位置和重叠关系维持临时编号，不进行人脸识别或跨镜身份识别。拥挤、长时间完全遮挡、摄像机移动或目标快速交叉时可能更换编号，须使用现场正负样本验收。

## 首次准备与登记

模型文件与人员在岗能力共用同一套受控准备流程，只需准备一次：

```powershell
.\.venv\Scripts\python.exe deploy\scripts\prepare_yolo.py
```

保持 `start.cmd` 正在运行，再开一个项目终端登记入侵能力和模板：

```powershell
.\.venv\Scripts\python.exe deploy\scripts\setup_intrusion.py --api-url http://127.0.0.1:8000
```

登记脚本通过公开 API 上传或复用摘要一致的模型文件，完成真实 ONNX 黑图推理自检，并发布“人员区域入侵监测”。它不会覆盖用户修改过的同名模型、模板或登记回执。可选 `--source-id <视频源ID>` 将该视频的全画面设为模板默认区域；未指定时，创建任务必须选择视频并绘制区域。

如果还需要人员在岗模板，独立执行：

```powershell
.\.venv\Scripts\python.exe deploy\scripts\setup_presence.py --api-url http://127.0.0.1:8000
```

## 状态与事件

```text
等待区域清空 → 已布防 → 进入确认 → 本次入侵已报警
       ↑                                  ↓
       └──────── 连续无人 10 秒 ──────────┘
```

短暂遮挡阶段保留候选目标但暂停确认时间。遮挡超过 5 秒会丢弃未报警候选；已报警事件仍需区域连续无人 10 秒才结束，期间不会重复报警。真实事件类型为 `person_intrusion`，包含开始/结束媒体位置（录像）、区域、人员框和现场截图；证据写入失败不会把真实报警改成成功截图。

## 针对性验证

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
.\.venv\Scripts\python.exe -m pytest tests/backend/test_intrusion_rule.py tests/backend/test_local_execution.py tests/backend/test_yolo_services.py -q
.\.venv\Scripts\python.exe -m pytest tests/deploy/test_setup_presence.py -q
```

# 多模态 API 接入说明

## 当前边界

项目已提供 OpenAI Chat Completions 兼容的多模态适配器，支持三项受控能力：

1. 在服务端提供的候选目录中严格选择完整匹配的模板；API 只能返回候选序号，不能编造模型或模板 ID。
2. 没有完整匹配时生成结构化多模态执行方案，并逐字保留用户的完整原始需求。
3. 接收本机调用方抽取的有限 JPEG 采样帧，返回结构化触发判断、置信度、事件类型、原因和采样时间。

当前本地运行器仍只执行人员在岗和区域入侵 YOLO 模板，`supports_multimodal_tasks` 保持为 `False`。因此接口完成不等于多模态视频任务已经可启动；在真实帧调度、连续条件和事件持久化接线完成前，系统会明确拒绝启动，不会用规划结果冒充检测结果。

## 配置

将以下内容写入 Git 忽略的 `.env.local`，不要提交真实密钥：

```env
VISION_MULTIMODAL_API_URL=https://供应方地址/v1/chat/completions
VISION_MULTIMODAL_API_KEY=真实密钥
VISION_MULTIMODAL_MODEL=供应方模型名称
VISION_MULTIMODAL_API_TIMEOUT_SECONDS=60
VISION_MULTIMODAL_MATCH_THRESHOLD=0.8
VISION_MULTIMODAL_MAX_FRAMES=8
VISION_MULTIMODAL_MAX_IMAGE_BYTES=2097152
```

远程地址必须使用 HTTPS 且必须配置密钥。未来本地部署时允许使用回环 HTTP，例如：

```env
VISION_MULTIMODAL_API_URL=http://127.0.0.1:11434/v1/chat/completions
VISION_MULTIMODAL_API_KEY=
VISION_MULTIMODAL_MODEL=local-vision
```

修改配置后重启应用，在“模型管理 → 多模态模型”中选择该部署用于“多模态能力与证据分析”。用途选择只影响后续新方案，不会修改历史快照。

## 协议约束

- 请求使用 OpenAI 兼容的 `POST /v1/chat/completions` JSON 结构，并要求 `response_format={"type":"json_object"}`。
- 客户端关闭环境代理继承和 HTTP 重定向，响应上限为 64 KiB。
- 远程 HTTP、URL 凭据、查询串和片段均被拒绝；本地回环 HTTP 是为最终本机部署保留的迁移路径。
- 单次帧判断默认最多 8 张 JPEG，每张最大 2 MiB；调用方必须在本机完成抽帧。
- API Key 仅放在 `Authorization` 请求头，不进入提示词、数据库、响应或日志。
- 方案只发送媒体类型、时长和分辨率等粗粒度信息，不发送视频源 ID、地址或摄像头凭据。

## 后续本地化

本地模型服务只要提供同一兼容端点及结构化 JSON 输出，即可通过修改 `VISION_MULTIMODAL_API_URL` 和模型名切换。后续仍需实现：录像/直播采样调度、跨帧连续时长判断、断流复位、事件去重、证据保存和运行资源限制。

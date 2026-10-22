import axios from 'axios'
export function csrfToken(cookies = document.cookie): string {
  const value = cookies.split(';').map(v => v.trim()).find(v => v.startsWith('vision_csrf='))?.slice(12) ?? ''
  try { return decodeURIComponent(value) } catch { return '' }
}
const messages: Record<string, string> = {
  AGENT_NOT_FOUND:'智能体不存在，请返回列表并刷新。',
  REVISION_NOT_FOUND:'配置版本不存在，请刷新详情。',
  REVISION_CONFLICT:'配置已被其他页面更新。当前输入已保留，请先复制需要保留的内容，再刷新并比较。',
  REVISION_IMMUTABLE:'已发布配置不能直接修改，请复制为新草稿。',
  SOURCE_UNAVAILABLE:'所选视频源不存在或已归档，请重新选择。',
  INVALID_MEDIA_RANGE:'录像区间超出视频时长，或该视频源不支持区间。',
  IDEMPOTENCY_CONFLICT:'此请求编号已用于不同内容，请刷新后重新操作。',
  CAPABILITY_SERVICE_UNAVAILABLE:'模型能力评估服务尚未接入。草稿已保留，暂不能验证或启动。',
  CAMERA_ADDRESS_FORBIDDEN:'摄像头地址须为允许网段内的 RTSP 地址，请检查地址与安全设置。', PASSWORD_TOO_SHORT:'密码至少需要 12 个字符。', ALREADY_INITIALIZED:'管理员已初始化，请使用已有账号登录。', LOGIN_RATE_LIMITED:'登录尝试过于频繁，请稍后再试。', MEDIA_NOT_READY:'视频尚未准备就绪，请等待探测或转码完成。', MEDIA_MISSING:'媒体文件不存在，请重新导入视频。', DEPENDENCY_UNAVAILABLE:'实时媒体网关尚未接入，请在运行状态中检查本地组件。', UPLOAD_TOO_LARGE:'文件超过当前上传限制，请检查存储设置。', MEDIA_GATEWAY_UNAVAILABLE:'摄像头媒体网关尚未接入，暂时无法预览。',
  FILE_UNREADABLE:'文件无法读取，请检查文件是否损坏或重新选择。', MEDIA_UNSUPPORTED:'当前环境无法解码此视频，请检查本地媒体组件或更换文件。',
  STORAGE_LOW:'存储空间不足，请释放空间后重试。', SOURCE_UNREACHABLE:'无法连接视频源，请检查现场网络和地址。',
  SOURCE_AUTH_FAILED:'摄像头拒绝认证，请修改凭据后测试。', SOURCE_DIAGNOSIS_UNKNOWN:'连接失败，原因尚未确认，请检查网络、地址和设备状态。',
 WORKER_UNAVAILABLE:'后台处理进程尚未就绪，请在运行状态中检查。',
  INVALID_CREDENTIALS:'用户名或密码不正确。', SETUP_ALREADY_COMPLETED:'管理员已初始化，请使用已有账号登录。',
  SOURCE_NOT_ALLOWED:'此摄像头地址不在允许访问的网段内，请检查安全设置。', FILE_TOO_LARGE:'文件超过当前上传限制，请检查存储设置。',
  VALIDATION_ERROR:'提交的信息不符合要求，请检查表单。', CSRF_INVALID:'安全令牌已更新，请刷新页面后重试。',
}
export function humanError(error: unknown): string {
  const value = error as {response?: {status?: number; data?: {error?: {code?:string; request_id?:string}}}}
  const status = value?.response?.status
  const detail = value?.response?.data?.error
  const code=detail?.code?.toUpperCase()
  if (code && messages[code]) return messages[code]!
  if (status === 401) return '会话已过期，请重新登录。'
  if (status === 403) return '当前账号没有执行此操作的权限。'
  if (status === 404) return '内容已不存在，请刷新列表。'
  if (status === 409) return '内容已被更新，请刷新后重新修改；当前输入已保留。'
  if (status === 413) return '文件超过允许的大小，请选择更小的文件。'
  if (status === 422) return '提交的信息不符合要求，请检查表单。'
  if (status === 503) return '所需服务尚未就绪，请查看运行状态后重试。'
  if (status && status >= 500) return `服务暂时无法完成请求，请稍后重试。${detail?.request_id ? ` 请求编号：${detail.request_id}` : ''}`
  return '无法连接本机服务，请确认服务已启动后重试。'
}
export const client = axios.create({baseURL:'/api/v1',withCredentials:true,timeout:30000})
client.interceptors.request.use(config => {
  if (!['get','head','options'].includes(config.method ?? 'get')) config.headers.set('X-CSRF-Token', csrfToken())
  return config
})
client.interceptors.response.use(response => response, error => {
  if (axios.isAxiosError(error) && error.response?.status === 401 && !error.config?.url?.startsWith('/auth/')) window.dispatchEvent(new Event('vision-session-expired'))
  return Promise.reject(error)
})

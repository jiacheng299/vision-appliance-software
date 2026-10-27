import { newId } from '../../shared/ids'
import type { MonitorEvent, Run, RevisionConfig } from './api'
import { humanError } from '../../shared/api/client'
import { runSourceKey } from './channelSources'
export const activeStates = new Set<Run['state']>(['queued','starting','running','reconnecting','stopping'])
export const labels: Record<string,string> = {draft:'草稿',ready:'待启动',queued:'排队中',starting:'启动中',running:'运行中',reconnecting:'断流重连中',stopping:'停止中',stopped:'已停止',completed:'已完成',failed:'异常',canceled:'已取消',unknown:'状态待确认',archived:'已归档',pending:'待处理',succeeded:'成功',partial_failed:'部分失败',unreviewed:'待核查',correct:'正确',false_positive:'误报',collecting:'收集中',rendering:'生成中',packaging:'打包中',clarification_required:'需要补充条件',unsupported:'暂不支持',insufficient_evidence:'证据条件不足',executable:'可执行',ready_evidence:'证据就绪',missing:'证据不足',partial:'证据不完整',expired:'证据已过期',published:'已发布'}
export const label = (value: string) => labels[value] ?? value
export function mergedEvents(previous: MonitorEvent[], incoming: MonitorEvent[]): MonitorEvent[] {
  const events = new Map(previous.map(e => [e.id,e]))
  for (const event of incoming) {
    const old = events.get(event.id)
    if (!old || event.row_version >= old.row_version) events.set(event.id,event)
  }
  return [...events.values()].sort((a,b) => b.occurred_at.localeCompare(a.occurred_at) || b.id.localeCompare(a.id)).slice(0,500)
}
export function actualRuns(runs: Run[]): Run[] {
  const result = new Map<string,Run>()
  for (const run of [...runs].sort((a,b)=>(b.created_at??b.started_at??'').localeCompare(a.created_at??a.started_at??''))) {
    const key=runSourceKey(run),old = result.get(key)
    if (!old || (activeStates.has(run.state) && !activeStates.has(old.state))) result.set(key,run)
  }
  return [...result.values()]
}
export function configChanges(before: RevisionConfig, after: RevisionConfig): {channel:string;field:string;before:string;after:string}[] {
  const result:{channel:string;field:string;before:string;after:string}[]=[]
  const fields={task_mode:'任务模式',execution_plan:'执行方案与大模型版本',sources:'通道内视频源、区域与录像范围',source_id:'视频源',requirement_text:'监测需求',target:'监测对象',rule:'触发规则',duration_seconds:'持续时长（秒）',start_media_ms:'录像开始位置（毫秒）',end_media_ms:'录像结束位置（毫秒）',capability_ref:'模型与模板版本',regions:'监测区域'} as const
  for(const current of after.channels??[]){
    const old=before.channels?.find(c=>c.channel_id===current.channel_id)
    if(!old){result.push({channel:current.name,field:'通道',before:'无',after:'新增通道'});continue}
    for(const [key,name] of Object.entries(fields)){
      const field=key as keyof typeof fields
      if(JSON.stringify(old[field])!==JSON.stringify(current[field])){
        const text=(value:unknown)=>value==null||value===''?'未设置':typeof value==='object'?JSON.stringify(value):String(value)
        result.push({channel:current.name,field:name,before:field==='regions'?`${old.regions?.length??0} 个区域`:text(old[field]),after:field==='regions'?`${current.regions?.length??0} 个区域（边界/名称已改变，请核对画面）`:text(current[field])})
      }
    }
  }
  for(const old of before.channels??[])if(!after.channels?.some(c=>c.channel_id===old.channel_id))result.push({channel:old.name,field:'通道',before:'已有通道',after:'本版未配置；未选择停止时原运行将继续'})
  return result
}
export function requestKey(scope: string, payload: unknown): string {
  const signature = JSON.stringify(payload), storageKey = `vision.agent.request.${scope}`
  try {
    const old = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null') as {signature:string;key:string}|null
    if (old?.signature === signature) return old.key
  } catch { /* An interrupted storage write does not authorize reusing another request. */ }
  const key = newId()
  sessionStorage.setItem(storageKey,JSON.stringify({signature,key}))
  return key
}
export function received(scope: string) { sessionStorage.removeItem(`vision.agent.request.${scope}`) }
const businessCodes = new Set(['execution_plan_stale','execution_plan_blocked','task_planning_unavailable','multimodal_execution_unavailable','multimodal_service_unavailable','grouped_sources_unavailable','validation_stale','validation_blocked','confirmation_required','published_revision_required','invalid_channel_scope','run_scope_changed','channel_busy','agent_archived','agent_in_use','baseline_running','feedback_conflict','invalid_media_range','invalid_time','evidence_unavailable','playback_unavailable','invalid_baseline','invalid_export_scope','export_state_conflict','export_not_ready','runtime_service_unavailable','events_service_unavailable','media_service_unavailable','exports_service_unavailable','provider_contract_invalid'])
export function agentError(error: unknown): string {
  const detail = (error as {response?:{data?:{error?:{code?:string;message?:string}}}})?.response?.data?.error
  if (detail?.code && businessCodes.has(detail.code) && detail.message) return detail.message.slice(0,1000)
  return humanError(error)
}

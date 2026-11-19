<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import { agentApi, type Operation, type Revision, type Run, type Workspace } from './api'
import { activeStates, actualRuns, agentError, received, requestKey } from './state'
import type { Source } from '../../shared/api/types'
import { formatDate } from '../../shared/ui/resource'
import MediaPlayer from '../../shared/media/MediaPlayer.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import AgentStatus from './AgentStatus.vue'
import RunPlayer from './RunPlayer.vue'
import EventsPanel from './EventsPanel.vue'
import TrustChecksPanel from './TrustChecksPanel.vue'
import ObservationPanel from './ObservationPanel.vue'
import RoutePanel from './RoutePanel.vue'
import TaskSummaryStrip from './TaskSummaryStrip.vue'
import VideoWall from './VideoWall.vue'
import { channelSources, sourceCount, wallGroups } from './channelSources'
const props=defineProps<{agentId:string;workspace:Workspace|null;revision:Revision;sources:Source[];canWrite:boolean;focusRunId?:string}>()
const emit=defineEmits<{operation:[value:Operation];retry:[value:Run]}>()
const selectedRunId=ref<string|null>(null),stopping=ref(''),error=ref('')
const trustChecksOpen = ref(false)
// 任务视图按使用流程排布：画面 → 观察记录 → 模型组合 → 事件
type Tab = 'live' | 'observation' | 'routing' | 'events'
const tab = ref<Tab>('live')
const real=computed(()=>props.workspace?.data_origin==='real')
type RouteTarget = { sourceId: string; channelId: string; rule: string; duration: number | null }
const defaultRouteTarget = computed<RouteTarget | null>(() => {
  const channel = props.revision.config.channels?.[0]
  const binding = channel ? channelSources(channel)[0] : undefined
  const source = binding ? props.sources.find(item => item.id === binding.source_id) : undefined
  return channel?.channel_id && source
    ? { sourceId: source.id, channelId: channel.channel_id, rule: channel.rule,
        duration: channel.duration_seconds ?? null }
    : null
})
const selectedRouteKey = ref<{ sourceId: string; channelId: string } | null>(null)
const selectedRouteTarget = computed<RouteTarget | null>(() => {
  const selected = selectedRouteKey.value
  if (!selected) return null
  const channel = props.revision.config.channels?.find(item => item.channel_id === selected.channelId)
  const source = props.sources.find(item => item.id === selected.sourceId)
  const bound = channel && channelSources(channel).some(binding => binding.source_id === selected.sourceId)
  return channel?.channel_id && source && bound
    ? { sourceId: selected.sourceId, channelId: channel.channel_id, rule: channel.rule,
        duration: channel.duration_seconds ?? null }
    : null
})
const routeTarget = computed(() => selectedRouteTarget.value ?? defaultRouteTarget.value)
function openRoute(target: { sourceId: string; channelId: string | null }) {
  if (!target.channelId || !props.sources.some(item => item.id === target.sourceId)) return
  const channel = props.revision.config.channels?.find(item => item.channel_id === target.channelId
    && channelSources(item).some(binding => binding.source_id === target.sourceId))
  if (!channel) return
  selectedRouteKey.value = { sourceId: target.sourceId, channelId: target.channelId }
  tab.value = 'routing'
}
const tabs = computed<{value:Tab;label:string;enabled:boolean}[]>(() => [
  {value:'live', label:'画面', enabled:true},
  {value:'observation', label:'观察记录', enabled:real.value},
  {value:'routing', label:'模型组合', enabled:real.value && !!routeTarget.value},
  {value:'events', label:'事件', enabled:true},
])
watch(()=>props.workspace?.data_origin,()=>{
  const current = tabs.value.find(item => item.value === tab.value)
  if(current && !current.enabled && real.value === false) tab.value='live'
})
const runs=computed(()=>props.workspace?.runs??[]),currentRuns=computed(()=>actualRuns(runs.value))
const selected=computed(()=>runs.value.find(r=>r.id===selectedRunId.value)??currentRuns.value[0])
const fallbackSource=computed(()=>{const c=props.revision.config.channels?.[0];return c?props.sources.find(s=>s.id===channelSources(c)[0]?.source_id):undefined})
const view=ref(sourceCount(props.revision.config)>1?'wall':'single')
const groups=computed(()=>wallGroups(props.revision.config,currentRuns.value))
const groupRuns=(id:string)=>currentRuns.value.filter(r=>r.channel_id===id)
watch(()=>props.focusRunId,value=>{if(value){selectedRunId.value=value;view.value='single';tab.value='live'}},{immediate:true})
function state(run:Run){
  if(!props.workspace?.runtime_available)return 'unknown'
  if(['running','reconnecting'].includes(run.state)&&(!run.last_heartbeat_at||Date.now()-Date.parse(run.last_heartbeat_at)>30000))return 'unknown'
  return run.state
}
function progress(run:Run){return run.selected_duration_ms&&run.processed_media_ms!=null?`${Math.min(100,Math.max(0,run.processed_media_ms/run.selected_duration_ms*100)).toFixed(1)}%`:'进度未知'}
function duration(run:Run){return run.started_at?`${Math.max(0,Math.floor(((run.ended_at?Date.parse(run.ended_at):Date.now())-Date.parse(run.started_at))/1000))} 秒`:'尚未开始'}
async function stop(run:Run){
  if(stopping.value||!window.confirm(`确认停止“${run.channel_name}”整个通道内的所有活动视频？其他通道不受影响。`))return
  stopping.value=run.id;error.value='';const scope=`stop.${run.id}`
  try{const op=await agentApi.stopChannel(props.agentId,run.channel_id,requestKey(scope,{channel_id:run.channel_id}));received(scope);emit('operation',op)}catch(e){error.value=agentError(e)}finally{stopping.value=''}
}
</script>
<template>
  <ErrorBanner :error="error" :retryable="false"/>
  <p v-if="workspace&&!workspace.runtime_available" class="error-banner" role="alert">{{workspace.runtime_error}} 保留已读取的历史状态，但当前状态待确认，控制操作暂不可用。</p>
  <TaskSummaryStrip :agent-id="agentId" :channel-id="routeTarget?.channelId ?? null"
    :source-id="routeTarget?.sourceId ?? null" :real="real"/>
  <div class="agent-actions agent-tabs" role="tablist" aria-label="任务视图">
    <NButton v-for="item in tabs.filter(entry => entry.enabled)" :key="item.value" size="small"
      :aria-label="item.label" :aria-selected="tab===item.value" :aria-pressed="tab===item.value"
      :type="tab===item.value?'primary':'default'" @click="tab=item.value">{{item.label}}</NButton>
  </div>

  <template v-if="tab==='live'">
    <div class="agent-actions wall-view-toggle">
      <NButton :type="view==='wall'?'primary':'default'" @click="view='wall'">监控墙</NButton>
      <NButton :type="view==='single'?'primary':'default'" @click="view='single'">单画面与报警</NButton>
      <NButton v-if="real" aria-label="模型防护" :aria-expanded="trustChecksOpen"
        :type="trustChecksOpen?'primary':'default'" @click="trustChecksOpen=!trustChecksOpen">模型防护</NButton>
    </div>
    <TrustChecksPanel v-if="trustChecksOpen && real" :key="agentId"
      :agent-id="agentId" :runs="runs" :sources="sources"/>
    <div v-if="groups.length" class="run-channel-grid"><article v-for="group in groups" :key="group.id" class="panel run-channel-card"><strong>{{group.name}}</strong><p>{{group.tiles.length}} 路视频 · {{groupRuns(group.id).filter(r=>activeStates.has(r.state)).length}} 路活动 · {{groupRuns(group.id).filter(r=>r.state==='failed').length}} 路异常</p><small>共享规则，按整个通道启停；请核对每个画面的实际版本与状态。</small><div class="agent-actions"><NButton v-if="canWrite&&groupRuns(group.id).some(r=>activeStates.has(r.state))" size="small" :disabled="!workspace?.runtime_available||!!stopping" :loading="groupRuns(group.id).some(r=>r.id===stopping)" @click="stop(groupRuns(group.id).find(r=>activeStates.has(r.state))!)">停止整个通道</NButton></div></article></div>
    <section v-for="run in currentRuns.filter(r=>r.state==='failed')" :key="run.id" class="error-banner" role="alert">
      <div><strong>{{run.channel_name}}：监测异常</strong><p>{{run.message||'本次监测已中断。请确认视频源和模型可用后重新启动。'}}</p><small v-if="run.error_code">错误代码：{{run.error_code}}</small></div>
      <NButton v-if="canWrite" :disabled="!workspace?.runtime_available||!!stopping" @click="emit('retry',run)">重新监测</NButton>
    </section>
    <VideoWall v-if="view==='wall'" :agent-id="agentId" :revision="revision" :runs="runs" :sources="sources" :runtime-available="workspace?.runtime_available??false"/>

    <div v-if="view==='single'" class="agent-live-grid"><section class="panel"><div class="panel-title"><h2>{{selected?.channel_name || '视频源预览'}}</h2><AgentStatus v-if="selected" :value="state(selected)"/><span v-else class="status">未启动监测</span></div>
      <NSelect v-if="runs.length" v-model:value="selectedRunId" :options="runs.map(r=>({label:`${r.channel_name} / ${sources.find(s=>s.id===r.source_id)?.name??r.source_id} · v${r.revision_no} · ${r.id}`,value:r.id}))" :placeholder="selected?.channel_name" aria-label="选择当前或历史运行画面"/>
      <template v-if="selected"><p class="run-meta">运行编号 {{selected.id}} · 实际配置 v{{selected.revision_no}}</p><p v-if="!activeStates.has(selected.state)" class="notice">当前展示已结束运行的历史/回放入口，不是实时监测画面；若没有录像，媒体服务会说明不可回放。</p><RunPlayer :key="selected.id" :identity="`${selected.id}:${selected.state}:${workspace?.runtime_available}`" :agent-id="agentId" :load="()=>agentApi.playback(agentId,selected!.id)" :is-live="selected.source_kind==='camera'&&state(selected)==='running'" :alert-active="selected.alert_state==='absence'" alert-label="人员缺岗"/><p class="muted">最近心跳 {{formatDate(selected.last_heartbeat_at??null)}} · {{selected.source_kind==='file'?`分析进度 ${progress(selected)}`:`运行时长 ${duration(selected)}`}}</p><p v-if="selected.source_kind==='file'" class="muted">播放器位置与分析位置分别显示，播放或拖动进度条不会改变分析进度。</p></template>
      <template v-else><MediaPlayer v-if="fallbackSource" :source="fallbackSource"/><EmptyState v-else icon="video" title="尚无运行或可预览的视频源" description="可先保存配置，验证并确认后再启动。"/><p class="muted">这里仅预览视频源，不代表已启动分析或已产生检测框。</p></template>
    </section><EventsPanel :agent-id="agentId" :runs="runs" :sources="sources" :can-write="canWrite" compact/></div>
    <EventsPanel v-if="view==='wall'" :agent-id="agentId" :runs="runs" :sources="sources" :can-write="canWrite" compact/>
  </template>

  <ObservationPanel v-if="tab==='observation' && real" :key="agentId"
    :agent-id="agentId" :runs="runs" :sources="sources" @open-route="openRoute"/>

  <RoutePanel v-if="tab==='routing' && real && routeTarget"
    :key="`${routeTarget.sourceId}:${routeTarget.channelId}:${routeTarget.rule}:${routeTarget.duration ?? ''}`"
    :agent-id="agentId" :channel-id="routeTarget.channelId"
    :source-label="sources.find(item => item.id === routeTarget?.sourceId)?.name"
    :source-id="routeTarget.sourceId" :rule="routeTarget.rule" :duration-seconds="routeTarget.duration"/>

  <EventsPanel v-if="tab==='events'" :agent-id="agentId" :runs="runs" :sources="sources" :can-write="canWrite"/>
</template>

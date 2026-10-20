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
const props=defineProps<{agentId:string;workspace:Workspace|null;revision:Revision;sources:Source[];canWrite:boolean;focusRunId?:string}>()
const emit=defineEmits<{operation:[value:Operation]}>()
const selectedRunId=ref<string|null>(null),stopping=ref(''),error=ref('')
const runs=computed(()=>props.workspace?.runs??[]),currentRuns=computed(()=>actualRuns(runs.value))
const selected=computed(()=>runs.value.find(r=>r.id===selectedRunId.value)??currentRuns.value[0])
const fallbackSource=computed(()=>props.sources.find(s=>s.id===props.revision.config.channels?.[0]?.source_id))
watch(()=>props.focusRunId,value=>{if(value)selectedRunId.value=value},{immediate:true})
function state(run:Run){
  if(!props.workspace?.runtime_available)return 'unknown'
  if(['running','reconnecting'].includes(run.state)&&(!run.last_heartbeat_at||Date.now()-Date.parse(run.last_heartbeat_at)>30000))return 'unknown'
  return run.state
}
function progress(run:Run){return run.selected_duration_ms&&run.processed_media_ms!=null?`${Math.min(100,Math.max(0,run.processed_media_ms/run.selected_duration_ms*100)).toFixed(1)}%`:'进度未知'}
function duration(run:Run){return run.started_at?`${Math.max(0,Math.floor(((run.ended_at?Date.parse(run.ended_at):Date.now())-Date.parse(run.started_at))/1000))} 秒`:'尚未开始'}
async function stop(run:Run){
  if(stopping.value||!window.confirm(`确认停止“${run.channel_name}”的这次运行？其他通道不受影响。`))return
  stopping.value=run.id;error.value='';const scope=`stop.${run.id}`
  try{const op=await agentApi.stop(props.agentId,run.id,requestKey(scope,{run_id:run.id}));received(scope);emit('operation',op)}catch(e){error.value=agentError(e)}finally{stopping.value=''}
}
</script>
<template>
  <ErrorBanner :error="error" :retryable="false"/>
  <p v-if="workspace&&!workspace.runtime_available" class="error-banner" role="alert">{{workspace.runtime_error}} 保留已读取的历史状态，但当前状态待确认，控制操作暂不可用。</p>
  <div v-if="currentRuns.length" class="run-channel-grid"><article v-for="run in currentRuns" :key="run.id" class="panel run-channel-card" :class="{selected:selected?.id===run.id}"><button class="run-channel-title" @click="selectedRunId=run.id"><strong>{{run.channel_name}}</strong><AgentStatus :value="state(run)"/></button><p>实际配置 v{{run.revision_no}} · {{run.source_kind==='file'?progress(run):duration(run)}}</p><small>{{run.message}}</small><div class="agent-actions"><NButton v-if="canWrite&&activeStates.has(run.state)" size="small" :disabled="!workspace?.runtime_available||!!stopping" :loading="stopping===run.id" @click="stop(run)">{{run.state==='queued'?'取消排队':'停止这一路'}}</NButton></div></article></div>
  <div class="agent-live-grid"><section class="panel"><div class="panel-title"><h2>{{selected?.channel_name || '视频源预览'}}</h2><AgentStatus v-if="selected" :value="state(selected)"/><span v-else class="status">未启动监测</span></div>
    <NSelect v-if="runs.length" v-model:value="selectedRunId" :options="runs.map(r=>({label:`${r.channel_name} · v${r.revision_no} · ${r.id}`,value:r.id}))" :placeholder="selected?.channel_name" aria-label="选择当前或历史运行画面"/>
    <template v-if="selected"><p class="run-meta">Run {{selected.id}} · 实际版本 {{selected.revision_id}}</p><p v-if="!activeStates.has(selected.state)" class="notice">当前展示已结束运行的历史/回放入口，不是实时监测画面；若没有录像，媒体服务会说明不可回放。</p><RunPlayer :key="selected.id" :identity="`${selected.id}:${selected.state}:${workspace?.runtime_available}`" :agent-id="agentId" :load="()=>agentApi.playback(agentId,selected!.id)" :is-live="selected.source_kind==='camera'&&state(selected)==='running'"/><p class="muted">最近心跳 {{formatDate(selected.last_heartbeat_at??null)}} · {{selected.source_kind==='file'?`分析进度 ${progress(selected)}`:`运行时长 ${duration(selected)}`}}</p><p v-if="selected.source_kind==='file'" class="muted">播放器位置与分析位置分别显示，播放或拖动进度条不会改变分析进度。</p></template>
    <template v-else><MediaPlayer v-if="fallbackSource" :source="fallbackSource"/><EmptyState v-else icon="video" title="尚无运行或可预览的视频源" description="可先保存配置，验证并确认后再启动。"/><p class="muted">这里仅预览视频源，不代表已启动分析或已产生检测框。</p></template>
  </section><EventsPanel :agent-id="agentId" :runs="runs" :can-write="canWrite" compact/></div>
</template>

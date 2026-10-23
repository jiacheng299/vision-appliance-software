<script setup lang="ts">
import { MANUAL_REVIEW_AVAILABLE } from './features'
import type { Source } from '../../shared/api/types'
import { computed, ref, toRef, watch } from 'vue'
import { NButton, NInput, NSelect } from 'naive-ui'
import { agentApi, type EventFilters, type MonitorEvent, type Missed, type Run } from './api'
import { useEvents } from './useEvents'
import { agentError, label } from './state'
import { formatDate } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import AgentStatus from './AgentStatus.vue'
import EventDrawer from './EventDrawer.vue'
import MissedDialog from './MissedDialog.vue'
const props=withDefaults(defineProps<{agentId:string;runs:Run[];canWrite:boolean;compact?:boolean;sources?:Source[]}>(),{sources:()=>[]})
const filters=ref<EventFilters>({}),runId=ref<string|null>(null),review=ref<string|null>(null),type=ref(''),from=ref(''),to=ref(''),filterError=ref(''),selected=ref<MonitorEvent|null>(null),missedOpen=ref(false),missedRows=ref<Missed[]>([]),missedError=ref('')
const {items,error,connected,lastUpdated,nextCursor,loading,refresh,more}=useEvents(toRef(props,'agentId'),filters)
const runOptions=computed(()=>props.runs.map(r=>({label:`${r.channel_name} · v${r.revision_no} · ${r.id}`,value:r.id})))
function applyFilters(){
  filterError.value=''
  const date=(value:string)=>value?new Date(value).toISOString():undefined
  try{
    if(from.value&&to.value&&Date.parse(from.value)>Date.parse(to.value)){filterError.value='开始时间应早于结束时间。';return}
    filters.value={run_id:runId.value??undefined,review_status:review.value??undefined,event_type:type.value.trim()||undefined,from_time:date(from.value),to_time:date(to.value)}
  }catch{filterError.value='筛选时间无效。'}
}
async function loadMissed(){try{missedRows.value=(await agentApi.missed(props.agentId)).items;missedError.value=''}catch(e){missedError.value=agentError(e)}}
watch(()=>props.agentId,()=>{missedRows.value=[];if(MANUAL_REVIEW_AVAILABLE&&!props.compact)void loadMissed()},{immediate:true})
function missedSaved(){missedOpen.value=false;void loadMissed()}
</script>
<template>
  <section class="panel events-panel" :class="{'events-compact':compact}">
    <div class="panel-title"><h2>{{compact?'实时报警流':'事件与人工核查'}} <small>已加载 {{items.length}}</small></h2><NButton size="small" :loading="loading" @click="refresh">刷新</NButton></div>
    <p class="stream-status" :class="{disconnected:!connected}">{{connected?'报警订阅已连接':'报警未连接 / 正在重连'}} · 最后更新 {{lastUpdated?formatDate(lastUpdated):'尚无有效数据'}}</p>
    <template v-if="!compact"><div class="agent-event-filters"><NSelect v-model:value="runId" :options="runOptions" placeholder="全部运行与版本" clearable aria-label="筛选运行"/><NSelect v-model:value="review" :options="[{label:'待核查',value:'unreviewed'},{label:'正确',value:'correct'},{label:'误报',value:'false_positive'}]" placeholder="全部核查状态" clearable aria-label="筛选核查状态"/><NInput v-model:value="type" placeholder="事件类型（完整名称）" aria-label="筛选事件类型"/><label>开始时间<input v-model="from" type="datetime-local" class="agent-native-input" aria-label="事件开始时间"/></label><label>结束时间<input v-model="to" type="datetime-local" class="agent-native-input" aria-label="事件结束时间"/></label><NButton @click="applyFilters">应用筛选</NButton></div><ErrorBanner :error="filterError" :retryable="false"/></template>
    <ErrorBanner :error="error" @retry="refresh"/>
    <div class="event-feed-list"><button v-for="event in items" :key="event.id" class="event-feed-card" @click="selected=event"><div class="panel-title"><strong>{{event.event_type}}</strong><AgentStatus v-if="MANUAL_REVIEW_AVAILABLE" :value="event.review_status"/></div><p>{{formatDate(event.occurred_at)}} · {{event.severity}} <span v-if="event.data_origin==='mock'" class="demo-chip">模拟</span></p><p>{{event.reason}}</p><small>来源 {{runs.find(r=>r.id===event.run_id)?.channel_name??event.channel_id}} / {{sources.find(s=>s.id===event.source_id)?.name??event.source_id}} · {{label(event.evidence_status==='ready'?'ready_evidence':event.evidence_status)}}</small></button></div>
    <EmptyState v-if="!items.length&&!error&&!loading" icon="bell" title="当前范围没有事件" description="未收到事件不代表已证明没有目标行为，请同时核对运行与视频状态。"/>
    <NButton v-if="nextCursor&&!compact" :loading="loading" @click="more">加载更早事件</NButton>
    <template v-if="MANUAL_REVIEW_AVAILABLE&&!compact"><div class="panel-title agent-section-title"><h2>人工漏报记录 <small>{{missedRows.length}} 条</small></h2><NButton v-if="canWrite" :disabled="!runs.some(r=>r.started_at)" @click="missedOpen=true">补录漏报</NButton></div><ErrorBanner :error="missedError" @retry="loadMissed"/><p v-if="!missedRows.length&&!missedError" class="muted">尚无人工漏报记录，人工记录不计为系统检出。</p><article v-for="record in missedRows" :key="record.id" class="agent-config-row"><h3>{{record.event_type}}</h3><p>{{record.description}}</p><small>{{record.start_media_ms!=null?`${record.start_media_ms/1000} – ${(record.end_media_ms??0)/1000} 秒`:formatDate(record.occurred_at??null)}} · 运行 {{record.run_id}} · 配置 {{record.revision_id}}</small><p class="muted">{{record.evidence_message}}</p></article></template>
  </section>
  <EventDrawer v-if="selected" :agent-id="agentId" :event="selected" :can-write="canWrite" @close="selected=null" @changed="refresh"/>
  <MissedDialog v-if="MANUAL_REVIEW_AVAILABLE&&missedOpen" :agent-id="agentId" :runs="runs" @close="missedOpen=false" @saved="missedSaved"/>
</template>

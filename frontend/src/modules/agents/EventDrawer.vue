<script setup lang="ts">
import { MANUAL_REVIEW_AVAILABLE } from './features'
import { computed, onUnmounted, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInput, NSelect } from 'naive-ui'
import { agentApi, type EventDetail, type MonitorEvent } from './api'
import { agentError, label, received, requestKey } from './state'
import { formatDate } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import AgentStatus from './AgentStatus.vue'
import RunPlayer from './RunPlayer.vue'
const props=defineProps<{agentId:string;event:MonitorEvent;canWrite:boolean}>()
const emit=defineEmits<{close:[];changed:[]}>()
const detail=ref<EventDetail|null>(null),error=ref(''),loading=ref(false),saving=ref(false),reason=ref(''),reviewLabel=ref<'correct'|'false_positive'|null>(null),evidenceId=ref('')
const evidence=computed(()=>detail.value?.evidence.find(e=>e.id===evidenceId.value))
const unchanged=computed(()=>detail.value?.review_status===reviewLabel.value&&detail.value?.feedback_reason===reason.value)
const unsaved=computed(()=>!!detail.value&&(reason.value!==detail.value.feedback_reason||(reviewLabel.value!==null&&reviewLabel.value!==detail.value.review_status)))
let generation=0,disposed=false
async function load(initial=false){
  const request=++generation;loading.value=true;error.value=''
  try{const value=await agentApi.event(props.agentId,props.event.id);if(request!==generation||disposed)return;detail.value=value;if(initial){reason.value=value.feedback_reason;reviewLabel.value=value.review_status==='unreviewed'?null:value.review_status;evidenceId.value=''}}catch(e){if(request===generation)error.value=agentError(e)}finally{if(request===generation)loading.value=false}
}
watch(()=>props.event.id,()=>void load(true),{immediate:true})
onUnmounted(()=>{disposed=true;generation++})
function close(){if(!saving.value&&(!unsaved.value||window.confirm('人工核查尚未保存，确定放弃这些输入？')))emit('close')}
async function submit(){
  if(!detail.value||!reviewLabel.value||saving.value)return
  const scope=`feedback.${detail.value.id}`,body={label:reviewLabel.value,reason:reason.value,row_version:detail.value.row_version}
  saving.value=true;error.value=''
  try{const result=await agentApi.feedback(props.agentId,detail.value,reviewLabel.value,reason.value,requestKey(scope,body));received(scope);if(!disposed){detail.value=result;emit('changed')}}catch(e){if(!disposed)error.value=agentError(e)}finally{saving.value=false}
}
</script>
<template>
  <NDrawer :show="true" :width="680" :mask-closable="!saving" :close-on-esc="!saving" @update:show="close"><NDrawerContent title="事件详情" closable>
    <ErrorBanner :error="error" :retryable="false"/><NButton :loading="loading" :disabled="saving" size="small" @click="load(false)">刷新事件</NButton>
    <template v-if="detail">
      <div class="agent-summary agent-section-title"><h2>{{detail.event_type}}</h2><AgentStatus v-if="MANUAL_REVIEW_AVAILABLE" :value="detail.review_status"/><span v-if="detail.data_origin==='mock'" class="demo-chip">模拟事件</span></div>
      <p>{{formatDate(detail.occurred_at)}} · {{detail.severity}}</p><h3 class="agent-section-title">系统提供的判断依据</h3><p class="event-reason">{{detail.reason || '服务未提供判断依据。'}}</p>
      <dl class="detail-meta"><div class="wide"><dt>来源视频源</dt><dd>{{detail.source_id}}</dd></div><div class="wide"><dt>智能体 / 通道</dt><dd>{{detail.agent_id}} / {{detail.channel_id}}</dd></div><div class="wide"><dt>实际运行 / 配置版本</dt><dd>{{detail.run_id}} / {{detail.revision_id}}</dd></div><div v-if="detail.start_media_ms!=null" class="wide"><dt>录像位置</dt><dd>{{detail.start_media_ms/1000}} 秒 – {{(detail.end_media_ms??detail.start_media_ms)/1000}} 秒</dd></div></dl>
      <h3>事件证据 · {{label(detail.evidence_status==='ready'?'ready_evidence':detail.evidence_status)}}</h3><p v-if="detail.evidence_status!=='ready'" class="notice">证据尚未齐全或不可用。事件仍保留，不补造截图、片段或判断解释。</p>
      <div v-for="item in detail.evidence" :key="item.id" class="agent-region-row"><div>{{item.kind==='image'?'截图':'录像片段'}} · {{label(item.state==='ready'?'ready_evidence':item.state)}}<p class="muted">{{item.message}}</p></div><NButton size="small" :disabled="item.state!=='ready'" @click="evidenceId=item.id">查看</NButton></div>
      <RunPlayer v-if="evidence" :key="evidence.id" :identity="evidence.id" :agent-id="agentId" :media-kind="evidence.kind==='image'?'image':'video'" :load="()=>agentApi.evidence(agentId,event.id,evidence!.id)"/>
      <template v-if="MANUAL_REVIEW_AVAILABLE&&canWrite"><h3 class="agent-section-title">人工核查</h3><div class="field"><label>核查结果</label><NSelect v-model:value="reviewLabel" :options="[{label:'正确',value:'correct'},{label:'误报',value:'false_positive'}]" placeholder="请主动选择核查结果" :disabled="saving" aria-label="核查结果"/></div><div class="field"><label for="feedback-reason">原因或备注（可选）</label><NInput :input-props="{id:'feedback-reason'}" v-model:value="reason" type="textarea" :maxlength="2000" :disabled="saving"/></div><NButton type="primary" :disabled="!reviewLabel||unchanged" :loading="saving" @click="submit">保存核查结果</NButton><p class="muted">每次核查修订保留作者、时间与旧结果，不改变事件所关联的运行版本。</p></template>
      <div class="manual-review-closed"><strong>人工核查</strong><span>当前版本暂未开放</span></div>
      <h3 v-if="detail.feedback_history.length" class="agent-section-title">历史核查记录（只读）</h3><article v-for="feedback in [...detail.feedback_history].reverse()" :key="feedback.id" class="agent-config-row"><AgentStatus :value="feedback.label"/><p>{{feedback.reason || '未填写原因'}}</p><small>{{formatDate(feedback.created_at)}} · {{feedback.author_id}}</small></article>
    </template>
  </NDrawerContent></NDrawer>
</template>

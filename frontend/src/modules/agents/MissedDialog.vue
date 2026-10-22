<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NInput, NInputNumber, NModal, NSelect } from 'naive-ui'
import { agentApi, type Run } from './api'
import { agentError, received, requestKey } from './state'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import RunPlayer from './RunPlayer.vue'
const props=defineProps<{agentId:string;runs:Run[];defaultRunId?:string}>()
const emit=defineEmits<{close:[];saved:[]}>()
const runId=ref<string|null>(props.defaultRunId??null),eventType=ref(''),description=ref(''),start=ref<number|null>(null),end=ref<number|null>(null),occurred=ref(''),error=ref(''),saving=ref(false)
const run=computed(()=>props.runs.find(r=>r.id===runId.value))
const hasRange=computed(()=>run.value?.source_kind==='file'||run.value?.recording_available)
const playhead=ref<number|null>(null)
watch(runId,()=>{start.value=null;end.value=null;occurred.value='';playhead.value=null})
function nowLocal(){const date=new Date();const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);occurred.value=local.toISOString().slice(0,23)}
async function save(){
  if(saving.value)return
  if(!run.value||!eventType.value.trim()||!description.value.trim()){error.value='请选择实际运行，并填写事件类型和漏报描述。';return}
  if(hasRange.value&&(start.value==null||end.value==null||start.value>=end.value)){error.value='请填写有效的录像起止位置。';return}
  if(!hasRange.value&&!occurred.value){error.value='请填写漏报发生时间。';return}
  let occurredAt:string|null=null
  if(occurred.value){const value=new Date(occurred.value);if(!Number.isFinite(value.getTime())){error.value='发生时间无效。';return}occurredAt=value.toISOString()}
  const body={run_id:run.value.id,event_type:eventType.value.trim(),description:description.value.trim(),start_media_ms:start.value==null?null:Math.round(start.value*1000),end_media_ms:end.value==null?null:Math.round(end.value*1000),occurred_at:occurredAt}
  const scope=`missed.${props.agentId}`;saving.value=true;error.value=''
  try{await agentApi.addMissed(props.agentId,body,requestKey(scope,body));received(scope);emit('saved')}catch(e){error.value=agentError(e)}finally{saving.value=false}
}
</script>
<template>
  <NModal :show="true" preset="card" title="补录漏报事件" class="agent-confirm-modal" :mask-closable="false" :closable="!saving" :close-on-esc="!saving" @update:show="!saving&&emit('close')">
    <p class="notice">人工补录会关联所选运行的实际配置版本，不会计入系统检出数。没有保存录像时，仅记录描述和时间，并明确缺少回放证据。</p>
    <div class="field"><label>关联哪次运行</label><NSelect v-model:value="runId" :options="runs.filter(r=>r.started_at).map(r=>({label:`${r.channel_name} · v${r.revision_no} · ${r.id}`,value:r.id}))" :disabled="saving" aria-label="漏报关联运行" placeholder="选择实际运行，不能选择最新草稿代替"/></div>
    <p v-if="run" class="muted">配置 {{run.revision_id}} · 视频源 {{run.source_id}}</p>
    <template v-if="run&&hasRange"><RunPlayer :identity="run.id" :agent-id="agentId" :load="()=>agentApi.playback(agentId,run!.id)" @position="playhead=$event"/><div class="agent-actions"><span>当前回放位置 {{playhead==null?'尚未读取':`${(playhead/1000).toFixed(3)} 秒`}}</span><NButton :disabled="playhead==null||saving" @click="start=(playhead??0)/1000">标记为开始</NButton><NButton :disabled="playhead==null||saving" @click="end=(playhead??0)/1000">标记为结束</NButton></div><p class="muted">本次验证范围：{{(run.start_media_ms??0)/1000}} 秒起{{run.end_media_ms!=null?`，至 ${run.end_media_ms/1000} 秒`:''}}</p><div class="field-grid"><div class="field"><label>漏报开始位置（秒）</label><NInputNumber v-model:value="start" :min="0" :precision="3" :disabled="saving" aria-label="漏报开始位置"/></div><div class="field"><label>漏报结束位置（秒）</label><NInputNumber v-model:value="end" :min="0" :precision="3" :disabled="saving" aria-label="漏报结束位置"/></div></div></template>
    <div v-else-if="run" class="field"><label for="missed-time">发生时间（本机时区）</label><input id="missed-time" v-model="occurred" type="datetime-local" step="0.001" :disabled="saving" class="agent-native-input"/><NButton size="small" :disabled="saving" @click="nowLocal">使用当前时间</NButton></div>
    <div class="field"><label for="missed-type">漏报事件类型</label><NInput :input-props="{id:'missed-type'}" v-model:value="eventType" :maxlength="160" :disabled="saving"/></div><div class="field"><label for="missed-description">漏报描述</label><NInput :input-props="{id:'missed-description'}" v-model:value="description" type="textarea" :maxlength="4000" :disabled="saving"/></div><ErrorBanner :error="error" :retryable="false"/>
    <div class="agent-actions"><NButton :disabled="saving" @click="emit('close')">取消</NButton><NButton type="primary" :loading="saving" @click="save">保存人工漏报记录</NButton></div>
  </NModal>
</template>

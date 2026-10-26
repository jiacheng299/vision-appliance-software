<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { NButton, NCheckbox, NCheckboxGroup, NModal } from 'naive-ui'
import { agentApi, type AgentDetail, type Operation, type Revision, type Run, type Validation } from './api'
import type { Source } from '../../shared/api/types'
import { activeStates, agentError, configChanges, label, received, requestKey } from './state'
import { formatDate } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import { channelSources } from './channelSources'
const props=defineProps<{agent:AgentDetail;revision:Revision;runs:Run[];sources:Source[];canWrite:boolean;compact?:boolean;runtimeAvailable:boolean}>()
const emit=defineEmits<{changed:[];operation:[value:Operation];busy:[value:boolean];edit:[]}>()
const validation=ref<Validation|null>(null),error=ref(''),notice=ref(''),busy=ref(false),confirmationOpen=ref(false),ack=ref(false)
const selectedChannels=ref<string[]>([]),runOpen=ref(false),runAck=ref(false),runBody=ref<{revision_id:string;channel_ids:string[];expected_active_run_ids:string[]}|null>(null),runKind=ref<'start'|'apply'>('start')
const archived=computed(()=>!!props.agent.archived_at)
const invalid=computed(()=>!validation.value||validation.value.verdict!=='executable'||Date.parse(validation.value.expires_at)<=Date.now())
const runScope=computed(()=>props.revision.config.channels?.filter(c=>selectedChannels.value.includes(c.channel_id??''))??[])
const oldRuns=computed(()=>props.runs.filter(r=>activeStates.has(r.state)&&runBody.value?.channel_ids.includes(r.channel_id)))
const changes=computed(()=>oldRuns.value.flatMap(r=>configChanges(r.config_snapshot,props.revision.config).filter(c=>c.channel===r.channel_name||c.field==='通道')))
let generation=0,disposed=false
watch(busy,value=>emit('busy',value))
watch(()=>props.revision.config.channels?.map(c=>c.channel_id).join('|'),()=>{selectedChannels.value=(props.revision.config.channels??[]).flatMap(c=>c.channel_id?[c.channel_id]:[])},{immediate:true})
watch([()=>props.revision.id,()=>props.revision.latest_validation_id],async()=>{
  const current=++generation;validation.value=null;error.value='';notice.value=''
  if(props.revision.latest_validation_id)try{const result=await agentApi.validation(props.revision.latest_validation_id);if(current===generation&&!disposed)validation.value=result}catch(e){if(current===generation)error.value=agentError(e)}
},{immediate:true})
onUnmounted(()=>{disposed=true;generation++})
async function validate(){
  if(busy.value||archived.value)return
  busy.value=true;error.value='';const id=props.revision.id
  try{const result=await agentApi.validate(props.revision);if(!disposed&&props.revision.id===id){validation.value=result;notice.value='验证结果已保存，请逐条核对条件和限制。';emit('changed')}}catch(e){if(!disposed)error.value=agentError(e)}finally{busy.value=false}
}
async function confirm(){
  if(!ack.value||!validation.value||busy.value)return
  busy.value=true;error.value='';const scope=`confirm.${props.revision.id}`,body={row_version:props.revision.row_version,validation_id:validation.value.id,config_hash:validation.value.config_hash}
  try{await agentApi.confirm(props.revision,validation.value,requestKey(scope,body));received(scope);if(!disposed){confirmationOpen.value=false;notice.value='配置已发布并冻结。发布本身不会启动或改变当前运行。';emit('changed')}}catch(e){if(!disposed)error.value=agentError(e)}finally{busy.value=false}
}
function openStart(channelId?:string){
  error.value='';notice.value=''
  if(channelId)selectedChannels.value=[channelId]
  if(props.revision.state!=='published'){error.value='请先验证并确认发布所选配置。';return}
  const ids=runScope.value.flatMap(c=>c.channel_id?[c.channel_id]:[])
  if(!ids.length){error.value='请至少选择一路监测通道。';return}
  const active=props.runs.filter(r=>ids.includes(r.channel_id)&&activeStates.has(r.state))
  runBody.value={revision_id:props.revision.id,channel_ids:ids,expected_active_run_ids:active.map(r=>r.id)}
  runKind.value=active.length?'apply':'start';runAck.value=false;runOpen.value=true
}
async function start(){
  if(!runAck.value||!runBody.value||busy.value)return
  busy.value=true;error.value='';const body=runBody.value,scope=`${runKind.value}.${props.agent.id}`
  try{const operation=await agentApi.submit(props.agent.id,runKind.value,body,requestKey(scope,body));received(scope);if(!disposed){runOpen.value=false;emit('operation',operation);notice.value='操作已受理，正在查询最终结果。'}}catch(e){if(!disposed)error.value=agentError(e)}finally{busy.value=false}
}
defineExpose({openStart})
</script>
<template>
  <section class="panel workflow-panel">
    <div class="panel-title"><div><h2>配置 v{{revision.revision_no}} · {{revision.state==='published'?'已发布（只读）':'草稿'}}</h2><p class="muted">期望版本：{{agent.desired_revision_id ? `v${agent.revisions.find(r=>r.id===agent.desired_revision_id)?.revision_no ?? '?'}` : '尚未发布'}}。实际运行使用的版本请看每一路运行记录。</p></div><div v-if="canWrite&&!archived" class="agent-actions"><NButton :disabled="busy" @click="emit('edit')">{{revision.state==='published'?'复制后修改':'编辑草稿'}}</NButton><NButton v-if="revision.state==='draft'" :loading="busy" @click="validate">验证配置</NButton><NButton v-if="revision.state==='draft'" :disabled="busy||invalid" @click="confirmationOpen=true;ack=false">确认发布</NButton><NButton v-if="revision.state==='published'" type="primary" :disabled="busy||!runtimeAvailable" @click="openStart()">启动 / 应用配置</NButton></div></div>
    <ErrorBanner :error="error" :retryable="false"/><p v-if="notice" class="notice" role="status">{{notice}}</p>
    <p v-if="archived" class="notice">此智能体已归档，仍可核查历史；恢复后可继续编辑和运行。</p>
    <div v-if="!compact&&revision.state==='published'" class="field"><label>本次启动或应用的通道组（组内所有视频一同处理，未选组保持原状）</label><NCheckboxGroup v-model:value="selectedChannels"><NCheckbox v-for="c in revision.config.channels" :key="c.channel_id" :value="c.channel_id" :label="`${c.name}（${channelSources(c).length} 路视频）`"/></NCheckboxGroup></div>
    <div v-if="validation&&!compact" class="validation-result"><h3>{{label(validation.verdict)}}</h3><p>验证有效期至 {{formatDate(validation.expires_at)}}；配置、视频源或能力版本变化后需重新验证。</p><ul v-if="validation.missing_conditions?.length"><li v-for="value in validation.missing_conditions" :key="value">需补充：{{value}}</li></ul><ul v-if="validation.unsupported_conditions?.length"><li v-for="value in validation.unsupported_conditions" :key="value">未覆盖：{{value}}</li></ul><ul><li v-for="value in validation.evidence_limitations" :key="value">限制：{{value}}</li></ul></div>
    <p v-else-if="!compact" class="muted">暂无本配置的有效验证结果。原始需求不能被静默删减后启动。</p>
  </section>
  <NModal v-model:show="confirmationOpen" preset="card" title="核对并发布配置" class="agent-confirm-modal" :mask-closable="false" :closable="!busy" :close-on-esc="!busy">
    <p class="notice">发布将冻结 v{{revision.revision_no}}。后续修改会复制成新草稿；当前运行不会因发布而变化。</p>
    <article v-for="c in revision.config.channels" :key="c.channel_id" class="agent-config-row"><h3>{{c.name}}</h3><div v-for="b in channelSources(c)" :key="b.source_id"><p>视频源：{{sources.find(s=>s.id===b.source_id)?.name??b.source_id}} · {{b.regions?.length??0}} 个区域</p><p v-if="b.start_media_ms!=null">录像区间 {{b.start_media_ms/1000}} – {{(b.end_media_ms??0)/1000}} 秒</p></div><p>原始需求：{{c.requirement_text}}</p><p>对象 {{c.target}} · 规则 {{c.rule}} · 时长 {{c.duration_seconds??'未设置'}} 秒 · 组内 {{channelSources(c).length}} 路视频共用规则</p><p>模型 {{c.capability_ref?.model_id}} / {{c.capability_ref?.model_version}} · 模板 {{c.capability_ref?.template_id}} / {{c.capability_ref?.template_version}}</p></article>
    <ul><li v-for="value in validation?.evidence_limitations" :key="value">{{value}}</li></ul>
    <NCheckbox v-model:checked="ack">我已核对全部监测需求、区域、配置和能力限制。</NCheckbox><ErrorBanner :error="error" :retryable="false"/>
    <div class="agent-actions"><NButton :disabled="busy" @click="confirmationOpen=false">暂不发布</NButton><NButton type="primary" :disabled="!ack||invalid" :loading="busy" @click="confirm">确认发布</NButton></div>
  </NModal>
  <NModal v-model:show="runOpen" preset="card" :title="runKind==='apply'?'应用配置：先停止，再启动':'确认启动监测'" class="agent-confirm-modal" :mask-closable="false" :closable="!busy" :close-on-esc="!busy">
    <p class="notice">{{runKind==='apply'?'所选通道组内全部旧运行将停止，再按每个视频建立新运行。新启动失败不会自动恢复旧运行。':'只启动所选通道；运行服务还会检查资源、视频源和模型可用性。'}}</p>
    <ul><li v-for="c in runScope" :key="c.channel_id">{{c.name}} → 配置 v{{revision.revision_no}}<ul><li v-for="r in oldRuns.filter(r=>r.channel_id===c.channel_id)" :key="r.id">停止 {{sources.find(s=>s.id===r.source_id)?.name??r.source_id}} 的旧运行 {{r.id}}</li></ul></li></ul>
    <div v-if="changes.length" class="table-wrap"><table><thead><tr><th>通道 / 变更</th><th>原设置</th><th>新设置</th></tr></thead><tbody><tr v-for="(change,index) in changes" :key="index"><td>{{change.channel}} / {{change.field}}</td><td class="wrap">{{change.before}}</td><td class="wrap">{{change.after}}</td></tr></tbody></table></div>
    <p v-else class="muted">执行设置没有差异时仍会新建 Run，不复用旧运行编号。</p><NCheckbox v-model:checked="runAck">我已核对所选通道和停启影响。</NCheckbox><ErrorBanner :error="error" :retryable="false"/>
    <div class="agent-actions"><NButton :disabled="busy" @click="runOpen=false">保留配置，暂不运行</NButton><NButton type="primary" :disabled="!runAck" :loading="busy" @click="start">确认提交</NButton></div>
  </NModal>
</template>

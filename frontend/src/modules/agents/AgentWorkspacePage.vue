<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { NButton, NInput, NModal, NSelect } from 'naive-ui'
import { environment } from '../../shared/environment'
import type { Source } from '../../shared/api/types'
import { agentApi, listAgentSources, type AgentDetail, type Revision, type Run, type Scenario } from './api'
import { activeStates, agentError, received, requestKey } from './state'
import { useWorkspace } from './useWorkspace'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import AgentStatus from './AgentStatus.vue'
import RevisionEditor from './RevisionEditor.vue'
import WorkflowPanel from './WorkflowPanel.vue'
import MonitorPanel from './MonitorPanel.vue'
import AgentWorkspaceHeader from './AgentWorkspaceHeader.vue'
import HistoryPanel from './HistoryPanel.vue'
import ExportsPanel from './ExportsPanel.vue'
import './agents.css'
import { channelSources } from './channelSources'
const route=useRoute(),router=useRouter(),agentId=computed(()=>String(route.params.id))
const agent=ref<AgentDetail|null>(null),sources=ref<Source[]>([]),error=ref(''),sourceError=ref(''),notice=ref(''),loading=ref(false),busy=ref(false),saving=ref(false),workflowBusy=ref(false)
const selectedId=ref(''),editing=ref<Revision|null>(null),dirty=ref(false),focusRunId=ref(''),workflowPanel=ref<InstanceType<typeof WorkflowPanel>|null>(null)
const renameOpen=ref(false),name=ref(''),description=ref(''),renameError=ref(''),scenario=ref<Scenario>('normal'),faultRunId=ref<string|null>(null)
const selected=computed(()=>agent.value?.revisions.find(r=>r.id===selectedId.value)??agent.value?.latest_revision)
const canWrite = true
const isDemo=computed(()=>environment.value?.data_origin==='mock'||agent.value?.data_origin==='mock')
const tab=computed(()=>String(route.params.tab||'live'))
let generation=0,disposed=false
async function load(){
  const request=++generation,id=agentId.value;loading.value=true;error.value=''
  try{const result=await agentApi.detail(id);if(request!==generation||disposed)return;agent.value=result;if(!result.revisions.some(r=>r.id===selectedId.value))selectedId.value=result.latest_revision.id}
  catch(e){if(request===generation&&!disposed)error.value=agentError(e)}finally{if(request===generation)loading.value=false}
}
const {data:workspace,operations,error:workspaceError,operationError,refresh:refreshWorkspace,track}=useWorkspace(agentId,()=>void load())
const runs=computed(()=>workspace.value?.runs??[])
const status=computed(()=>{
  if(agent.value?.archived_at)return 'archived'
  if(!workspace.value?.runtime_available)return agent.value?.desired_revision_id?'unknown':agent.value?.status??'draft'
  const active=runs.value.filter(r=>activeStates.has(r.state))
  if(active.some(r=>['running','reconnecting'].includes(r.state)&&(!r.last_heartbeat_at||Date.now()-Date.parse(r.last_heartbeat_at)>30000)))return 'unknown'
  if(active.some(r=>['running','reconnecting'].includes(r.state)))return 'running'
  if(active.some(r=>r.state==='stopping'))return 'stopping'
  if(active.length)return 'queued'
  return agent.value?.status??'draft'
})
async function loadSources(){try{const result=await listAgentSources();if(!disposed){sources.value=result;sourceError.value=''}}catch(e){if(!disposed)sourceError.value=agentError(e)}}
watch(agentId,()=>{agent.value=null;selectedId.value='';editing.value=null;dirty.value=false;notice.value='';focusRunId.value='';void load();void loadSources()},{immediate:true})
onUnmounted(()=>{disposed=true;generation++;window.removeEventListener('beforeunload',beforeUnload)})
function mayLeave(){return !busy.value&&!saving.value&&!workflowBusy.value&&(!dirty.value||window.confirm('尚有未保存的配置，确定离开并放弃修改？'))}
onBeforeRouteLeave(()=>mayLeave())
onBeforeRouteUpdate(()=>{if(!mayLeave())return false;editing.value=null;dirty.value=false})
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value||saving.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
async function clone(editAfter=false){
  if(!agent.value||!selected.value||busy.value)return
  busy.value=true;error.value='';const scope=`clone.${agentId.value}`,body={base_revision_id:selected.value.id,row_version:agent.value.row_version}
  try{const revision=await agentApi.clone(agentId.value,selected.value.id,agent.value.row_version,requestKey(scope,body));received(scope);if(disposed)return;await load();selectedId.value=revision.id;if(editAfter)editing.value=revision;notice.value=`已创建 v${revision.revision_no} 草稿，当前运行和历史配置保持原样。`}
  catch(e){if(!disposed)error.value=agentError(e)}finally{busy.value=false}
}
function edit(){if(!selected.value||agent.value?.archived_at)return;if(selected.value.state==='published')void clone(true);else editing.value=selected.value}
async function saved(revision:Revision){editing.value=null;dirty.value=false;await load();selectedId.value=revision.id;notice.value='草稿已保存，之前的验证失效。当前运行仍使用其原始配置版本。'}
function openRename(){if(!agent.value)return;name.value=agent.value.name;description.value=agent.value.description;renameError.value='';renameOpen.value=true}
async function rename(){
  if(!agent.value||busy.value)return
  if(!name.value.trim()){renameError.value='名称不能为空。';return}
  busy.value=true;try{await agentApi.rename(agentId.value,{name:name.value.trim(),description:description.value.trim(),row_version:agent.value.row_version});renameOpen.value=false;await load()}catch(e){renameError.value=agentError(e)}finally{busy.value=false}
}
async function remove(){
  if(!agent.value||busy.value||!window.confirm(`确认永久删除任务“${agent.value.name}”？将先停止监测，再删除配置、运行历史、告警及证据截图，无法恢复。所属模板、模型、视频源和原始录像不会删除。`))return
  busy.value=true;error.value=''
  const template=selected.value?.config.agent_template_ref?.template_id
  try{await agentApi.remove(agent.value);busy.value=false;await router.push(template?`/agent-templates/${template}`:'/agents')}catch(e){error.value=agentError(e)}finally{busy.value=false}
}
async function viewRun(run:Run){focusRunId.value=run.id;await router.push(`/agents/${agentId.value}/live`)}
async function retry(run:Run){selectedId.value=run.revision_id;await nextTick();workflowPanel.value?.openStart(run.channel_id)}
async function retestCreated(revision:Revision){await load();selectedId.value=revision.id;notice.value='复测草稿已建立，保留原视频范围和基线关联。请编辑、验证并确认后再启动。';await router.push(`/agents/${agentId.value}/config`)}
async function setScenario(){busy.value=true;error.value='';try{await agentApi.scenario(scenario.value,faultRunId.value??undefined);await refreshWorkspace();await load();notice.value='模拟情形已切换。若报警订阅中断，最多数秒后重连补拉。'}catch(e){error.value=agentError(e)}finally{busy.value=false}}
const scenarios=[{label:'恢复正常',value:'normal'},{label:'模型服务不可用',value:'model_unavailable'},{label:'视频网关断流',value:'video_disconnected'},{label:'报警订阅中断',value:'events_disconnected'},{label:'新运行启动失败',value:'start_failed'},{label:'资源不足，进入排队',value:'resource_queued'},{label:'旧运行停止失败',value:'stop_failed'},{label:'重复投递同一事件',value:'duplicate_events'},{label:'证据条件不足',value:'insufficient_evidence'},{label:'选定一路运行异常',value:'run_failed'},{label:'导出失败，可重试',value:'export_failed'}]
</script>
<template>
  <AgentWorkspaceHeader v-if="agent&&selected" :agent="agent" :revision="selected" :status="status" :loading="loading" :disabled="!!editing||busy||saving||workflowBusy" :can-write="canWrite" @select="selectedId=$event" @refresh="load();refreshWorkspace()" @rename="openRename" @remove="remove"/>
  <div v-else class="page-heading"><h1>智能体详情</h1></div>
  <ErrorBanner :error="error" @retry="load"/><ErrorBanner :error="sourceError" @retry="loadSources"/><ErrorBanner :error="workspaceError" @retry="refreshWorkspace"/><ErrorBanner :error="operationError" @retry="refreshWorkspace"/><p v-if="notice" class="notice agent-notice" role="status">{{notice}}</p><div v-if="loading" class="loading-line"/>
  <template v-if="agent&&selected">

    <details v-if="isDemo&&canWrite" class="panel demo-controls"><summary>演示故障与异常流程（全部为模拟）</summary><div class="agent-actions"><NSelect v-model:value="scenario" :options="scenarios" aria-label="模拟故障情形" style="width:240px"/><NSelect v-if="scenario==='run_failed'" v-model:value="faultRunId" :options="runs.filter(r=>activeStates.has(r.state)).map(r=>({label:r.channel_name,value:r.id}))" placeholder="选定异常运行" style="width:220px"/><NButton :loading="busy" @click="setScenario">应用模拟情形</NButton></div><p class="muted">切换情形不会声称有真实摄像头、模型或证据。演示运行/反馈存在内存中，重启后重置。</p></details>
    <WorkflowPanel ref="workflowPanel" :agent="agent" :revision="selected" :runs="runs" :sources="sources" :can-write="canWrite" :runtime-available="workspace?.runtime_available??false" :compact="tab!=='config'" @changed="load" @busy="workflowBusy=$event" @edit="edit" @operation="track"/>
    <details v-if="operations.length" class="panel operation-panel" :open="operations.some(o=>['pending','running','failed','partial_failed'].includes(o.state))"><summary>操作进度 · 最近结果 {{operations[0]?.state==='succeeded'?'成功':operations[0]?.state==='pending'?'待处理':operations[0]?.state==='running'?'处理中':'需要核对'}}</summary><div class="operation-log"><article v-for="operation in operations" :key="operation.id" class="operation-row"><div class="panel-title"><strong>{{{start:'启动',stop:'停止',apply:'应用配置'}[operation.kind]}}</strong><AgentStatus :value="operation.state"/></div><p>{{operation.message}}</p><div v-for="child in operation.channels" :key="`${child.channel_id}:${child.source_id??child.old_run_id}`" class="operation-channel"><AgentStatus :value="child.state"/><span>{{selected.config.channels?.find(c=>c.channel_id===child.channel_id)?.name??child.channel_id}} / {{sources.find(s=>s.id===child.source_id)?.name??child.source_id}}</span><p>{{child.message}}</p><small v-if="child.old_run_id">旧运行编号 {{child.old_run_id}}</small><small v-if="child.new_run_id">新运行编号 {{child.new_run_id}}</small></div></article></div></details>
    <MonitorPanel v-if="tab==='live'" :agent-id="agent.id" :workspace="workspace" :revision="selected" :sources="sources" :can-write="canWrite" :focus-run-id="focusRunId" @operation="track" @retry="retry"/>
    <section v-else-if="tab==='config'" class="panel"><div class="panel-title"><h2>配置内容 · v{{selected.revision_no}}</h2><NButton v-if="canWrite&&!agent.archived_at" :disabled="busy||workflowBusy" @click="edit">{{selected.state==='published'?'修改配置':'继续编辑'}}</NButton></div><p v-if="!selected.config.channels?.length" class="muted">当前配置未包含通道。请通过“编辑草稿”添加通道及监测条件。</p><article v-for="c in selected.config.channels" :key="c.channel_id" class="agent-config-row"><h3>{{c.name}}</h3><dl class="detail-meta"><div><dt>视频源</dt><dd>{{channelSources(c).map(b=>sources.find(s=>s.id===b.source_id)?.name??b.source_id).join('、')||'尚未选择'}}</dd></div><div><dt>持续时长</dt><dd>{{c.duration_seconds==null?'尚未设置':`${c.duration_seconds} 秒`}}</dd></div><div><dt>对象 / 规则</dt><dd>{{c.target||'待补充'}} / {{c.rule||'待补充'}}</dd></div><div><dt>区域</dt><dd>{{channelSources(c).reduce((n,b)=>n+(b.regions?.length??0),0)}} 个（各视频独立配置）</dd></div><div class="wide"><dt>原始需求</dt><dd>{{c.requirement_text||'尚未填写'}}</dd></div><div class="wide"><dt>执行方式与版本</dt><dd>{{c.execution_plan?.executor_kind==='multimodal'?`多模态大模型 ${c.execution_plan.deployment_id} / ${c.execution_plan.deployment_version} · ${c.execution_plan.instruction}`:c.capability_ref?`${c.capability_ref.model_id} / ${c.capability_ref.model_version} · ${c.capability_ref.template_id} / ${c.capability_ref.template_version}`:'尚未绑定'}}</dd></div></dl></article><p v-if="selected.baseline_run_id" class="notice">此版本的复测基线：{{selected.baseline_run_id}}</p></section>
    <HistoryPanel v-else-if="tab==='history'" :agent="agent" :runs="runs" :can-write="canWrite" :runtime-available="workspace?.runtime_available??false" :selected-revision-id="selected.id" @select="selectedId=$event" @view="viewRun" @retry="retry" @retest="retestCreated"/>
    <section v-else-if="tab==='events'" class="panel agent-feature-unavailable" aria-label="人工核查暂未开放"><h2>人工核查</h2><p>当前版本暂未开放</p><small>系统报警仍可在“画面与报警”中查看。</small></section>
    <ExportsPanel v-else :agent-id="agent.id" :runs="runs" :can-write="canWrite" :is-demo="isDemo"/>
  </template>
  <RevisionEditor v-if="editing" :revision="editing" :sources="sources" @close="editing=null;dirty=false" @dirty="dirty=$event" @saving="saving=$event" @saved="saved"/>
  <NModal v-model:show="renameOpen" preset="card" title="修改名称与说明" class="agent-create-modal" :mask-closable="false" :closable="!busy" :close-on-esc="!busy"><form @submit.prevent="rename"><div class="field"><label for="rename-agent">名称</label><NInput :input-props="{id:'rename-agent'}" v-model:value="name" :maxlength="160" :disabled="busy"/></div><div class="field"><label for="rename-description">说明</label><NInput :input-props="{id:'rename-description'}" v-model:value="description" type="textarea" :maxlength="2000" :disabled="busy"/></div><ErrorBanner :error="renameError" :retryable="false"/><NButton type="primary" attr-type="submit" :loading="busy">保存</NButton></form></NModal>
</template>

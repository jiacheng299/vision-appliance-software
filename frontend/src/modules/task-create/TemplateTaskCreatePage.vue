<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref,watch } from 'vue'
import { onBeforeRouteLeave,useRoute,useRouter } from 'vue-router'
import { NButton,NCheckbox,NInput,NInputNumber,NSelect } from 'naive-ui'
import { agentApi,listAgentSources,type AgentDetail,type CapabilityCatalog,type ChannelSource,type Operation,type Revision,type Validation } from '../agents/api'
import { templatesApi,allPublishedTemplates,modelKey,plainModelName,templateError,type AgentTemplate,type TemplateRevision,type ParameterSetting,type ParameterDefinition } from '../agents/templatesApi'
import { retryKey } from './state'
import type { Source } from '../../shared/api/types'
import { channelSources } from '../agents/channelSources'
import { label } from '../agents/state'
import ParameterFields from '../agents/ParameterFields.vue'
import RegionEditor from '../../shared/media/RegionEditor.vue'
import MediaPlayer from '../../shared/media/MediaPlayer.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import './task-create.css'
import '../agents/agents.css'
const route=useRoute(),router=useRouter()
const templates=ref<AgentTemplate[]>([]),sources=ref<Source[]>([]),definitions=ref<ParameterDefinition[]>([]),catalog=ref<CapabilityCatalog|null>(null)
const templateId=ref<string|null>(null),version=ref<TemplateRevision|null>(null),name=ref(''),description=ref('')
const binding=ref<ChannelSource>({source_id:'',regions:[],start_media_ms:null,end_media_ms:null}),parameters=ref<ParameterSetting[]>([])
const agent=ref<AgentDetail|null>(null),revision=ref<Revision|null>(null),validation=ref<Validation|null>(null),operation=ref<Operation|null>(null)
const busy=ref(false),loading=ref(true),error=ref(''),loadError=ref(''),notice=ref(''),pendingRegion=ref(false),ack=ref(false),legacyDraft=ref('')
const saved=ref(''),validated=ref('')
let allowLeave=false,stopped=false,pollTimer:ReturnType<typeof setTimeout>|undefined
const source=computed(()=>sources.value.find(s=>s.id===binding.value.source_id))
const selectedTemplate=computed(()=>templates.value.find(t=>t.id===templateId.value))
const model=computed(()=>catalog.value?.items.find(i=>modelKey(i.reference)===modelKey(version.value?.config.model_ref)))
const signature=computed(()=>JSON.stringify({template:version.value?.id,name:name.value,description:description.value,source:binding.value,parameters:parameters.value}))
const dirty=computed(()=>signature.value!==saved.value),frozen=computed(()=>busy.value||!!operation.value||revision.value?.state==='published'||!!legacyDraft.value)
const executable=computed(()=>validation.value?.verdict==='executable'&&validated.value===signature.value&&Date.parse(validation.value.expires_at)>Date.now())
watch(signature,()=>{validation.value=null;validated.value='';ack.value=false})
function chooseTemplate(id:string|null){
  if(agent.value)return
  templateId.value=id;version.value=templates.value.find(t=>t.id===id)?.published_revision??null
  parameters.value=JSON.parse(JSON.stringify(version.value?.config.parameters??[])) as ParameterSetting[]
  if(!name.value&&selectedTemplate.value)name.value=`${selectedTemplate.value.name}任务`
}
function changeSource(id:string|null){
  if(pendingRegion.value&&!window.confirm('切换视频将放弃尚未保存的区域，确定继续？'))return
  binding.value={source_id:id??'',regions:[],start_media_ms:null,end_media_ms:null};pendingRegion.value=false
}
function check(){
  if(!name.value.trim())throw Error('请填写任务名称。')
  if(!templateId.value||!version.value)throw Error('请选择已发布的智能体模板。')
  if(!binding.value.source_id)throw Error('请选择一个检测视频源。')
  if(pendingRegion.value)throw Error('请先闭合并保存正在绘制的区域。')
}
function displayError(e:unknown){return e instanceof Error&&!('response' in e)?e.message:templateError(e)}
async function persist(){
  check()
  if(!agent.value){
    const body={name:name.value.trim(),description:description.value.trim(),template_revision_id:version.value!.id,source:binding.value,parameters:parameters.value}
    agent.value=await templatesApi.instantiate(templateId.value!,body,retryKey(`template-task:${version.value!.id}`,body));revision.value=agent.value.latest_revision
  }else{
    if(!revision.value)throw Error('任务草稿状态缺失，请重新加载。')
    const config=JSON.parse(JSON.stringify(revision.value.config)) as Revision['config'],channel=config.channels![0]!
    channel.sources=[JSON.parse(JSON.stringify(binding.value))];channel.source_id=null;channel.regions=[];channel.start_media_ms=null;channel.end_media_ms=null
    channel.parameters=JSON.parse(JSON.stringify(parameters.value)) as ParameterSetting[]
    const values=Object.fromEntries(parameters.value.filter(p=>p.value!=null&&p.value!=='').map(p=>[p.key,p.value]))
    channel.target=String(values.target??version.value!.config.default_target??'');channel.rule=String(values.rule??version.value!.config.default_rule??'')
    channel.duration_seconds=typeof values.duration_seconds==='number'?values.duration_seconds:null
    if(agent.value.name!==name.value.trim()||agent.value.description!==description.value.trim())agent.value=await agentApi.rename(agent.value.id,{name:name.value.trim(),description:description.value.trim(),row_version:agent.value.row_version})
    revision.value=await agentApi.save(revision.value,config)
    agent.value=await agentApi.detail(agent.value.id)
  }
  saved.value=signature.value
  await router.replace({path:'/create',query:{draft:agent.value.id}})
  return revision.value!
}
async function save(){if(busy.value)return;busy.value=true;error.value='';try{await persist();notice.value='任务草稿已保存，尚未启动分析。'}catch(e){error.value=displayError(e)}finally{busy.value=false}}
async function evaluate(){if(busy.value)return;busy.value=true;error.value='';try{const r=await persist();validation.value=await agentApi.validate(r);agent.value=await agentApi.detail(agent.value!.id);revision.value=agent.value.latest_revision;validated.value=signature.value;ack.value=false;notice.value='任务验证已完成，请核对结果。'}catch(e){error.value=displayError(e)}finally{busy.value=false}}
async function poll(){
  if(stopped||!agent.value||!operation.value)return
  try{operation.value=await agentApi.operation(agent.value.id,operation.value.id);if(['pending','running'].includes(operation.value.state))pollTimer=setTimeout(()=>void poll(),1000);else if(operation.value.state==='succeeded'){allowLeave=true;await router.push(`/agents/${agent.value.id}/live`)}}catch(e){error.value=displayError(e)}
}
async function start(){
  if(busy.value||!ack.value||!executable.value||!agent.value||!revision.value||!validation.value)return
  busy.value=true;error.value=''
  try{if(revision.value.state==='draft')revision.value=await agentApi.confirm(revision.value,validation.value,retryKey(`template-confirm:${revision.value.id}`,validation.value));const body={revision_id:revision.value.id,channel_ids:revision.value.config.channels!.map(c=>c.channel_id!),expected_active_run_ids:[]};operation.value=await agentApi.submit(agent.value.id,'start',body,retryKey(`template-start:${agent.value.id}`,body));notice.value='启动请求已受理，等待执行器返回最终结果。';void poll()}catch(e){error.value=displayError(e)}finally{busy.value=false}
}
async function initialize(){
  loading.value=true;loadError.value=''
  try{
    const results=await Promise.allSettled([allPublishedTemplates(),listAgentSources(),templatesApi.parameters(),agentApi.catalog()])
    if(stopped)return
    if(results[0].status==='fulfilled')templates.value=results[0].value;else throw results[0].reason
    if(results[1].status==='fulfilled')sources.value=results[1].value;else loadError.value=templateError(results[1].reason)
    if(results[2].status==='fulfilled')definitions.value=results[2].value.items;else throw results[2].reason
    if(results[3].status==='fulfilled')catalog.value=results[3].value
    if(route.query.draft){
      const task=await agentApi.detail(String(route.query.draft)),ref=task.latest_revision.config.agent_template_ref
      if(!ref){legacyDraft.value=task.id;allowLeave=true;return}
      const detail=await templatesApi.detail(ref.template_id)
      if(!templates.value.some(t=>t.id===detail.id))templates.value.push(detail)
      templateId.value=detail.id;version.value=detail.revisions.find(v=>v.id===ref.revision_id)??null
      if(!version.value)throw Error('任务引用的模板版本不存在。')
      agent.value=task;revision.value=task.latest_revision;name.value=task.name;description.value=task.description
      const channel=task.latest_revision.config.channels![0]!
      binding.value=JSON.parse(JSON.stringify(channelSources(channel)[0])) as ChannelSource
      parameters.value=JSON.parse(JSON.stringify(channel.parameters??[])) as ParameterSetting[]
    }else if(route.query.template)chooseTemplate(String(route.query.template))
    saved.value=signature.value
  }catch(e){loadError.value=displayError(e)}finally{loading.value=false}
}
onMounted(()=>void initialize())
onBeforeRouteLeave(()=>allowLeave||!dirty.value||window.confirm('任务包含未保存的配置，确定离开？'))
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value||busy.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{stopped=true;clearTimeout(pollTimer);window.removeEventListener('beforeunload',beforeUnload)})
</script>
<template>
  <div class="page-heading"><div><h1>任务创建</h1><p>选择智能体模板，配置一个视频源及检测条件，再验证和启动</p></div><RouterLink to="/agents">管理智能体模板</RouterLink></div>
  <ErrorBanner :error="loadError" @retry="initialize"/><ErrorBanner :error="error" :retryable="false"/><p v-if="notice" class="notice">{{notice}}</p><div v-if="loading" class="loading-line"/>
  <section v-if="legacyDraft" class="panel"><h2>历史任务配置</h2><p>此任务创建于模板关联功能启用前，原配置与自然语言执行方案完整保留。</p><RouterLink :to="{path:'/create/legacy',query:{draft:legacyDraft}}">继续编辑历史任务</RouterLink></section>
  <div v-else class="create-layout"><section class="panel create-main">
    <h2>1. 选择智能体模板</h2><div class="field"><label>智能体模板</label><NSelect :value="templateId" :options="templates.map(t=>({label:t.name,value:t.id}))" :disabled="busy||!!agent" filterable placeholder="选择已发布模板，例如：火灾检测" aria-label="选择智能体模板" @update:value="chooseTemplate"/></div>
    <p v-if="!templates.length&&!loading" class="notice">暂无已发布模板，请先在智能体管理中新建并发布模板。</p>
    <p v-if="version" class="hint">模板版本 v{{version.revision_no}} · {{model?plainModelName(model.name):version.config.model_ref?.model_id}} {{version.config.model_ref?.model_version}}。任务保存后固定使用此版本。</p>
    <fieldset :disabled="frozen" class="create-fields"><h2 class="agent-section-title">2. 配置检测视频</h2>
      <div class="field"><label>任务名称</label><NInput v-model:value="name" :disabled="frozen" :maxlength="160" aria-label="任务名称" placeholder="例如：一号仓库火灾检测"/></div><div class="field"><label>任务说明</label><NInput v-model:value="description" :disabled="frozen" type="textarea" :maxlength="2000" aria-label="任务说明"/></div>
      <div class="field"><label>检测视频源</label><NSelect :value="binding.source_id||null" :options="sources.map(s=>({label:`${s.name} · ${s.kind==='file'?'录像文件':'监控直播'}`,value:s.id}))" :disabled="frozen" filterable placeholder="选择一路视频" aria-label="检测视频源" @update:value="changeSource"/></div>
      <template v-if="source"><MediaPlayer :source="source"/><template v-if="source.kind==='file'"><div class="field-grid"><div class="field"><label>录像开始位置（秒，选填）</label><NInputNumber :value="binding.start_media_ms==null?null:binding.start_media_ms/1000" :disabled="frozen" :min="0" :precision="3" aria-label="任务录像开始位置" @update:value="binding.start_media_ms=$event==null?null:Math.round($event*1000)"/></div><div class="field"><label>录像结束位置（秒，选填）</label><NInputNumber :value="binding.end_media_ms==null?null:binding.end_media_ms/1000" :disabled="frozen" :min="0" :precision="3" aria-label="任务录像结束位置" @update:value="binding.end_media_ms=$event==null?null:Math.round($event*1000)"/></div></div></template><div class="field"><label>检测区域</label><RegionEditor :regions="binding.regions??[]" :source="source" :disabled="frozen" :demo="catalog?.data_origin==='mock'" @change="binding.regions=$event" @pending="pendingRegion=$event"/></div></template>
      <h2 class="agent-section-title">3. 设置模板条件</h2><ParameterFields :settings="parameters" @update:settings="parameters=$event" :definitions="definitions" :model="model" :disabled="frozen||!version"/>
    </fieldset>
    <div class="agent-actions"><NButton :disabled="frozen||!version||loading" :loading="busy" @click="save">保存任务草稿</NButton><NButton type="primary" :disabled="frozen||!version||loading" :loading="busy" @click="evaluate">验证任务</NButton></div>
  </section><aside class="panel create-summary"><h2>任务执行依据</h2><p>模板：{{selectedTemplate?.name??'尚未选择'}}</p><p>版本：{{version?`v${version.revision_no}`:'尚未选择'}}</p><p>视频：{{source?.name??'尚未选择'}}</p><p class="notice">修改模板不会改变本任务。只有验证通过并确认后才会启动分析。</p>
    <section v-if="validation" class="create-assessment"><h3>{{label(validation.verdict)}}</h3><ul><li v-for="message in [...(validation.missing_conditions??[]),...(validation.unsupported_conditions??[]),...(validation.evidence_limitations??[])]" :key="message">{{message}}</li></ul></section>
    <NCheckbox v-model:checked="ack" :disabled="!executable||busy||!!operation">已核对模板版本、视频范围和检测条件</NCheckbox><NButton block type="primary" :disabled="!executable||!ack||busy||!!operation" :loading="busy" @click="start">确认启动</NButton>
    <p v-if="operation" class="notice">{{label(operation.state)}} · {{operation.message}}</p><NButton v-if="operation" :disabled="busy" @click="poll">刷新启动状态</NButton><RouterLink v-if="agent" :to="`/agents/${agent.id}/live`">查看任务详情</RouterLink>
  </aside></div>
</template>

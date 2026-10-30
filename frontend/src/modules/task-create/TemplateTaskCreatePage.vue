<script setup lang="ts">
import { computed,onBeforeUnmount,onMounted,ref,watch } from 'vue'
import { onBeforeRouteLeave,useRoute,useRouter } from 'vue-router'
import { NButton,NCheckbox,NInput,NInputNumber,NSelect } from 'naive-ui'
import { Plus,Video,Trash2,Info } from 'lucide-vue-next'
import { agentApi,listAgentSources,type AgentDetail,type CapabilityCatalog,type ChannelSource,type Operation,type Revision,type Validation } from '../agents/api'
import { templatesApi,allPublishedTemplates,modelKey,templateError,type AgentTemplate,type TemplateRevision,type TemplateConfig,type ParameterSetting,type ParameterDefinition } from '../agents/templatesApi'
import { retryKey } from './state'
import type { Source } from '../../shared/api/types'
import { channelSources } from '../agents/channelSources'
import { label } from '../agents/state'
import TaskConditions from './TaskConditions.vue'
import TemplateSelection from './TemplateSelection.vue'
import RegionEditor from '../../shared/media/RegionEditor.vue'
import MediaPlayer from '../../shared/media/MediaPlayer.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import { regionError,type Point } from '../../shared/media/regionGeometry'
import { safeMediaUrl } from '../../shared/media/url'
import './task-create.css'
import '../agents/agents.css'
import './template-task-create.css'
const route=useRoute(),router=useRouter()
const templates=ref<AgentTemplate[]>([]),sources=ref<Source[]>([]),definitions=ref<ParameterDefinition[]>([]),catalog=ref<CapabilityCatalog|null>(null)
const templateId=ref<string|null>(null),version=ref<TemplateRevision|null>(null),name=ref(''),description=ref('')
const step=ref(0)
const activeIndex=ref(0)
const bindings=ref<ChannelSource[]>([{source_id:'',regions:[],start_media_ms:null,end_media_ms:null}]),parameters=ref<ParameterSetting[]>([])
const agent=ref<AgentDetail|null>(null),revision=ref<Revision|null>(null),validation=ref<Validation|null>(null),operation=ref<Operation|null>(null)
const busy=ref(false),loading=ref(true),error=ref(''),loadError=ref(''),notice=ref(''),pendingRegions=ref<Record<string,boolean>>({}),ack=ref(false),legacyDraft=ref('')
const pendingRegion=computed(()=>Object.values(pendingRegions.value).some(Boolean))
const saved=ref(''),validated=ref(''),validationClock=ref(Date.now())
let allowLeave=false,stopped=false,pollTimer:ReturnType<typeof setTimeout>|undefined,validationTimer:ReturnType<typeof setTimeout>|undefined
const sourceFor=(b:ChannelSource)=>sources.value.find(s=>s.id===b.source_id)
const activeBinding=computed(()=>bindings.value[activeIndex.value])
const activeSource=computed(()=>activeBinding.value?sourceFor(activeBinding.value):undefined)
const selectedTemplate=computed(()=>templates.value.find(t=>t.id===templateId.value))
const model=computed(()=>catalog.value?.items.find(i=>modelKey(i.reference)===modelKey(version.value?.config.model_ref)))
const currentRule=computed(()=>String(parameters.value.find(p=>p.key==='rule')?.value??version.value?.config.default_rule??''))
const signature=computed(()=>JSON.stringify({template:version.value?.id,name:name.value,description:description.value,sources:bindings.value,parameters:parameters.value}))
const dirty=computed(()=>signature.value!==saved.value||pendingRegion.value),frozen=computed(()=>busy.value||!!operation.value||revision.value?.state==='published'||!!legacyDraft.value||!version.value)
const executable=computed(()=>!pendingRegion.value&&validation.value?.verdict==='executable'&&validated.value===signature.value&&Date.parse(validation.value.expires_at)>validationClock.value)
watch(signature,()=>{validation.value=null;validated.value='';ack.value=false})
function trackValidationExpiry(){
  clearTimeout(validationTimer);validationClock.value=Date.now()
  if(!validation.value)return
  const remaining=Date.parse(validation.value.expires_at)-validationClock.value
  if(remaining>0)validationTimer=setTimeout(trackValidationExpiry,Math.min(remaining+1,2_147_483_647))
  else ack.value=false
}
watch(validation,trackValidationExpiry,{flush:'sync'})
function selectVersion(row?:AgentTemplate){
  templateId.value=row?.id??null;version.value=row?.published_revision??null
  parameters.value=JSON.parse(JSON.stringify(version.value?.config.parameters??[])) as ParameterSetting[]
  bindings.value=[JSON.parse(JSON.stringify((version.value?.config as TemplateConfig|undefined)?.default_source??{source_id:'',regions:[],start_media_ms:null,end_media_ms:null})) as ChannelSource]
  pendingRegions.value={}
  activeIndex.value=0
  if(!name.value&&selectedTemplate.value)name.value=`${selectedTemplate.value.name}任务`
}
function chooseTemplate(id:string|null){
  if(agent.value||busy.value||id===templateId.value)return
  selectVersion(templates.value.find(t=>t.id===id&&!t.archived_at&&t.published_revision?.state==='published'))
}
function goStep(target:number){
  if(busy.value||operation.value)return
  if(pendingRegion.value){error.value='请先闭合并保存正在绘制的区域。';return}
  if(target>0&&!version.value)return
  if(target===2&&!validation.value&&revision.value?.state!=='published')return
  step.value=target;error.value=''
}
function changeSource(index:number,id:string|null){
  if(frozen.value)return
  const old=bindings.value[index];if(!old||id===old.source_id)return
  if(id&&bindings.value.some((b,i)=>i!==index&&b.source_id===id)){error.value='同一任务不能重复选择相同视频源。';return}
  if(pendingRegions.value[old.source_id]&&!window.confirm('切换视频将放弃尚未保存的区域，确定继续？'))return
  delete pendingRegions.value[old.source_id]
  bindings.value[index]={source_id:id??'',regions:[],start_media_ms:null,end_media_ms:null}
}
function switchSource(index:number){
  if(busy.value||index===activeIndex.value)return
  if(pendingRegion.value){error.value='请先闭合并保存正在绘制的区域。';return}
  activeIndex.value=index;error.value=''
}
function addSource(){
  if(frozen.value||bindings.value.length>=16)return
  if(pendingRegion.value){error.value='请先闭合并保存正在绘制的区域。';return}
  bindings.value.push({source_id:'',regions:[],start_media_ms:null,end_media_ms:null});activeIndex.value=bindings.value.length-1
}
function removeSource(index:number){
  if(frozen.value||bindings.value.length<=1)return
  const old=bindings.value[index]!
  if(pendingRegions.value[old.source_id]&&!window.confirm('移除视频将放弃其正在绘制的区域，确定继续？'))return
  delete pendingRegions.value[old.source_id];bindings.value.splice(index,1)
  if(activeIndex.value>index)activeIndex.value--
  else if(activeIndex.value>=bindings.value.length)activeIndex.value=bindings.value.length-1
}
function check(){
  if(!name.value.trim())throw Error('请填写任务名称。')
  if(!templateId.value||!version.value)throw Error('请选择已发布的智能体模板。')
  if(!bindings.value.length||bindings.value.some(b=>!b.source_id))throw Error('请选择一个检测视频源，并补全每一路视频选择。')
  if(new Set(bindings.value.map(b=>b.source_id)).size!==bindings.value.length)throw Error('同一任务不能重复选择相同视频源。')
  if(pendingRegion.value)throw Error('请先闭合并保存正在绘制的区域。')
  for(const binding of bindings.value){
    const source=sourceFor(binding)
    if(!source||!['ready','online'].includes(source.status))throw Error('视频源当前不可访问，请重新选择可用视频源。')
    for(const region of binding.regions??[]){const invalid=regionError(region.points as Point[]);if(invalid)throw Error(`检测区域无效：${invalid}`)}
    const {start_media_ms:start,end_media_ms:end}=binding
    if(source.kind==='camera'&&(start!=null||end!=null))throw Error('监控直播不能设置录像范围，请重新选择视频源。')
    if((start!=null&&(!Number.isFinite(start)||start<0))||(end!=null&&(!Number.isFinite(end)||end<=0))||(start!=null&&end!=null&&start>=end)||(source.duration_ms!=null&&((start??0)>=source.duration_ms||(end??0)>source.duration_ms)))throw Error('请核对录像起止位置，范围必须位于当前视频内。')
  }
}
function displayError(e:unknown){return e instanceof Error&&!('response' in e)?e.message:templateError(e)}
async function persist(){
  check()
  if(!agent.value){
    const body={name:name.value.trim(),description:description.value.trim(),template_revision_id:version.value!.id,...(bindings.value.length===1?{source:bindings.value[0]!}:{sources:bindings.value}),parameters:parameters.value}
    agent.value=await templatesApi.instantiate(templateId.value!,body,retryKey(`template-task:${version.value!.id}`,body));revision.value=agent.value.latest_revision
  }else{
    if(!revision.value)throw Error('任务草稿状态缺失，请重新加载。')
    const config=JSON.parse(JSON.stringify(revision.value.config)) as Revision['config'],channel=config.channels![0]!
    channel.sources=JSON.parse(JSON.stringify(bindings.value));channel.source_id=null;channel.regions=[];channel.start_media_ms=null;channel.end_media_ms=null
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
async function evaluate(){if(busy.value)return;busy.value=true;error.value='';try{const r=await persist();validation.value=await agentApi.validate(r);agent.value=await agentApi.detail(agent.value!.id);revision.value=agent.value.latest_revision;validated.value=signature.value;ack.value=false;step.value=2;notice.value='任务验证已完成，请核对结果。'}catch(e){error.value=displayError(e)}finally{busy.value=false}}
async function poll(){
  if(stopped||!agent.value||!operation.value)return
  try{operation.value=await agentApi.operation(agent.value.id,operation.value.id);if(['pending','running'].includes(operation.value.state))pollTimer=setTimeout(()=>void poll(),1000);else if(operation.value.state==='succeeded'){allowLeave=true;await router.push(`/agents/${agent.value.id}/live`)}}catch(e){error.value=displayError(e)}
}
async function start(){
  if(busy.value||!ack.value||!executable.value||!agent.value||!revision.value||!validation.value)return
  if(!(Date.parse(validation.value.expires_at)>Date.now())){trackValidationExpiry();error.value='验证已过期，请重新验证任务。';return}
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
      bindings.value=JSON.parse(JSON.stringify(channelSources(channel).length?channelSources(channel):[{source_id:'',regions:[],start_media_ms:null,end_media_ms:null}])) as ChannelSource[]
      parameters.value=JSON.parse(JSON.stringify(channel.parameters??[])) as ParameterSetting[]
      step.value=revision.value.state==='published'?2:1
    }else if(route.query.template)chooseTemplate(String(route.query.template))
    saved.value=signature.value
  }catch(e){loadError.value=displayError(e)}finally{loading.value=false}
}
onMounted(()=>void initialize())
onBeforeRouteLeave(()=>allowLeave||!dirty.value||window.confirm('任务包含未保存的配置，确定离开？'))
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value||busy.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{stopped=true;clearTimeout(pollTimer);clearTimeout(validationTimer);window.removeEventListener('beforeunload',beforeUnload)})
</script>
<template>
  <div class="tc-page">
  <div class="page-heading"><div><h1>创建监测任务 <small class="tc-draft">草稿</small></h1><p>先确定监测模板，再配置视频与检测区域</p></div><RouterLink to="/agents">返回任务列表</RouterLink></div>
  <ErrorBanner :error="loadError" @retry="initialize"/><ErrorBanner :error="error" :retryable="false"/><p v-if="notice" class="notice">{{notice}}</p><div v-if="loading" class="loading-line"/>
  <section v-if="legacyDraft" class="panel"><h2>历史任务配置</h2><p>此任务创建于模板关联功能启用前，原配置与自然语言执行方案完整保留。</p><RouterLink :to="{path:'/create/legacy',query:{draft:legacyDraft}}">继续编辑历史任务</RouterLink></section>
  <template v-else>
  <nav class="tc-steps" aria-label="任务创建步骤"><button v-for="(title,index) in ['选择模板','配置视频与区域','验证并启动']" :key="title" :class="{active:step===index,complete:step>index}" :aria-current="step===index?'step':undefined" :disabled="busy||!!operation||loading||(index>0&&!version)||(index===2&&!validation&&revision?.state!=='published')" @click="goStep(index)"><span>{{index+1}}</span>{{title}}</button></nav>
  <TemplateSelection v-show="step===0" :templates="templates" :selected-id="templateId" :version="version" :disabled="busy||!!agent||loading" @select="chooseTemplate"/>
  <div class="tc-basic-layout"><section v-show="step===1" class="panel create-main">
    <p class="hint">{{selectedTemplate?.name}} · 模板版本 v{{version?.revision_no}} · 共用规则，各路独立监测与报警</p>
    <fieldset class="create-fields">
      <div class="tc-identity"><div class="field"><label>任务名称</label><NInput v-model:value="name" :disabled="frozen" :maxlength="160" aria-label="任务名称" placeholder="例如：园区人员在岗监测"/></div><div class="tc-pinned-template"><label>智能体模板</label><strong>{{selectedTemplate?.name}} · v{{version?.revision_no}}</strong><span>已确认模板</span></div><details><summary>任务说明（选填）</summary><NInput v-model:value="description" :disabled="frozen" type="textarea" :maxlength="2000" aria-label="任务说明"/></details></div>
      <div class="tc-video-workspace">
        <aside class="tc-sources" aria-label="监控视频列表"><div class="tc-section-heading"><h2>监控视频 <small>{{bindings.length}} 路</small></h2><NButton size="small" :disabled="frozen||bindings.length>=16" @click="addSource"><Plus :size="14"/>添加视频源</NButton></div>
          <article v-for="(binding,index) in bindings" :key="binding.source_id||`empty-${index}`" :class="['tc-source-card',{active:activeIndex===index}]">
            <div class="tc-source-top"><button type="button" class="tc-source-select" :aria-label="`配置视频${index+1}`" :aria-current="activeIndex===index?'true':undefined" :disabled="busy" @click="switchSource(index)"><span class="tc-thumbnail"><img v-if="safeMediaUrl(sourceFor(binding)?.thumbnail_url??null)" :src="safeMediaUrl(sourceFor(binding)?.thumbnail_url??null)!" alt="视频源缩略图"/><Video v-else :size="23"/></span><span><strong>{{sourceFor(binding)?.name??`视频 ${index+1}`}}</strong><small>{{sourceFor(binding)?label(sourceFor(binding)!.status):'请选择视频源'}}</small><small :class="{'tc-configured':(binding.regions?.length??0)>0}">{{binding.regions?.length?`${binding.regions.length} 个区域 · 已配置`:'尚未设置区域'}}</small></span></button><button v-if="bindings.length>1" type="button" class="tc-remove" :disabled="frozen" :aria-label="`移除视频${index+1}`" @click="removeSource(index)"><Trash2 :size="14"/></button></div>
            <NSelect :value="binding.source_id||null" :options="sources.map(s=>({label:s.name,value:s.id,disabled:bindings.some((b,i)=>i!==index&&b.source_id===s.id)}))" :disabled="frozen" filterable placeholder="选择本路视频" :aria-label="index===0?'检测视频源':`检测视频源${index+1}`" @update:value="changeSource(index,$event)"/>
          </article><p class="tc-source-hint">各视频分别设置区域。每路占用一个并发名额，超过上限的运行会排队。</p>
        </aside>
        <section class="tc-preview" aria-label="当前视频配置"><div class="tc-section-heading"><h2>{{activeSource?.name??'配置视频与监测区域'}}</h2><span v-if="activeSource" class="tc-source-kind">{{activeSource.kind==='camera'?'监控直播':'录像文件'}}</span></div>
          <template v-if="activeSource&&activeBinding">
            <RegionEditor :key="`${version?.id}:${activeBinding.source_id}`" :regions="activeBinding.regions??[]" :source="activeSource" :disabled="frozen" :demo="catalog?.data_origin==='mock'" @change="activeBinding.regions=$event" @pending="pendingRegions[activeBinding.source_id]=$event"/>
            <template v-if="activeSource.kind==='file'"><div class="field-grid tc-file-range"><div class="field"><label>录像开始位置（秒）</label><NInputNumber :value="activeBinding.start_media_ms==null?null:activeBinding.start_media_ms/1000" :disabled="frozen" :min="0" :precision="3" aria-label="任务录像开始位置" @update:value="activeBinding.start_media_ms=$event==null?null:Math.round($event*1000)"/></div><div class="field"><label>录像结束位置（秒）</label><NInputNumber :value="activeBinding.end_media_ms==null?null:activeBinding.end_media_ms/1000" :disabled="frozen" :min="0" :precision="3" aria-label="任务录像结束位置" @update:value="activeBinding.end_media_ms=$event==null?null:Math.round($event*1000)"/></div></div><details class="tc-original-preview"><summary>预览原始录像</summary><MediaPlayer :source="activeSource"/></details></template>
            <p v-else class="tc-preview-hint"><Info :size="15"/>直播使用静态帧划区，可重新选取当前帧，无需设置录像起止时间。</p>
          </template><div v-else class="tc-no-source"><Video :size="42"/><h3>先选择本路视频</h3><p>从左侧选择摄像头或录像，再设置监测区域。</p></div>
        </section>
        <TaskConditions :settings="parameters" @update:settings="parameters=$event" :definitions="definitions" :model="model" :source-count="bindings.length" :rule="currentRule" :disabled="frozen||!version"/>
      </div>
    </fieldset>
  </section><aside v-show="step===2" class="panel create-summary"><h2>核对配置与验证结果</h2><p>模板：{{selectedTemplate?.name??'尚未选择'}}</p><p>模板版本 {{version?`v${version.revision_no}`:'尚未选择'}}</p><p>视频：{{bindings.filter(b=>b.source_id).length}} 路</p><p v-for="(b,index) in bindings" :key="index">{{index+1}}. {{sourceFor(b)?.name??'尚未选择'}} · {{b.regions?.length??0}} 个区域</p><p class="notice">所有视频共用检测条件，报警独立记录。只有验证通过并确认后才会启动分析。</p>
    <section v-if="validation" class="create-assessment"><h3>{{label(validation.verdict)}}</h3><ul><li v-for="message in [...(validation.missing_conditions??[]),...(validation.unsupported_conditions??[]),...(validation.evidence_limitations??[])]" :key="message">{{message}}</li></ul></section>
    <NCheckbox v-model:checked="ack" :disabled="!executable||busy||!!operation">已核对模板版本、视频范围和检测条件</NCheckbox>
    <p v-if="operation" class="notice">{{label(operation.state)}} · {{operation.message}}</p><NButton v-if="operation" :disabled="busy" @click="poll">刷新启动状态</NButton><RouterLink v-if="agent" :to="`/agents/${agent.id}/live`">查看任务详情</RouterLink>
  </aside></div>
  <footer class="tc-footer"><div><strong v-if="version">已选择：{{selectedTemplate?.name}} · v{{version.revision_no}}</strong><strong v-else>请选择一个已发布模板</strong><p>{{step===0?'确认后进入视频与区域配置':step===1?`${bindings.filter(b=>b.source_id).length} 路视频 · 共用规则，各路独立报警`:'验证通过后，核对并确认启动'}}</p></div><div class="agent-actions">
    <NButton v-if="step===0" type="primary" aria-label="确认模板，下一步" :disabled="!version||busy||loading||!!loadError" @click="goStep(1)">确认模板，下一步</NButton>
    <template v-if="step===1"><NButton :disabled="busy||!!operation" @click="goStep(0)">上一步</NButton><NButton :disabled="frozen||loading" :loading="busy" @click="save">保存草稿</NButton><NButton type="primary" :disabled="frozen||loading" :loading="busy" @click="evaluate">验证任务</NButton></template>
    <template v-if="step===2"><NButton :disabled="busy||!!operation" @click="goStep(1)">返回修改配置</NButton><NButton type="primary" aria-label="确认启动" :disabled="!executable||!ack||busy||!!operation" :loading="busy" @click="start">确认启动</NButton></template>
  </div></footer>
  </template>
  </div>
</template>
<style scoped>
.tc-draft{display:inline-block;font-size:11px;padding:4px 9px;background:#e2edff;color:#2367ed;border-radius:5px;vertical-align:middle;margin-left:10px}.tc-steps{display:flex;gap:20px;margin:24px 0}.tc-steps button{flex:1;display:flex;align-items:center;gap:12px;padding:12px;border:0;background:transparent;font:inherit;color:#8491a6;text-align:left}.tc-steps button.active{color:#2367ed;font-weight:650}.tc-steps button.complete{color:#2d936a}.tc-steps button span{display:grid;place-items:center;width:30px;height:30px;border:1px solid #d5deed;border-radius:50%}.tc-steps button.active span{background:#2367ed;color:white;border-color:#2367ed}.tc-basic-layout .create-summary{position:static}.tc-footer{position:sticky;bottom:0;z-index:20;display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:20px;padding:18px 20px;background:#fff;border:1px solid #e4eaf3;border-radius:8px;box-shadow:0 -4px 16px #16305b06}.tc-footer strong{font-size:13px;color:#263951}.tc-footer p{font-size:11px;color:#8390a5;margin-top:7px}.tc-footer .agent-actions{margin:0}
</style>

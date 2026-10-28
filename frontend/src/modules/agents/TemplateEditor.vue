<script setup lang="ts">
import { computed,onBeforeUnmount,ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { NButton,NDrawer,NDrawerContent,NInput,NInputNumber,NSelect } from 'naive-ui'
import { agentApi,listAgentSources,type CapabilityCatalog } from './api'
import type { Source } from '../../shared/api/types'
import { templatesApi,modelKey,plainModelName,templateError,type AgentTemplate,type TemplateConfig,type ParameterDefinition } from './templatesApi'
import { newId } from '../../shared/ids'
import ParameterFields from './ParameterFields.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import RegionEditor from '../../shared/media/RegionEditor.vue'
const props=defineProps<{row?:AgentTemplate}>()
const emit=defineEmits<{close:[];saved:[row:AgentTemplate]}>()
const name=ref(props.row?.name??''),description=ref(props.row?.description??'')
const config=ref<TemplateConfig>(JSON.parse(JSON.stringify(props.row?.latest_revision.config??{model_ref:null,parameters:[]})))
const catalog=ref<CapabilityCatalog|null>(null),definitions=ref<ParameterDefinition[]>([]),error=ref(''),catalogError=ref(''),saving=ref(false)
const sources=ref<Source[]>([]),sourceError=ref(''),pendingRegion=ref(false)
let disposed=false,token='',signature=''
const currentRow=ref<AgentTemplate|undefined>(props.row)
const body=computed(()=>({name:name.value.trim(),description:description.value.trim(),config:config.value}))
const baseline=ref(JSON.stringify(body.value)),dirty=computed(()=>JSON.stringify(body.value)!==baseline.value||pendingRegion.value)
const selectedSource=computed(()=>sources.value.find(s=>s.id===config.value.default_source?.source_id))
const selectedModel=computed(()=>catalog.value?.items.find(i=>modelKey(i.reference)===modelKey(config.value.model_ref)))
const targetNames=computed(()=>selectedModel.value?.targets.map(value=>definitions.value.find(d=>d.key==='target')?.options?.find(o=>o.value===value)?.label??value).join('、'))
async function load(){
  const results=await Promise.allSettled([agentApi.catalog(),templatesApi.parameters(),listAgentSources()]);if(disposed)return
  const [models,parameters,videos]=results
  if(models.status==='fulfilled'){catalog.value=models.value;catalogError.value=''}else catalogError.value=templateError(models.reason)
  if(parameters.status==='fulfilled')definitions.value=parameters.value.items;else error.value=templateError(parameters.reason)
  if(videos.status==='fulfilled'){sources.value=videos.value;sourceError.value=''}else sourceError.value=templateError(videos.reason)
}
void load()
function selectModel(value:string|null){config.value.model_ref=catalog.value?.items.find(i=>modelKey(i.reference)===value)?.reference??null}
function selectSource(id:string|null){
  if(saving.value||id===config.value.default_source?.source_id)return
  if(pendingRegion.value&&!window.confirm('切换视频将放弃尚未保存的区域，确定继续？'))return
  config.value.default_source=id?{source_id:id,regions:[],start_media_ms:null,end_media_ms:null}:null;pendingRegion.value=false
}
function close(){if(!saving.value&&(!dirty.value||window.confirm('模板包含未保存的修改，确定放弃？')))emit('close')}
onBeforeRouteLeave(()=>!saving.value&&(!dirty.value||window.confirm('模板包含未保存的修改，确定离开？')))
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value||saving.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>{disposed=true;window.removeEventListener('beforeunload',beforeUnload)})
async function save(publish=false){
  if(saving.value)return
  if(!body.value.name){error.value='请填写模板名称。';return}
  if(!definitions.value.length&&config.value.parameters?.length){error.value='配置项目录不可用，请重新加载后保存。';return}
  if(pendingRegion.value){error.value='请先闭合并保存正在绘制的默认区域。';return}
  if(config.value.default_source&&(!selectedSource.value||!['ready','online'].includes(selectedSource.value.status))){error.value='默认视频源当前不可访问，请重新选择或清除默认视频源。';return}
  saving.value=true;error.value=''
  try{
    let result:AgentTemplate
    if(currentRow.value)result=await templatesApi.save(currentRow.value,body.value)
    else{const encoded=JSON.stringify(body.value);if(signature!==encoded||!token){signature=encoded;token=newId()}result=await templatesApi.create(body.value,token)}
    currentRow.value=result
    baseline.value=JSON.stringify(body.value)
    if(publish){const encoded=`publish:${result.id}:${result.row_version}`;if(signature!==encoded){signature=encoded;token=newId()}result=await templatesApi.publish(result,token);currentRow.value=result}
    if(!disposed)emit('saved',result)
  }catch(e){if(!disposed)error.value=templateError(e)}finally{saving.value=false}
}
</script>
<template>
  <NDrawer :show="true" placement="right" width="min(100vw, max(720px, 55vw))" :mask-closable="!saving" :close-on-esc="!saving" @update:show="show=>{if(!show)close()}">
    <NDrawerContent :title="row?'编辑智能体模板':'新建智能体模板'" :closable="!saving" @close="close">
      <div class="agent-create-intro"><span class="agent-create-eyebrow">可复用任务模板</span><h2>模板基础配置</h2><p>配置模板业务、分析模型和可选条件。任务选择已发布模板后，再配置具体视频及检测区域。</p></div>
      <p v-if="row?.published_revision" class="notice">本次修改将生成新版本，既有任务继续使用创建时的模板版本。</p>
      <p v-if="row?.imported_from_agent_id" class="notice">此模板由历史智能体配置登记。请核对模型及条件后发布，原任务与运行记录保持不变。</p>
      <ErrorBanner :error="error" :retryable="false"/>
      <section class="agent-create-section"><h3>业务定义</h3><div class="field"><label>模板名称</label><NInput v-model:value="name" :disabled="saving" :maxlength="160" placeholder="例如：火灾检测" aria-label="模板名称"/></div><div class="field"><label>业务说明</label><NInput v-model:value="description" type="textarea" :disabled="saving" :maxlength="2000" placeholder="说明该模板可完成的具体检测任务" aria-label="模板业务说明"/></div></section>
      <section class="agent-create-section"><h3>选择模型</h3><ErrorBanner :error="catalogError" @retry="load"/><div class="field"><label>模型</label><NSelect :value="modelKey(config.model_ref)" :options="catalog?.items.map(i=>({label:`${plainModelName(i.name)} · ${i.reference.model_version}`,value:modelKey(i.reference)!}))??[]" :disabled="saving||!!catalogError" clearable filterable placeholder="选择分析模型" aria-label="选择模型" @update:value="selectModel"/></div><p v-if="selectedModel" class="hint">模型支持 {{targetNames}} 等检测对象；具体条件从下方配置项池选择。</p><p v-else-if="config.model_ref" class="hint">原模型版本暂不在可用目录中，历史引用已保留；重新发布前须确认模型可用。</p></section>
      <section class="agent-create-section"><h3>可选配置项</h3><ParameterFields :settings="config.parameters??[]" @update:settings="config.parameters=$event" :definitions="definitions" :model="selectedModel" selectable :disabled="saving"/></section>
      <section class="agent-create-section"><h3>默认视频（选填）</h3><p class="hint">任务会继承此视频及检测范围，也可改选其他视频。留空时，创建任务必须选择视频。</p><ErrorBanner :error="sourceError" @retry="load"/><div class="field"><label>默认视频源</label><NSelect :value="config.default_source?.source_id??null" :options="sources.map(s=>({label:`${s.name} · ${s.kind==='file'?'录像文件':'监控直播'}`,value:s.id,disabled:!['ready','online'].includes(s.status)}))" :disabled="saving" clearable filterable aria-label="模板默认视频源" placeholder="不设置默认视频" @update:value="selectSource"/></div>
        <template v-if="config.default_source&&selectedSource"><div v-if="selectedSource.kind==='file'" class="field-grid"><div class="field"><label>录像开始位置（秒，选填）</label><NInputNumber :value="config.default_source.start_media_ms==null?null:config.default_source.start_media_ms/1000" :disabled="saving" :min="0" :precision="3" aria-label="模板默认录像开始位置" @update:value="config.default_source.start_media_ms=$event==null?null:Math.round($event*1000)"/></div><div class="field"><label>录像结束位置（秒，选填）</label><NInputNumber :value="config.default_source.end_media_ms==null?null:config.default_source.end_media_ms/1000" :disabled="saving" :min="0" :precision="3" aria-label="模板默认录像结束位置" @update:value="config.default_source.end_media_ms=$event==null?null:Math.round($event*1000)"/></div></div><RegionEditor :key="config.default_source.source_id" :regions="config.default_source.regions??[]" :source="selectedSource" :disabled="saving" :demo="catalog?.data_origin==='mock'" @change="config.default_source.regions=$event" @pending="pendingRegion=$event"/></template>
      </section>
      <template #footer><div class="agent-create-footer"><p>发布模板不会启动任务，也不会更新旧任务。</p><div class="agent-actions"><NButton :disabled="saving" @click="close">取消</NButton><NButton :disabled="saving" :loading="saving" @click="save(false)">保存草稿</NButton><NButton type="primary" :disabled="saving||!config.model_ref" :loading="saving" @click="save(true)">保存并发布</NButton></div></div></template>
    </NDrawerContent>
  </NDrawer>
</template>

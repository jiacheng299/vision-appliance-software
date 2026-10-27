<script setup lang="ts">
import { onBeforeUnmount,ref,watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton,NInput } from 'naive-ui'
import { templatesApi,modelKey,plainModelName,templateError,type AgentTemplate } from './templatesApi'
import { agentApi,type CapabilityCatalog } from './api'
import { environment } from '../../shared/environment'
import { newId } from '../../shared/ids'
import { formatDate } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import Icon from '../../shared/ui/Icon.vue'
import TemplateEditor from './TemplateEditor.vue'
import './agents.css'
const router=useRouter(),items=ref<AgentTemplate[]>([]),catalog=ref<CapabilityCatalog|null>(null),query=ref(''),archived=ref(false)
const loading=ref(false),error=ref(''),cursor=ref<string|null>(null),editing=ref<AgentTemplate|null|undefined>(undefined),seeding=ref(false)
let generation=0,timer:ReturnType<typeof setTimeout>|undefined,disposed=false,demoRow:AgentTemplate|undefined
const demoKey=newId()
async function load(more=false){
  const request=++generation;loading.value=true;error.value=''
  try{const page=await templatesApi.list(query.value,more?cursor.value??undefined:undefined,false,archived.value);if(request!==generation||disposed)return;items.value=more?[...items.value,...page.items.filter(i=>!items.value.some(old=>old.id===i.id))]:page.items;cursor.value=page.next_cursor??null}catch(e){if(request===generation&&!disposed)error.value=templateError(e)}finally{if(request===generation)loading.value=false}
}
watch([query,archived],()=>{clearTimeout(timer);generation++;cursor.value=null;timer=setTimeout(()=>void load(),250)})
void load();void agentApi.catalog().then(value=>{if(!disposed)catalog.value=value}).catch(()=>{})
onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(timer)})
function model(row:AgentTemplate){const ref=row.latest_revision.config.model_ref;return catalog.value?.items.find(i=>modelKey(i.reference)===modelKey(ref))?.name.split(' + ')[0]??ref?.model_id??'尚未选择模型'}
async function saved(row:AgentTemplate){editing.value=undefined;await router.push(`/agent-templates/${row.id}`)}
async function seed(){
  if(seeding.value)return;seeding.value=true;error.value=''
  try{const cap=catalog.value??await agentApi.catalog();const fire=cap.items.find(i=>i.targets.includes('fire'));if(!fire)throw Error('模拟火灾模型不可用。');demoRow??=await templatesApi.create({name:'火灾检测（模拟）',description:'模拟模板，仅演示模板与任务关联，不执行真实火灾识别。',config:{model_ref:fire.reference,default_target:'',default_rule:'',title:'',summary:'',parameters:[{key:'confidence_threshold',value:.8,required:false},{key:'alarm_interval_seconds',value:30,required:false}]}},demoKey);const result=await templatesApi.publish(demoRow,`${demoKey}-publish`);await saved(result)}catch(e){error.value=templateError(e)}finally{seeding.value=false}
}
</script>
<template>
  <div class="page-heading"><div><h1>智能体管理</h1><p>管理可复用任务模板，汇总使用模板的任务与视频源</p></div><NButton type="primary" @click="editing=null"><template #icon><Icon name="plus"/></template>新建智能体模板</NButton></div>
  <p class="notice agent-notice">每张卡片代表一个业务模板。任务通过已发布模板确定模型和配置，旧任务保留创建时的模板版本。</p>
  <div class="toolbar"><NInput v-model:value="query" clearable placeholder="搜索模板名称" aria-label="搜索智能体模板" class="search"/><NButton @click="archived=!archived">{{archived?'返回可用模板':'查看归档模板'}}</NButton><NButton :loading="loading" @click="load()">刷新</NButton><RouterLink to="/agents/legacy">历史任务入口</RouterLink><NButton v-if="environment?.data_origin==='mock'" :loading="seeding" @click="seed">创建模拟火灾模板</NButton></div>
  <ErrorBanner :error="error" @retry="load()"/><div v-if="loading" class="loading-line"/>
  <div v-if="items.length" class="agent-grid template-grid"><article v-for="row in items" :key="row.id" class="panel template-card"><div class="template-card-heading"><span class="template-icon"><Icon name="bot" :size="25"/></span><span class="status" :class="row.published_revision?'good':''">{{row.archived_at?'已归档':row.published_revision?'已发布':'模板草稿'}}</span></div><RouterLink :to="`/agent-templates/${row.id}`" class="agent-card-name">{{row.name}}</RouterLink><p class="agent-description">{{row.description||'暂无业务说明'}}</p><p class="template-model">模型：{{model(row)}}</p><div class="template-counts"><div><strong>{{row.task_count}}</strong><span>关联任务</span></div><div><strong>{{row.source_count}}</strong><span>关联视频源</span></div></div><p class="muted">{{row.published_revision?`已发布 v${row.published_revision.revision_no}`:'尚未发布'}}<span v-if="row.latest_revision.state==='draft'"> · 草稿 v{{row.latest_revision.revision_no}}</span></p><p class="muted">更新于 {{formatDate(row.updated_at)}}</p><div class="agent-actions"><RouterLink :to="`/agent-templates/${row.id}`">管理模板与任务</RouterLink><NButton size="small" :disabled="!row.published_revision||!!row.archived_at" @click="$router.push({path:'/create',query:{template:row.id}})">创建任务</NButton><NButton size="small" :disabled="!!row.archived_at" @click="editing=row">编辑模板</NButton></div></article></div>
  <section v-else-if="!loading&&!error" class="panel"><EmptyState icon="bot" title="暂无智能体模板" description="新建模板并选择分析模型及配置项，发布后即可用于任务创建。" large><NButton type="primary" @click="editing=null">新建智能体模板</NButton></EmptyState></section>
  <div v-if="cursor" class="agent-load-more"><NButton :loading="loading" @click="load(true)">加载更多模板</NButton></div>
  <TemplateEditor v-if="editing!==undefined" :row="editing??undefined" @close="editing=undefined" @saved="saved"/>
</template>

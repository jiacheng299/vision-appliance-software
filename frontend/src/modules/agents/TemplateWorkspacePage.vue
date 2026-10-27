<script setup lang="ts">
import { computed,onBeforeUnmount,ref,watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton,NSelect } from 'naive-ui'
import { templatesApi,templateError,modelKey,plainModelName,type TemplateDetail,type TemplateTask,type TemplateSource,type ParameterDefinition } from './templatesApi'
import { agentApi,type CapabilityCatalog } from './api'
import { formatDate } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import AgentStatus from './AgentStatus.vue'
import ParameterFields from './ParameterFields.vue'
import TemplateEditor from './TemplateEditor.vue'
import './agents.css'
const route=useRoute(),id=computed(()=>String(route.params.id)),row=ref<TemplateDetail|null>(null)
const tasks=ref<TemplateTask[]>([]),sources=ref<TemplateSource[]>([]),definitions=ref<ParameterDefinition[]>([]),catalog=ref<CapabilityCatalog|null>(null)
const error=ref(''),taskError=ref(''),sourceError=ref(''),loading=ref(false),editing=ref(false),busy=ref(false),cursor=ref<string|null>(null)
const tab=ref('tasks'),selectedRevision=ref('')
let generation=0,disposed=false
const revision=computed(()=>row.value?.revisions.find(r=>r.id===selectedRevision.value)??row.value?.latest_revision)
const selectedModel=computed(()=>catalog.value?.items.find(i=>modelKey(i.reference)===modelKey(revision.value?.config.model_ref)))
async function load(){const request=++generation;loading.value=true;error.value='';try{const value=await templatesApi.detail(id.value);if(request===generation&&!disposed){row.value=value;if(!value.revisions.some(r=>r.id===selectedRevision.value))selectedRevision.value=value.latest_revision.id}}catch(e){if(request===generation&&!disposed)error.value=templateError(e)}finally{if(request===generation)loading.value=false}}
async function loadTasks(more=false){const templateId=id.value;try{const page=await templatesApi.tasks(templateId,more?cursor.value??undefined:undefined);if(disposed||templateId!==id.value)return;tasks.value=more?[...tasks.value,...page.items]:page.items;cursor.value=page.next_cursor??null;taskError.value=''}catch(e){if(templateId===id.value)taskError.value=templateError(e)}}
async function loadSources(){const templateId=id.value;try{const result:TemplateSource[]=[],visited=new Set<string>();let position:string|undefined;do{const page=await templatesApi.sources(templateId,position);result.push(...page.items);position=page.next_cursor??undefined;if(position&&visited.has(position))throw Error('Pagination did not advance');if(position)visited.add(position)}while(position);if(!disposed&&templateId===id.value){sources.value=result;sourceError.value=''}}catch(e){if(templateId===id.value)sourceError.value=templateError(e)}}
watch(id,()=>{row.value=null;tasks.value=[];sources.value=[];cursor.value=null;selectedRevision.value='';void load();void loadTasks();void loadSources()},{immediate:true})
void templatesApi.parameters().then(v=>{if(!disposed)definitions.value=v.items}).catch(()=>{})
void agentApi.catalog().then(v=>{if(!disposed)catalog.value=v}).catch(()=>{})
onBeforeUnmount(()=>{disposed=true;generation++})
async function saved(value:TemplateDetail|import('./templatesApi').AgentTemplate){editing.value=false;await load();selectedRevision.value=value.latest_revision.id}
async function archive(){if(!row.value||busy.value||!window.confirm(row.value.archived_at?'确认恢复此模板？':'确认归档此模板？归档后不能创建新任务，已有任务及运行不受影响。'))return;busy.value=true;try{row.value=await templatesApi.archive(row.value,!row.value.archived_at)}catch(e){error.value=templateError(e)}finally{busy.value=false}}
</script>
<template>
  <RouterLink to="/agents">‹ 返回智能体模板列表</RouterLink>
  <div v-if="row" class="page-heading"><div><span class="agent-create-eyebrow">智能体模板</span><h1>{{row.name}}</h1><p>{{row.description||'暂无业务说明'}}</p></div><div class="agent-actions"><NButton :disabled="busy||editing" :loading="loading" @click="load();loadTasks();loadSources()">刷新</NButton><NButton :disabled="!!row.archived_at||busy" @click="editing=true">编辑模板</NButton><NButton :disabled="busy" @click="archive">{{row.archived_at?'恢复模板':'归档模板'}}</NButton><NButton type="primary" :disabled="!row.published_revision||!!row.archived_at" @click="$router.push({path:'/create',query:{template:row.id}})">使用模板创建任务</NButton></div></div>
  <ErrorBanner :error="error" @retry="load"/><div v-if="loading" class="loading-line"/>
  <template v-if="row">
    <div class="template-overview"><div class="panel"><small>关联任务</small><strong>{{row.task_count}}</strong></div><div class="panel"><small>关联视频源（含历史）</small><strong>{{row.source_count}}</strong></div><div class="panel"><small>已发布模板</small><strong>{{row.published_revision?`v${row.published_revision.revision_no}`:'尚未发布'}}</strong></div></div>
    <p class="notice">每个任务固定使用创建时的模板版本。发布新版本不会修改已有任务、运行记录或报警证据。</p>
    <div class="agent-actions template-tabs"><NButton :type="tab==='tasks'?'primary':'default'" @click="tab='tasks'">关联任务</NButton><NButton :type="tab==='sources'?'primary':'default'" @click="tab='sources'">关联视频源</NButton><NButton :type="tab==='config'?'primary':'default'" @click="tab='config'">模板配置与版本</NButton></div>
    <section v-if="tab==='tasks'" class="panel"><ErrorBanner :error="taskError" @retry="loadTasks()"/><EmptyState v-if="!tasks.length&&!taskError" title="暂无关联任务" description="使用该模板创建的任务将在此汇总。"/><article v-for="task in tasks" :key="task.agent.id" class="template-task-row"><div class="panel-title"><RouterLink :to="`/agents/${task.agent.id}/live`" class="agent-card-name">{{task.agent.name}}</RouterLink><AgentStatus :value="task.agent.status"/></div><p>模板版本 v{{task.template_revision_no}} · {{task.sources.map(s=>s.name).join('、')||'尚未绑定视频源'}}</p><p class="muted">创建于 {{formatDate(task.agent.created_at)}}<span v-if="task.agent.archived_at"> · 任务已归档</span></p><div class="agent-actions"><RouterLink :to="`/agents/${task.agent.id}/live`">查看画面与报警</RouterLink><RouterLink :to="`/agents/${task.agent.id}/config`">查看任务配置</RouterLink><RouterLink :to="`/agents/${task.agent.id}/history`">查看运行历史</RouterLink></div></article><NButton v-if="cursor" @click="loadTasks(true)">加载更多任务</NButton></section>
    <section v-else-if="tab==='sources'" class="panel"><ErrorBanner :error="sourceError" @retry="loadSources"/><EmptyState v-if="!sources.length&&!sourceError" title="暂无关联视频源" description="汇总所有关联任务使用过的视频源，同一视频源仅显示一次。"/><article v-for="source in sources" :key="source.id" class="template-source-row"><div><strong>{{source.name}}</strong><p class="muted">{{source.kind==='camera'?'监控直播':source.kind==='file'?'录像文件':'历史视频源'}} · {{source.status==='archived'?'已归档':source.status==='unavailable'?'当前不可用':source.status==='ready'?'就绪':source.status==='online'?'在线':source.status==='unverified'?'待验证':source.status}}</p></div><RouterLink v-if="!['archived','unavailable'].includes(source.status)" :to="`/sources/${source.id}`">查看视频源</RouterLink></article></section>
    <section v-else-if="revision" class="panel"><div class="panel-title"><h2>模板配置</h2><NSelect v-model:value="selectedRevision" :options="row.revisions.map(r=>({label:`v${r.revision_no} · ${r.state==='published'?'已发布':'草稿'}`,value:r.id}))" aria-label="模板版本" style="width:210px"/></div><p>模型：{{selectedModel?plainModelName(selectedModel.name):revision.config.model_ref?.model_id??'尚未选择'}} <span v-if="revision.config.model_ref">· {{revision.config.model_ref.model_version}}</span></p><p class="muted">发布于 {{formatDate(revision.published_at)}} · 该版本关联 {{tasks.filter(t=>t.template_revision_id===revision?.id).length}} 个已加载任务</p><ParameterFields :settings="revision.config.parameters??[]" :definitions="definitions" :model="selectedModel" disabled/></section>
  </template>
  <TemplateEditor v-if="editing&&row" :row="row" @close="editing=false" @saved="saved"/>
</template>

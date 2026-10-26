<script setup lang="ts">
import { MANUAL_REVIEW_AVAILABLE } from './features'
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, NSelect } from 'naive-ui'
import { humanError } from '../../shared/api/client'
import { formatDate } from '../../shared/ui/resource'
import { safeMediaUrl } from '../../shared/media/url'
import type { Source } from '../../shared/api/types'
import EmptyState from '../../shared/ui/EmptyState.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import Icon from '../../shared/ui/Icon.vue'
import { agentApi, listAgentSources, type Agent, type AgentDetail } from './api'
import { sourceCount } from './channelSources'
import { environment } from '../../shared/environment'
import { agentError, label } from './state'
import AgentStatus from './AgentStatus.vue'
import CreateAgentDrawer from './CreateAgentDrawer.vue'
import './agents.css'
const router = useRouter()
const items = ref<Agent[]>([]), sources = ref<Source[]>([]), query = ref(''), sourceId = ref<string | null>(null)
const error = ref(''), sourcesError = ref(''), loading = ref(false), cursor = ref<string | null>(null), showCreate = ref(false)
const canWrite = true
const stateFilter=ref<string|null>(null),scene=ref(''),archived=ref(false),sort=ref('updated_desc'),seeding=ref(false)
let generation = 0, timer: ReturnType<typeof setTimeout> | undefined
async function load(more = false) {
  const request = ++generation; loading.value = true; error.value = ''
  try {
    const data = await agentApi.list(query.value, sourceId.value ?? '', more ? cursor.value ?? undefined : undefined,{status:stateFilter.value??undefined,scene:scene.value.trim()||undefined,archived:archived.value,sort:sort.value})
    if (request !== generation) return
    items.value = more ? [...items.value, ...data.items.filter(item => !items.value.some(old => old.id === item.id))] : data.items
    cursor.value = data.next_cursor ?? null
  } catch (e) { if (request === generation) error.value = humanError(e) }
  finally { if (request === generation) loading.value = false }
}
async function loadSources() { try { sources.value = await listAgentSources(); sourcesError.value = '' } catch (e) { sourcesError.value = humanError(e) } }
watch([query, sourceId,stateFilter,scene,archived,sort], () => { generation++; items.value = []; cursor.value = null; clearTimeout(timer); timer = setTimeout(() => void load(), 250) })
onUnmounted(() => { generation++; clearTimeout(timer) })
void load(); void loadSources()
function openCreate() { showCreate.value = true; void loadSources() }
function created(agent:AgentDetail){showCreate.value=false;void router.push(`/agents/${agent.id}/config`)}
function thumbnail(agent: Agent) { return safeMediaUrl(sources.value.find(s => s.id === (agent.latest_revision.config.channels?.[0]?.sources?.[0]?.source_id??agent.latest_revision.config.channels?.[0]?.source_id))?.thumbnail_url ?? null) }
async function seed(){if(seeding.value)return;seeding.value=true;error.value='';try{const result=await agentApi.seed();await loadSources();await router.push(`/agents/${result.id}/config`)}catch(e){error.value=agentError(e)}finally{seeding.value=false}}
</script>
<template>
  <div class="page-heading"><div><h1>智能体管理</h1><p>管理监测配置、视频来源与版本记录</p></div><NButton v-if="canWrite" type="primary" @click="openCreate"><template #icon><Icon name="plus"/></template>新建草稿</NButton></div>
  <p class="notice agent-notice">{{environment?.data_origin==='mock'?'独立演示模式：可练习完整流程。模拟运行和事件不代表真实识别效果。':'运行状态和报警来自公共服务。服务未接入时可继续管理草稿和查看已有配置。'}}</p>
  <div class="toolbar"><NInput v-model:value="query" class="search" clearable placeholder="搜索智能体名称或说明" aria-label="搜索智能体"/><NSelect v-model:value="sourceId" :options="sources.map(s => ({label:s.name,value:s.id}))" clearable placeholder="全部视频源" aria-label="筛选视频源" style="width:210px"/><NSelect v-model:value="stateFilter" :options="['draft','ready','queued','running','stopping','stopped','failed','unknown'].map(value=>({label:label(value),value}))" clearable placeholder="全部状态" aria-label="筛选智能体状态"/><NInput v-model:value="scene" placeholder="场景规则名称" aria-label="筛选场景规则" style="width:160px"/><NSelect v-model:value="sort" :options="[{label:'最近更新',value:'updated_desc'},{label:'名称排序',value:'name_asc'}]" aria-label="智能体排序"/><NButton @click="archived=!archived">{{archived?'返回未归档':'查看归档'}}</NButton><NButton :loading="loading" @click="load()">刷新</NButton></div>
  <div v-if="environment?.data_origin==='mock'&&canWrite" class="agent-actions agent-notice"><NButton :loading="seeding" @click="seed">加载双路模拟样例</NButton><span class="muted">样例包含两路配置和监测区域，无需模型或摄像头。</span></div><ErrorBanner :error="error" @retry="load()"/><ErrorBanner :error="sourcesError" @retry="loadSources"/>
  <div v-if="loading" class="loading-line" aria-label="正在加载智能体"/>
  <div v-if="items.length" class="agent-grid">
    <article v-for="agent in items" :key="agent.id" class="panel agent-card">
      <RouterLink :to="`/agents/${agent.id}/live`" class="agent-card-preview" :aria-label="`查看${agent.name}`"><img v-if="thumbnail(agent)" :src="thumbnail(agent)!" :alt="`${agent.name} 的视频源缩略图`"/><Icon v-else name="video" :size="32"/><AgentStatus :value="agent.status"/></RouterLink>
      <div class="agent-card-body"><RouterLink :to="`/agents/${agent.id}/live`" class="agent-card-name">{{agent.name}}</RouterLink><p class="agent-description">{{agent.description || '暂无说明'}}</p><div class="agent-card-meta"><span>{{agent.latest_revision.config.channels?.length ?? 0}} 个通道 · {{sourceCount(agent.latest_revision.config)}} 路视频</span><span>最新配置 v{{agent.latest_revision.revision_no}}</span></div><p class="muted">活动配置：{{agent.active_revision_nos?.length?agent.active_revision_nos.map(n=>`v${n}`).join('、'):'无 / 状态待确认'}}</p><p v-if="agent.failed_run_count" class="status bad">异常 {{agent.failed_run_count}} 路</p><p v-if="MANUAL_REVIEW_AVAILABLE" class="muted">待核查 {{agent.pending_review_count==null?'未知':agent.pending_review_count}}</p><p v-else class="muted">人工核查 · 当前版本暂未开放</p><p class="muted">今日事件 {{agent.today_event_count==null?'未知':agent.today_event_count}} · 最近报警 {{formatDate(agent.latest_event_at??null)}}</p><p class="muted">更新于 {{formatDate(agent.updated_at)}}</p><div class="agent-actions"><RouterLink :to="`/agents/${agent.id}/live`">查看详情</RouterLink><RouterLink v-if="canWrite&&!agent.archived_at" :to="`/agents/${agent.id}/config`">编辑配置</RouterLink></div></div>
    </article>
  </div>
  <section v-else-if="!loading && !error" class="panel"><EmptyState large icon="bot" :title="query || sourceId ? '没有符合条件的智能体' : '先保存你的第一个监测草稿'" description="草稿保存后会形成一张卡片，可以继续配置视频源和监测需求。"><NButton v-if="canWrite && !query && !sourceId" type="primary" @click="openCreate">新建草稿</NButton></EmptyState></section>
  <div v-if="cursor" class="agent-load-more"><NButton :loading="loading" @click="load(true)">加载更多</NButton></div>
  <CreateAgentDrawer v-if="showCreate" :sources="sources" :sources-error="sourcesError" @close="showCreate=false" @created="created"/>
</template>

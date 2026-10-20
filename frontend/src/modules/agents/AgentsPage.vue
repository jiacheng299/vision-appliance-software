<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, NModal, NSelect } from 'naive-ui'
import { humanError } from '../../shared/api/client'
import { useSession } from '../../shared/auth/store'
import { formatDate } from '../../shared/ui/resource'
import { safeMediaUrl } from '../../shared/media/url'
import type { Source } from '../../shared/api/types'
import EmptyState from '../../shared/ui/EmptyState.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import Icon from '../../shared/ui/Icon.vue'
import { agentApi, listAgentSources, type Agent } from './api'
import { emptyConfig } from './draft'
import './agents.css'
const router = useRouter(), session = useSession()
const items = ref<Agent[]>([]), sources = ref<Source[]>([]), query = ref(''), sourceId = ref<string | null>(null)
const error = ref(''), sourcesError = ref(''), loading = ref(false), cursor = ref<string | null>(null), showCreate = ref(false)
const name = ref(''), description = ref(''), creating = ref(false), createError = ref('')
const canWrite = computed(() => session.user?.role !== 'viewer')
let generation = 0, timer: ReturnType<typeof setTimeout> | undefined, createToken = '', createBody = ''
async function load(more = false) {
  const request = ++generation; loading.value = true; error.value = ''
  try {
    const data = await agentApi.list(query.value, sourceId.value ?? '', more ? cursor.value ?? undefined : undefined)
    if (request !== generation) return
    items.value = more ? [...items.value, ...data.items.filter(item => !items.value.some(old => old.id === item.id))] : data.items
    cursor.value = data.next_cursor ?? null
  } catch (e) { if (request === generation) error.value = humanError(e) }
  finally { if (request === generation) loading.value = false }
}
async function loadSources() { try { sources.value = await listAgentSources(); sourcesError.value = '' } catch (e) { sourcesError.value = humanError(e) } }
watch([query, sourceId], () => { generation++; items.value = []; cursor.value = null; clearTimeout(timer); timer = setTimeout(() => void load(), 250) })
onUnmounted(() => { generation++; clearTimeout(timer) })
void load(); void loadSources()
function openCreate() { name.value = ''; description.value = ''; createError.value = ''; createToken = ''; createBody = ''; showCreate.value = true }
async function create() {
  if (creating.value) return
  if (!name.value.trim()) { createError.value = '请先给智能体起一个名称。'; return }
  const body = { name: name.value.trim(), description: description.value.trim(), config: emptyConfig() }
  const encoded = JSON.stringify(body)
  if (!createToken || createBody !== encoded) { createToken = crypto.randomUUID(); createBody = encoded }
  creating.value = true; createError.value = ''
  try { const result = await agentApi.create(body, createToken); showCreate.value = false; await router.push(`/agents/${result.id}/config`) }
  catch (e) { createError.value = humanError(e) }
  finally { creating.value = false }
}
function thumbnail(agent: Agent) { return safeMediaUrl(sources.value.find(s => s.id === agent.latest_revision.config.channels?.[0]?.source_id)?.thumbnail_url ?? null) }
</script>
<template>
  <div class="page-heading"><div><h1>智能体管理</h1><p>管理监测配置、视频来源与版本记录</p></div><NButton v-if="canWrite" type="primary" @click="openCreate"><template #icon><Icon name="plus"/></template>新建草稿</NButton></div>
  <p class="notice agent-notice">当前支持保存和编辑真实草稿。模型评估与监测运行尚未接入，草稿不会产生实时报警。</p>
  <div class="toolbar"><NInput v-model:value="query" class="search" clearable placeholder="搜索智能体名称或说明" aria-label="搜索智能体"/><NSelect v-model:value="sourceId" :options="sources.map(s => ({label:s.name,value:s.id}))" clearable placeholder="全部视频源" aria-label="筛选视频源" style="width:210px"/><span class="status">草稿</span><NButton :loading="loading" @click="load()">刷新</NButton></div>
  <ErrorBanner :error="error" @retry="load()"/><ErrorBanner :error="sourcesError" @retry="loadSources"/>
  <div v-if="loading" class="loading-line" aria-label="正在加载智能体"/>
  <div v-if="items.length" class="agent-grid">
    <article v-for="agent in items" :key="agent.id" class="panel agent-card">
      <RouterLink :to="`/agents/${agent.id}/live`" class="agent-card-preview" :aria-label="`查看${agent.name}`"><img v-if="thumbnail(agent)" :src="thumbnail(agent)!" :alt="`${agent.name} 的视频源缩略图`"/><Icon v-else name="video" :size="32"/><span class="status">草稿 · 未启动</span></RouterLink>
      <div class="agent-card-body"><RouterLink :to="`/agents/${agent.id}/live`" class="agent-card-name">{{agent.name}}</RouterLink><p class="agent-description">{{agent.description || '暂无说明'}}</p><div class="agent-card-meta"><span>{{agent.latest_revision.config.channels?.length ?? 0}} 路配置</span><span>最新草稿 v{{agent.latest_revision.revision_no}}</span></div><p class="muted">更新于 {{formatDate(agent.updated_at)}}</p><div class="agent-actions"><RouterLink :to="`/agents/${agent.id}/live`">查看详情</RouterLink><RouterLink v-if="canWrite" :to="`/agents/${agent.id}/config`">编辑配置</RouterLink></div></div>
    </article>
  </div>
  <section v-else-if="!loading && !error" class="panel"><EmptyState large icon="bot" :title="query || sourceId ? '没有符合条件的智能体' : '先保存你的第一个监测草稿'" description="草稿保存后会形成一张卡片，可以继续配置视频源和监测需求。"><NButton v-if="canWrite && !query && !sourceId" type="primary" @click="openCreate">新建草稿</NButton></EmptyState></section>
  <div v-if="cursor" class="agent-load-more"><NButton :loading="loading" @click="load(true)">加载更多</NButton></div>
  <NModal v-model:show="showCreate" preset="card" title="新建智能体草稿" class="agent-create-modal" :mask-closable="false" :closable="!creating" :close-on-esc="!creating">
    <form @submit.prevent="create"><div class="field"><label for="agent-name">智能体名称</label><NInput :input-props="{id:'agent-name'}" v-model:value="name" :maxlength="160" :disabled="creating" placeholder="例如：北门人员滞留监测"/></div><div class="field"><label for="agent-description">用途说明（可选）</label><NInput :input-props="{id:'agent-description'}" v-model:value="description" type="textarea" :maxlength="2000" :disabled="creating"/></div><ErrorBanner :error="createError" :retryable="false"/><p class="muted">创建后继续添加视频源、监测需求和区域，不会直接启动任务。</p><div class="agent-actions"><NButton :disabled="creating" @click="showCreate=false">取消</NButton><NButton type="primary" attr-type="submit" :loading="creating">创建草稿</NButton></div></form>
  </NModal>
</template>

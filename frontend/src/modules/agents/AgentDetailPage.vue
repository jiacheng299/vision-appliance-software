<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { NButton, NInput, NModal, NSelect } from 'naive-ui'
import { humanError } from '../../shared/api/client'
import { useSession } from '../../shared/auth/store'
import { formatDate } from '../../shared/ui/resource'
import type { Source } from '../../shared/api/types'
import MediaPlayer from '../../shared/media/MediaPlayer.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import { agentApi, listAgentSources, type AgentDetail, type Revision } from './api'
import RevisionEditor from './RevisionEditor.vue'
import './agents.css'
const route = useRoute(), session = useSession()
const agent = ref<AgentDetail | null>(null), sources = ref<Source[]>([]), error = ref(''), sourceError = ref(''), notice = ref(''), loading = ref(false), busy = ref(false), saving = ref(false)
const selectedRevisionId = ref(''), selectedChannelId = ref(''), editing = ref<Revision | null>(null), dirty = ref(false)
const renameOpen = ref(false), name = ref(''), description = ref(''), renameError = ref('')
const selected = computed(() => agent.value?.revisions.find(r => r.id === selectedRevisionId.value) ?? agent.value?.latest_revision)
const channel = computed(() => selected.value?.config.channels?.find(c => c.channel_id === selectedChannelId.value) ?? selected.value?.config.channels?.[0])
const source = computed(() => sources.value.find(s => s.id === channel.value?.source_id))
const tab = computed(() => String(route.params.tab || 'live'))
const canWrite = computed(() => session.user?.role !== 'viewer')
let generation = 0, cloneToken = '', cloneBody = ''
async function load() {
  const request = ++generation, id = String(route.params.id); loading.value = true; error.value = ''
  try {
    const result = await agentApi.detail(id)
    if (request !== generation) return
    agent.value = result
    if (!result.revisions.some(r => r.id === selectedRevisionId.value)) selectedRevisionId.value = result.latest_revision.id
  } catch (e) { if (request === generation) error.value = humanError(e) }
  finally { if (request === generation) loading.value = false }
}
async function loadSources() { try { sources.value = await listAgentSources(); sourceError.value = '' } catch (e) { sourceError.value = humanError(e) } }
watch(() => route.params.id, () => { agent.value = null; selectedRevisionId.value = ''; editing.value = null; dirty.value = false; notice.value = ''; void load() }, { immediate: true })
watch(selectedRevisionId, () => { selectedChannelId.value = '' })
void loadSources()
onUnmounted(() => generation++)
function mayLeave() { return !busy.value && !saving.value && (!editing.value || !dirty.value || window.confirm('尚有未保存的配置，确定离开并放弃修改？')) }
onBeforeRouteLeave(to => to.path === '/login' || mayLeave())
onBeforeRouteUpdate(() => { if (!mayLeave()) return false; editing.value = null; dirty.value = false })
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload))
async function clone() {
  if (!agent.value || !selected.value || busy.value) return
  const id = agent.value.id, body = `${id}:${selected.value.id}:${agent.value.row_version}`
  if (!cloneToken || cloneBody !== body) { cloneToken = crypto.randomUUID(); cloneBody = body }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await agentApi.clone(id, selected.value.id, agent.value.row_version, cloneToken)
    if (route.params.id !== id) return
    await load(); selectedRevisionId.value = result.id; notice.value = `已复制为草稿 v${result.revision_no}，原版本保持不变。`
  } catch (e) { if (route.params.id === id) error.value = humanError(e) }
  finally { busy.value = false }
}
function edit() { if (selected.value?.state === 'draft') { editing.value = selected.value; notice.value = '' } }
async function saved(revision: Revision) { editing.value = null; dirty.value = false; await load(); selectedRevisionId.value = revision.id; notice.value = '草稿已保存。未启动监测，也未改变任何运行。' }
function openRename() { if (agent.value) { name.value = agent.value.name; description.value = agent.value.description; renameError.value = ''; renameOpen.value = true } }
async function rename() {
  if (!agent.value || busy.value) return
  if (!name.value.trim()) { renameError.value = '名称不能为空。'; return }
  busy.value = true
  try { agent.value = await agentApi.rename(agent.value.id, { name: name.value.trim(), description: description.value.trim(), row_version: agent.value.row_version }); renameOpen.value = false }
  catch (e) { renameError.value = humanError(e) }
  finally { busy.value = false }
}
</script>
<template>
  <div class="page-heading"><div><RouterLink to="/agents">‹ 返回智能体列表</RouterLink><h1>{{agent?.name || '智能体详情'}}</h1><p>{{agent?.description || '查看监测配置与历史版本'}}</p></div><div class="agent-actions"><NButton :disabled="!!editing" :loading="loading" @click="load">刷新</NButton><NButton v-if="canWrite && agent" :disabled="busy || !!editing" @click="openRename">修改名称</NButton></div></div>
  <ErrorBanner :error="error" @retry="load"/><ErrorBanner :error="sourceError" @retry="loadSources"/>
  <p v-if="notice" class="notice agent-notice" role="status">{{notice}}</p>
  <div v-if="loading" class="loading-line"/>
  <template v-if="agent && selected">
    <div class="agent-summary"><span class="status">草稿 · 未启动</span><span>查看版本 v{{selected.revision_no}}</span><span>{{selected.config.channels?.length ?? 0}} 路配置</span><span class="muted">最后保存 {{formatDate(selected.updated_at)}}</span><NSelect v-model:value="selectedRevisionId" :options="agent.revisions.map(r => ({label:`v${r.revision_no} · ${r.state === 'draft' ? '草稿' : '已发布'}`,value:r.id}))" aria-label="选择配置版本" style="width:190px"/></div>
    <nav class="agent-tabs" aria-label="智能体详情导航"><RouterLink v-for="item in [{key:'live',label:'画面与报警'},{key:'config',label:'监测配置'},{key:'history',label:'版本与运行历史'},{key:'events',label:'事件核查'}]" :key="item.key" :to="`/agents/${agent.id}/${item.key}`">{{item.label}}</RouterLink></nav>
    <p class="notice agent-notice">{{agent.limitation}}</p>
    <template v-if="tab === 'live'">
      <div v-if="selected.config.channels?.length" class="agent-actions agent-notice"><NSelect v-model:value="selectedChannelId" :options="selected.config.channels.map(c => ({label:c.name,value:c.channel_id}))" :placeholder="channel?.name" aria-label="选择监测通道" style="width:260px"/></div>
      <div class="agent-live-grid"><section class="panel"><div class="panel-title"><h2>{{channel?.name || '视频画面'}}</h2><span class="status">非监测画面</span></div><MediaPlayer v-if="source" :source="source"/><EmptyState v-else icon="video" title="暂无可预览的视频源" description="请在监测配置中选择视频源；已归档的视频源不会提供预览。"/><p class="muted agent-preview-hint">此处仅预览视频源。尚未运行分析，不含检测框或实时报警；播放录像不会启动监测。</p></section><section class="panel"><h2>报警信息</h2><EmptyState icon="bell" title="尚未启动监测" description="运行与事件服务接入后显示报警。当前没有实时报警订阅。"/></section></div>
    </template>
    <section v-else-if="tab === 'config'" class="panel">
      <div class="panel-title"><h2>监测配置 · v{{selected.revision_no}}</h2><div v-if="canWrite" class="agent-actions"><NButton :loading="busy" @click="clone">复制为新版本</NButton><NButton v-if="selected.state === 'draft'" type="primary" @click="edit">编辑草稿</NButton></div></div>
      <EmptyState v-if="!selected.config.channels?.length" title="还没有监测通道" description="点击“编辑草稿”，添加视频源和监测需求。"/>
      <article v-for="c in selected.config.channels" :key="c.channel_id" class="agent-config-row"><h3>{{c.name}}</h3><dl class="detail-meta"><div><dt>视频源</dt><dd>{{sources.find(s => s.id === c.source_id)?.name || (c.source_id ? '原视频源不可用' : '尚未选择')}}</dd></div><div><dt>持续时长</dt><dd>{{c.duration_seconds == null ? '尚未设置' : `${c.duration_seconds} 秒`}}</dd></div><div><dt>监测对象／规则</dt><dd>{{c.target || '待补充'}} ／ {{c.rule || '待补充'}}</dd></div><div><dt>监测区域</dt><dd>{{c.regions?.length ?? 0}} 个</dd></div><div class="wide"><dt>原始需求</dt><dd>{{c.requirement_text || '尚未填写'}}</dd></div><div class="wide"><dt>模型能力</dt><dd>{{c.capability_ref ? `${c.capability_ref.model_id} · ${c.capability_ref.model_version}（待校验）` : '尚未绑定，模型服务未接入'}}</dd></div><div v-if="c.start_media_ms != null" class="wide"><dt>录像分析区间</dt><dd>{{c.start_media_ms/1000}} 秒至 {{(c.end_media_ms ?? 0)/1000}} 秒</dd></div></dl></article>
      <div class="agent-actions"><NButton disabled>验证配置</NButton><NButton disabled>启动监测</NButton></div><p class="muted">模型评估和运行服务尚未接入，因此暂不能验证或启动。</p>
    </section>
    <section v-else-if="tab === 'history'" class="panel"><div class="panel-title"><h2>配置版本</h2><NButton v-if="canWrite" :loading="busy" @click="clone">复制所选版本</NButton></div><div class="table-wrap"><table><thead><tr><th>版本</th><th>状态</th><th>来源版本</th><th>更新时间</th><th>操作</th></tr></thead><tbody><tr v-for="r in agent.revisions" :key="r.id"><td>v{{r.revision_no}}</td><td>{{r.state === 'draft' ? '草稿' : '已发布（只读）'}}</td><td>{{agent.revisions.find(base => base.id === r.base_revision_id)?.revision_no ? `v${agent.revisions.find(base => base.id === r.base_revision_id)?.revision_no}` : '初始版本'}}</td><td>{{formatDate(r.updated_at)}}</td><td><NButton size="small" @click="selectedRevisionId = r.id">{{selected.id === r.id ? '正在查看' : '查看此版本'}}</NButton></td></tr></tbody></table></div><h2 class="agent-section-title">运行记录</h2><EmptyState title="暂无运行记录" description="运行服务未接入。复制版本或保存草稿都不会创建一次运行。"/></section>
    <section v-else class="panel"><h2>事件与人工核查</h2><EmptyState icon="bell" title="事件服务尚未接入" description="后续可查看证据、标记正确或误报，并在录像中补录漏报。当前不生成模拟事件或反馈。"/></section>
  </template>
  <RevisionEditor v-if="editing" :revision="editing" :sources="sources" @close="editing=null;dirty=false" @dirty="dirty=$event" @saving="saving=$event" @saved="saved"/>
  <NModal v-model:show="renameOpen" preset="card" title="修改名称与说明" class="agent-create-modal" :mask-closable="false" :closable="!busy" :close-on-esc="!busy"><form @submit.prevent="rename"><div class="field"><label for="rename-agent">名称</label><NInput :input-props="{id:'rename-agent'}" v-model:value="name" :maxlength="160" :disabled="busy"/></div><div class="field"><label for="rename-description">说明</label><NInput :input-props="{id:'rename-description'}" v-model:value="description" type="textarea" :maxlength="2000" :disabled="busy"/></div><ErrorBanner :error="renameError" :retryable="false"/><NButton type="primary" attr-type="submit" :loading="busy">保存</NButton></form></NModal>
</template>

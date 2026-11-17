<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton } from 'naive-ui'
import { agentApi, type RouteEvaluation, type RouteState } from './api'
import { useResource } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'

const props = defineProps<{ sourceId: string; rule: string; durationSeconds?: number | null
  agentId?: string; channelId?: string }>()

const { data, loading, error, refresh } = useResource(() => agentApi.routes(props.sourceId, {
  rule: props.rule, duration_seconds: props.durationSeconds ?? undefined,
}))
const states = useResource(() => props.agentId
  ? agentApi.routeStates(props.agentId) : Promise.resolve([] as RouteState[]))
const acting = ref('')
const actionError = ref('')

const routeState = computed<RouteState | null>(() => {
  const rows = states.data.value ?? []
  const match = rows.find(row => row.source_id === props.sourceId
    && (!props.channelId || row.channel_id === props.channelId))
  return match ?? null
})
const bucketLabel = computed(() => data.value?.scenario.bucket === 'default'
  ? '常规场景' : `场景分桶 ${data.value?.scenario.bucket ?? ''}`)

function number(value: number | null | undefined, digits = 3) {
  return value == null ? '—' : value.toFixed(digits)
}
function members(row: RouteEvaluation) { return row.members.join(' + ') }
function memberText(list: string[] | null | undefined) { return list?.length ? list.join(' + ') : '—' }

async function propose() {
  if (!props.agentId || !props.channelId || acting.value) return
  acting.value = 'propose'; actionError.value = ''
  try {
    await agentApi.proposeRoute(props.agentId, { channel_id: props.channelId,
      source_id: props.sourceId, rule: props.rule,
      duration_seconds: props.durationSeconds ?? undefined })
    await Promise.all([states.refresh(), refresh()])
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '路由提议失败'
  } finally { acting.value = '' }
}
async function cancel() {
  if (!props.agentId || !props.channelId || acting.value) return
  acting.value = 'cancel'; actionError.value = ''
  try {
    await agentApi.cancelRoute(props.agentId, { channel_id: props.channelId,
      source_id: props.sourceId })
    await states.refresh()
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '取消失败'
  } finally { acting.value = '' }
}
</script>

<template>
  <section class="panel route-panel" aria-label="路由候选">
    <div class="panel-title"><h2>路由候选</h2><small>{{ bucketLabel }}</small></div>
    <p class="muted">按需求覆盖、依赖完整性、冲突、资源和切换代价评估模型执行组合。人工提议只登记候选，切换需要候选取得足够多的有效观察窗口。</p>
    <div class="toolbar route-toolbar">
      <NButton size="small" :loading="loading" @click="refresh">刷新路由评估</NButton>
      <NButton v-if="agentId && channelId" size="small" type="primary" :loading="acting==='propose'"
        :disabled="!!acting" @click="propose">评估并提议</NButton>
      <NButton v-if="routeState?.mode==='candidate'" size="small" :loading="acting==='cancel'"
        :disabled="!!acting" @click="cancel">取消候选</NButton>
    </div>
    <ErrorBanner :error="actionError" :retryable="false"/>
    <ErrorBanner :error="error" @retry="refresh"/>
    <section v-if="routeState" class="route-state" aria-label="路由状态">
      <div class="route-state-line">
        <strong>当前路由 {{ routeState.active_version }}</strong>
        <span>{{ memberText(routeState.active_members) }}</span>
        <span class="route-mode">{{ routeState.mode === 'candidate' ? '候选验证中' : '稳定' }}</span>
      </div>
      <div v-if="routeState.candidate_members" class="route-state-line">
        <span>候选：{{ memberText(routeState.candidate_members) }}</span>
        <span>评分 {{ number(routeState.candidate_score) }}</span>
        <span>有效窗口 {{ routeState.valid_windows }}</span>
        <span>增益 {{ number(routeState.delta_j) }}</span>
      </div>
      <ul v-if="routeState.drift?.length" class="route-drift" aria-label="属性漂移">
        <li v-for="item in routeState.drift ?? []" :key="item.attribute">
          {{ item.attribute }}：{{ item.previous ?? '未知' }} → {{ item.current ?? '未知' }}（{{ item.reason }}）
        </li>
      </ul>
      <p v-if="routeState.affected?.length" class="muted">
        受影响子图：{{ (routeState.affected ?? []).join('、') }}；保留：{{ (routeState.fixed ?? []).join('、') || '无' }}<span
          v-if="routeState.escalated">；已退化为全图重算（{{ routeState.escalation_reason }}）</span>
      </p>
      <ul v-if="routeState.notices?.length" class="route-notices"><li v-for="notice in routeState.notices ?? []" :key="notice">{{ notice }}</li></ul>
    </section>
    <p v-if="loading && !data" class="muted" role="status">正在评估路由候选…</p>
    <template v-else-if="data">
      <ul v-if="data.notices.length" class="route-notices" aria-label="路由评估口径说明">
        <li v-for="notice in data.notices" :key="notice">{{ notice }}</li>
      </ul>
      <div class="route-chosen" :class="data.chosen ? 'ok' : 'blocked'">
        <template v-if="data.chosen">
          <strong>评估首选：{{ data.chosen.label }}</strong>
          <span>综合评分 {{ number(data.chosen.score) }}</span>
          <small>覆盖 {{ number(data.chosen.coverage) }} · 依赖 {{ number(data.chosen.dependency) }} ·
            冲突 {{ number(data.chosen.conflict) }} · 资源 {{ number(data.chosen.cost) }} ·
            切换 {{ number(data.chosen.switch) }}</small>
        </template>
        <template v-else>
          <strong>没有可行组合</strong>
          <span>所有候选都被硬约束排除，需要补充能力或不满足观察条件。</span>
        </template>
      </div>
      <h3>可行候选</h3>
      <p v-if="!data.ranked.length" class="muted" role="status">暂无可行候选</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>组合</th><th>评分</th><th>覆盖</th><th>依赖</th><th>资源</th><th>切换</th></tr></thead>
          <tbody><tr v-for="row in data.ranked" :key="row.combination_id">
            <td class="wrap">{{ row.label }}<small class="route-members">{{ members(row) }}</small></td>
            <td>{{ number(row.score) }}</td><td>{{ number(row.coverage) }}</td>
            <td>{{ number(row.dependency) }}</td><td>{{ number(row.cost) }}</td><td>{{ number(row.switch) }}</td>
          </tr></tbody>
        </table>
      </div>
      <h3>被排除的候选</h3>
      <p v-if="!data.blocked.length" class="muted" role="status">没有候选被排除</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>组合</th><th>排除原因</th></tr></thead>
          <tbody><tr v-for="row in data.blocked" :key="row.combination_id">
            <td class="wrap">{{ row.label }}</td>
            <td class="wrap">{{ row.reasons.join('；') }}</td>
          </tr></tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.route-panel { margin-bottom: 16px; }
.route-toolbar { margin: 12px 0; display: flex; gap: 8px; flex-wrap: wrap; }
.route-notices { margin: 0 0 12px; padding-left: 18px; font-size: 12px; opacity: .85; }
.route-chosen { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 8px; border: 1px solid rgba(128,128,128,.35); margin-bottom: 12px; }
.route-chosen.ok { border-color: rgba(24,160,88,.6); }
.route-chosen.blocked { border-color: rgba(208,48,80,.6); }
.route-members { display: block; opacity: .7; font-size: 11px; }
.route-state { border: 1px solid rgba(128,128,128,.35); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.route-state-line { display: flex; gap: 12px; flex-wrap: wrap; align-items: baseline; font-size: 13px; }
.route-mode { font-size: 12px; opacity: .8; }
.route-drift { margin: 0; padding-left: 18px; font-size: 12px; opacity: .9; }
h3 { margin: 12px 0 6px; font-size: 13px; }
</style>

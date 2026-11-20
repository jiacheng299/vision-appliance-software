<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton } from 'naive-ui'
import { agentApi, type RouteEvaluation, type RouteState, type TimelineEntry } from './api'
import { useResource } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import RouteTimeline from './RouteTimeline.vue'

const props = defineProps<{ sourceId: string; rule: string; durationSeconds?: number | null
  agentId?: string; channelId?: string; sourceLabel?: string }>()

const { data, loading, error, refresh } = useResource(() => agentApi.routes(props.sourceId, {
  rule: props.rule, duration_seconds: props.durationSeconds ?? undefined,
}))
const states = useResource(() => props.agentId
  ? agentApi.routeStates(props.agentId) : Promise.resolve([] as RouteState[]))
const timeline = useResource(() => props.agentId && props.channelId
  ? agentApi.routeTimeline(props.agentId, { channel_id: props.channelId,
      source_id: props.sourceId, limit: 12 }) : Promise.resolve([] as TimelineEntry[]))
const policies = useResource(() => agentApi.trackerPolicies())
const acting = ref('')
const actionError = ref('')

const routeState = computed<RouteState | null>(() => {
  const rows = states.data.value ?? []
  const match = rows.find(row => row.source_id === props.sourceId
    && (!props.channelId || row.channel_id === props.channelId))
  return match ?? null
})
const bucketLabel = computed(() => data.value?.scenario.bucket === 'default'
  ? '常规场景' : `场景类型 ${data.value?.scenario.bucket ?? ''}`)

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
    await Promise.all([states.refresh(), refresh(), timeline.refresh()])
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '模型组合评估失败'
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
  <section class="panel route-panel" aria-label="模型组合">
    <div class="panel-title"><h2>模型组合</h2><small>{{ sourceLabel ? sourceLabel + ' · ' : '' }}{{ bucketLabel }}</small></div>
    <p class="muted">根据当前画面与观察条件比较模型组合。人工提议只登记候选，取得足够多的有效观察窗口后才会切换。</p>
    <div class="toolbar route-toolbar">
      <NButton size="small" :loading="loading" @click="refresh">刷新组合评估</NButton>
      <NButton v-if="agentId && channelId" size="small" type="primary" :loading="acting==='propose'"
        :disabled="!!acting" @click="propose">评估并提议</NButton>
      <NButton v-if="routeState?.mode==='candidate'" size="small" :loading="acting==='cancel'"
        :disabled="!!acting" @click="cancel">取消候选</NButton>
    </div>
    <ErrorBanner :error="actionError" :retryable="false"/>
    <ErrorBanner :error="error" @retry="refresh"/>
    <section v-if="routeState" class="route-state" aria-label="当前模型组合">
      <div class="route-state-line">
        <strong>当前组合 {{ routeState.active_version }}</strong>
        <span>{{ memberText(routeState.active_members) }}</span>
        <span class="route-mode">{{ routeState.mode === 'candidate' ? '候选验证中' : '稳定' }}</span>
      </div>
      <div v-if="routeState.candidate_members" class="route-state-line">
        <span>候选组合：{{ memberText(routeState.candidate_members) }}</span>
        <span>综合评分 {{ number(routeState.candidate_score) }}</span>
        <span>有效观察窗口 {{ routeState.valid_windows }}</span>
        <span>评分增益 {{ number(routeState.delta_j) }}</span>
      </div>
      <ul v-if="routeState.drift?.length" class="route-drift" aria-label="需要调整的部分">
        <li v-for="item in routeState.drift ?? []" :key="item.attribute">
          {{ item.attribute }}：{{ item.previous ?? '未知' }} → {{ item.current ?? '未知' }}（{{ item.reason }}）
        </li>
      </ul>
      <p v-if="routeState.affected?.length" class="muted">
        需要调整的部分：{{ (routeState.affected ?? []).join('、') }}；保持不变：{{ (routeState.fixed ?? []).join('、') || '无' }}<span
          v-if="routeState.escalated">；本次需重新评估整个组合（{{ routeState.escalation_reason }}）</span>
      </p>
      <ul v-if="routeState.notices?.length" class="route-notices"><li v-for="notice in routeState.notices ?? []" :key="notice">{{ notice }}</li></ul>
    </section>
    <p v-if="loading && !data" class="muted" role="status">正在评估模型组合…</p>
    <template v-else-if="data">
      <p v-if="data.evidence" class="route-evidence" :class="data.evidence.confidence === 'confirmed' ? 'ok' : 'blocked'"
        aria-label="场景证据来源">
        场景证据来自{{ data.evidence.confidence === 'confirmed' ? '有效观察' : '观察不足' }}窗口
        {{ data.evidence.window_start.toFixed(1) }}–{{ data.evidence.window_end.toFixed(1) }} 秒
        <span v-if="data.evidence.confidence !== 'confirmed'">（当前监测规则尚无有效观察窗口，只能作为提示）</span>
      </p>
      <p v-else class="route-evidence muted" aria-label="场景证据来源">
        该视频源还没有观察记录，场景条件按未测定处理。
      </p>
      <ul v-if="data.notices.length" class="route-notices" aria-label="组合评估说明">
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
      <h3>其他可行组合</h3>
      <p v-if="!data.ranked.length" class="muted" role="status">暂无可行候选</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>模型组合</th><th>评分</th><th>覆盖</th><th>依赖</th><th>资源</th><th>切换</th></tr></thead>
          <tbody><tr v-for="row in data.ranked" :key="row.combination_id">
            <td class="wrap">{{ row.label }}<small class="route-members">{{ members(row) }}</small></td>
            <td>{{ number(row.score) }}</td><td>{{ number(row.coverage) }}</td>
            <td>{{ number(row.dependency) }}</td><td>{{ number(row.cost) }}</td><td>{{ number(row.switch) }}</td>
          </tr></tbody>
        </table>
      </div>
      <h3>不可用组合及原因</h3>
      <p v-if="!data.blocked.length" class="muted" role="status">没有候选被排除</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>模型组合</th><th>排除原因</th></tr></thead>
          <tbody><tr v-for="row in data.blocked" :key="row.combination_id">
            <td class="wrap">{{ row.label }}</td>
            <td class="wrap">{{ row.reasons.join('；') }}</td>
          </tr></tbody>
        </table>
      </div>
    </template>
    <details v-if="policies.data.value || timeline.data.value?.length" class="route-secondary">
      <summary>策略与变更记录</summary>
      <div class="route-secondary-content">
        <section v-if="policies.data.value" class="route-policies" aria-label="关联策略">
          <h3>关联策略</h3>
          <p class="muted">{{ policies.data.value.notice }}</p>
          <ul>
            <li v-for="policy in policies.data.value.items" :key="policy.name">
              <strong>{{ policy.label }}</strong>
              <span class="route-history-kind">{{ policy.installed ? '已安装' : '未安装' }}</span>
              <span v-if="policy.name === policies.data.value.resolved.name && policies.data.value.resolved.available">当前使用</span>
              <small>{{ (policy.limitations ?? []).join('；') }}</small>
            </li>
          </ul>
          <p class="route-active" :class="policies.data.value.resolved.available ? 'ok' : 'blocked'"
            aria-label="实际装载的策略">
            实际装载：{{ policies.data.value.resolved.available
              ? `${policies.data.value.resolved.name}（${policies.data.value.resolved.external ? '外部策略' : '内置策略'}）`
              : `不可用 —— ${policies.data.value.resolved.reason}` }}
            <small>配置项 {{ policies.data.value.active }}</small>
          </p>
        </section>
        <RouteTimeline v-if="timeline.data.value?.length" :entries="timeline.data.value"/>
      </div>
    </details>
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
.route-history { margin-bottom: 12px; }
.route-history ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.route-history li { display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; font-size: 12px; border-bottom: 1px solid rgba(128,128,128,.18); padding-bottom: 4px; }
.route-history-kind { border: 1px solid rgba(128,128,128,.35); border-radius: 10px; padding: 0 6px; font-size: 11px; }
.route-history small { opacity: .7; }
.route-secondary { margin-top: 16px; border-top: 1px solid rgba(128,128,128,.3); }
.route-secondary summary { min-height: 24px; padding: 10px 0; cursor: pointer; font-size: 13px; font-weight: 600; }
.route-secondary summary:focus-visible { outline: 2px solid #2367ed; outline-offset: 3px; }
.route-secondary-content { padding-top: 4px; }
.route-policies { margin-bottom: 12px; }
.route-policies ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.route-policies li { display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; font-size: 12px; }
.route-policies small { opacity: .7; }
.route-evidence { margin: 0 0 8px; font-size: 12px; }
.route-evidence.ok { color: #18a058; }
.route-evidence.blocked { color: #d03050; }
.route-active { margin: 8px 0 0; font-size: 12px; display: flex; flex-direction: column; gap: 2px; }
.route-active.ok { color: #18a058; }
.route-active.blocked { color: #d03050; }
h3 { margin: 12px 0 6px; font-size: 13px; }
</style>

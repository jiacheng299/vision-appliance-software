<script setup lang="ts">
import { computed } from 'vue'
import { NButton } from 'naive-ui'
import { agentApi, type RouteEvaluation } from './api'
import { useResource } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'

const props = defineProps<{ sourceId: string; rule: string; durationSeconds?: number | null }>()
const { data, loading, error, refresh } = useResource(() => agentApi.routes(props.sourceId, {
  rule: props.rule, duration_seconds: props.durationSeconds ?? undefined,
}))

const bucketLabel = computed(() => data.value?.scenario.bucket === 'default'
  ? '常规场景' : `场景分桶 ${data.value?.scenario.bucket ?? ''}`)

function number(value: number | null | undefined, digits = 3) {
  return value == null ? '—' : value.toFixed(digits)
}
function members(row: RouteEvaluation) { return row.members.join(' + ') }
</script>

<template>
  <section class="panel route-panel" aria-label="路由候选">
    <div class="panel-title"><h2>路由候选</h2><small>{{ bucketLabel }}</small></div>
    <p class="muted">按需求覆盖、依赖完整性、冲突、资源和切换代价评估模型执行组合。评估不改变正在运行的任务。</p>
    <div class="toolbar route-toolbar">
      <NButton size="small" :loading="loading" @click="refresh">刷新路由评估</NButton>
    </div>
    <ErrorBanner :error="error" @retry="refresh"/>
    <p v-if="loading && !data" class="muted" role="status">正在评估路由候选…</p>
    <template v-else-if="data">
      <ul v-if="data.notices.length" class="route-notices" aria-label="路由评估口径说明">
        <li v-for="notice in data.notices" :key="notice">{{ notice }}</li>
      </ul>
      <div class="route-chosen" :class="data.chosen ? 'ok' : 'blocked'">
        <template v-if="data.chosen">
          <strong>当前选择：{{ data.chosen.label }}</strong>
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
.route-toolbar { margin: 12px 0; }
.route-notices { margin: 0 0 12px; padding-left: 18px; font-size: 12px; opacity: .85; }
.route-chosen { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 8px; border: 1px solid rgba(128,128,128,.35); margin-bottom: 12px; }
.route-chosen.ok { border-color: rgba(24,160,88,.6); }
.route-chosen.blocked { border-color: rgba(208,48,80,.6); }
.route-members { display: block; opacity: .7; font-size: 11px; }
h3 { margin: 12px 0 6px; font-size: 13px; }
</style>

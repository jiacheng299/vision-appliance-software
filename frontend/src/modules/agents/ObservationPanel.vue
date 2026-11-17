<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import { agentApi, type Observation, type ObservationVerdict, type Run } from './api'
import type { Source } from '../../shared/api/types'
import { formatDate, useResource } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'

const props = defineProps<{ agentId: string; runs: Pick<Run, 'source_id'>[]; sources: Pick<Source, 'id' | 'name'>[] }>()
const sourceId = ref<string | null>(null)
const verdict = ref<ObservationVerdict | null>(null)
const names = computed(() => new Map(props.sources.map(source => [source.id, source.name])))
const sourceOptions = computed(() => [...new Set(props.runs.map(run => run.source_id))]
  .map(id => ({ label: names.value.get(id) ?? id, value: id })))
const verdictOptions: { label: string; value: ObservationVerdict }[] = [
  { label: '检测到', value: 'detected' },
  { label: '限定窗口未检出', value: 'not_detected' },
  { label: '观察不足', value: 'insufficient' },
]
const { data, loading, error, refresh } = useResource(() => agentApi.observations(props.agentId, {
  source_id: sourceId.value ?? undefined,
  verdict: verdict.value ?? undefined,
}))
watch([sourceId, verdict], () => { data.value = null; void refresh() })

const labels: Record<ObservationVerdict, string> = {
  detected: '检测到', not_detected: '限定窗口未检出', insufficient: '观察不足',
}
function window(row: Observation) {
  const start = row.window_start.toFixed(1), end = row.window_end.toFixed(1)
  return `${start}–${end} 秒`
}
function rate(row: Observation) {
  const fps = row.metrics.actual_fps
  return fps == null ? '未测定' : `${fps.toFixed(1)} 帧/秒`
}
function glare(row: Observation) {
  const ratio = row.metrics.overexposure_ratio
  return ratio == null ? '未测定' : `${(ratio * 100).toFixed(1)}%`
}
function reasons(row: Observation) {
  return row.reasons.length ? row.reasons.join('；') : '观察条件全部满足'
}
</script>

<template>
  <section class="panel observation-panel" aria-label="有效观察记录">
    <div class="panel-title"><h2>有效观察</h2><small>近期最多 30 条</small></div>
    <p class="muted">只展示实际帧窗口的判定结果。观察不足不等于事件未发生，未检出也不外推到其他时段或区域。</p>
    <div class="toolbar observation-filter">
      <NSelect v-model:value="sourceId" :options="sourceOptions" clearable placeholder="全部视频源"
        aria-label="按视频源筛选有效观察"/>
      <NSelect v-model:value="verdict" :options="verdictOptions" clearable placeholder="全部结论"
        aria-label="按结论筛选有效观察"/>
      <NButton size="small" :loading="loading" @click="refresh">刷新观察记录</NButton>
    </div>
    <ErrorBanner :error="error" @retry="refresh"/>
    <div v-if="data" class="observation-summary" aria-label="观察结论统计">
      <span v-for="item in verdictOptions" :key="item.value" class="observation-chip">
        {{ item.label }} {{ data.summary[item.value] ?? 0 }}
      </span>
    </div>
    <p v-if="loading && !data" class="muted" role="status">正在读取有效观察记录…</p>
    <p v-else-if="!error && !data?.items.length" class="muted" role="status">暂无有效观察记录</p>
    <div v-else-if="!error && data?.items.length" class="table-wrap">
      <table>
        <thead><tr><th>视频源</th><th>结论</th><th>帧窗口</th><th>实际帧率</th><th>过曝</th><th>说明</th></tr></thead>
        <tbody><tr v-for="row in data.items" :key="row.id">
          <td class="wrap">{{ names.get(row.source_id) ?? row.source_id }}</td>
          <td><span :class="['observation-verdict', row.verdict]">{{ labels[row.verdict] }}</span></td>
          <td>{{ window(row) }}</td>
          <td>{{ rate(row) }}</td>
          <td>{{ glare(row) }}</td>
          <td class="wrap">{{ reasons(row) }}</td>
        </tr></tbody>
      </table>
      <p class="muted">最近一条记录时间 {{ formatDate(data.items[0]?.created_at ?? null) }}</p>
    </div>
  </section>
</template>

<style scoped>
.observation-panel { margin-bottom: 16px; }
.observation-filter { margin: 12px 0; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.observation-filter .n-select { width: min(100%, 220px); }
.observation-summary { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.observation-chip { border: 1px solid rgba(128, 128, 128, .35); border-radius: 12px; padding: 2px 10px; font-size: 12px; }
.observation-verdict { font-weight: 600; }
.observation-verdict.detected { color: #18a058; }
.observation-verdict.not_detected { color: #2080f0; }
.observation-verdict.insufficient { color: #d03050; }
</style>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import { agentApi, type Run, type TrustCheck } from './api'
import type { Source } from '../../shared/api/types'
import { formatDate, useResource } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import EventDrawer from './EventDrawer.vue'

const props = defineProps<{ agentId: string; runs: Pick<Run, 'source_id'>[]; sources: Pick<Source, 'id' | 'name'>[] }>()
const sourceId = ref<string | null>(null)
const eventId = ref<string | null>(null)
const names = computed(() => new Map(props.sources.map(source => [source.id, source.name])))
const options = computed(() => [...new Set(props.runs.map(run => run.source_id))]
  .map(id => ({ label: names.value.get(id) ?? id, value: id })))
const { data, loading, error, refresh } = useResource(() => agentApi.trustChecks(props.agentId, sourceId.value ?? undefined))
watch(sourceId, () => { data.value = null; eventId.value = null; void refresh() })

const labels: Record<TrustCheck['reason'], string> = {
  invalid_sample_time: '采样时间异常', sample_time_not_increasing: '采样时间未递增',
  sample_gap: '采样间断', observation_interrupted: '观察中断', unstable_detection: '检测波动',
  event_scope_mismatch: '报警关联异常', event_media_range_invalid: '报警录像时间异常',
  evidence_unavailable: '证据未就绪', observer_failed: '检查异常',
}
function position(row: TrustCheck) {
  const start = row.start_seconds, end = row.end_seconds
  const first = start ?? end
  if (row.source_kind === 'camera') return '实时采样'
  if (first == null) return '—'
  return start != null && end != null && start !== end
    ? `${start.toFixed(1)}–${end.toFixed(1)} 秒` : `${first.toFixed(1)} 秒`
}
</script>

<template>
  <section class="panel trust-checks-panel" aria-label="可信检查记录">
    <div class="panel-title"><h2>可信检查</h2><small>近期最多 30 条</small></div>
    <p class="muted">回查采样、检测和证据异常。业务报警继续按任务规则产生。</p>
    <div class="toolbar trust-filter">
      <NSelect v-model:value="sourceId" :options="options" clearable placeholder="全部视频源"
        aria-label="筛选可信检查视频源"/>
      <NButton size="small" :loading="loading" @click="refresh">刷新检查记录</NButton>
    </div>
    <ErrorBanner :error="error" @retry="refresh"/>
    <p v-if="loading && !data" class="muted" role="status">正在读取可信检查记录…</p>
    <p v-else-if="!error && !data?.length" class="muted" role="status">暂无可信检查记录</p>
    <div v-else-if="!error && data?.length" class="table-wrap">
      <table>
        <thead><tr><th>视频源</th><th>检查结果</th><th>记录时间</th><th>录像位置</th><th>关联报警</th></tr></thead>
        <tbody><tr v-for="row in data" :key="`${row.run_id}:${row.observed_at}:${row.reason}`">
          <td class="wrap">{{ names.get(row.source_id) ?? row.source_id }}</td>
          <td>{{ labels[row.reason] }}</td><td>{{ formatDate(row.observed_at) }}</td><td>{{ position(row) }}</td>
          <td><NButton v-if="row.event_id" text type="primary" size="small" aria-label="查看关联报警"
            @click="eventId = row.event_id ?? null">查看报警</NButton><span v-else>—</span></td>
        </tr></tbody>
      </table>
    </div>
    <EventDrawer v-if="eventId" :agent-id="agentId" :event-id="eventId" :can-write="false" @close="eventId = null"/>
  </section>
</template>

<style scoped>
.trust-checks-panel { margin-bottom: 16px; }
.trust-filter { margin: 12px 0; }
.trust-filter .n-select { width: min(100%, 250px); }
</style>

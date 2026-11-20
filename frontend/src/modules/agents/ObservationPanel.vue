<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import { agentApi, type Observation, type ObservationVerdict, type Run } from './api'
import type { Source } from '../../shared/api/types'
import { formatDate, useResource } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'

const props = defineProps<{ agentId: string; runs: Pick<Run, 'source_id'>[]; sources: Pick<Source, 'id' | 'name'>[] }>()
const emit = defineEmits<{ openRoute: [target: { sourceId: string; channelId: string | null }] }>()
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
const PAGE_SIZE = 10
const pageStartCursors = ref<(string | undefined)[]>([undefined])
const pageIndex = ref(0)
const canPrev = computed(() => pageIndex.value > 0)
const canNext = computed(() => !!data.value?.next_cursor)
function resetPages() { pageStartCursors.value = [undefined]; pageIndex.value = 0 }
function nextPage() {
  const cursor = data.value?.next_cursor
  if (!cursor) return
  pageStartCursors.value = [...pageStartCursors.value.slice(0, pageIndex.value + 1), cursor]
  pageIndex.value += 1
  void refresh()
}
function prevPage() {
  if (pageIndex.value === 0) return
  pageIndex.value -= 1
  void refresh()
}
const { data, loading, error, refresh } = useResource(() => agentApi.observations(props.agentId, {
  source_id: sourceId.value ?? undefined,
  verdict: verdict.value ?? undefined,
}, pageStartCursors.value[pageIndex.value] ?? undefined, PAGE_SIZE))
watch([sourceId, verdict], () => { resetPages(); data.value = null; void refresh() })

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
const storedReasonLabels: Record<string, string> = {
  '路由、画像或模型版本与当前不一致。': '模型组合、场景记录或模型版本与当前不一致。',
}
function reasons(row: Observation) {
  return row.reasons.length
    ? row.reasons.map(reason => storedReasonLabels[reason] ?? reason).join('；')
    : '观察条件全部满足'
}

// 观察条件逐项明细：这是"观察不足"与"未检出"分界线的具体依据
const selected = ref<Observation | null>(null)
const gateLabels: Record<string, string> = {
  frame_count: '成功解码帧数', time_continuous: '帧时间连续', actual_fps: '实际帧率',
  max_gap_seconds: '最大帧间隔', window_seconds: '观察窗口',
  roi_visible_ratio: '区域可见比例', overexposure_ratio: '过曝比例',
  blur_score: '画面清晰度', occlusion_ratio: '遮挡比例', target_scale_px: '可辨目标尺度',
  path_complete: '执行路径完整', version_consistency: '版本一致',
}
const statusLabels: Record<string, string> = {
  pass: '通过', fail: '不通过', unverified: '未测定', not_applicable: '不适用',
}
const gateReasons: Record<string, string> = {
  frame_absent: '窗口内没有任何成功解码的帧',
  frame_rate_low: '实际帧率低于门槛', frame_gap_large: '帧间隔超过允许值',
  window_short: '观察窗口短于要求', frame_time_discontinuous: '窗口内帧时间回退或不可用',
  roi_not_visible: '区域可见比例不足', overexposed: '过曝比例超过门槛',
  blurred: '清晰度低于门槛', occluded: '遮挡比例超过门槛',
  target_too_small: '可辨目标尺度不足', path_incomplete: '执行路径不完整或输出不可解析',
  version_mismatch: '模型组合、场景记录或模型版本不一致',
  unverified_frame: '帧时间指标未测定', unverified_roi: '区域可见比例未测定',
  unverified_quality: '画面质量指标未测定', unverified_scale: '目标尺度未测定',
}
function gateValue(value: number | null | undefined) {
  if (value == null) return '未测定'
  return Number.isInteger(value) ? String(value) : value.toFixed(3)
}
function metricRows(row: Observation) {
  const metrics = row.metrics
  return [
    ['成功解码帧数', gateValue(metrics.frame_count)],
    ['实际帧率', metrics.actual_fps == null ? '未测定' : `${metrics.actual_fps.toFixed(2)} 帧/秒`],
    ['最大帧间隔', metrics.max_gap_seconds == null ? '未测定' : `${metrics.max_gap_seconds.toFixed(2)} 秒`],
    ['区域可见比例', metrics.roi_visible_ratio == null ? '未测定' : `${(metrics.roi_visible_ratio * 100).toFixed(1)}%`],
    ['过曝比例', metrics.overexposure_ratio == null ? '未测定' : `${(metrics.overexposure_ratio * 100).toFixed(1)}%`],
    ['画面清晰度', metrics.blur_score == null ? '未测定' : metrics.blur_score.toFixed(1)],
    ['遮挡比例', metrics.occlusion_ratio == null ? '未测定' : `${(metrics.occlusion_ratio * 100).toFixed(1)}%`],
    ['可辨目标尺度', metrics.target_scale_px == null ? '未测定' : `${metrics.target_scale_px.toFixed(0)} 像素`],
  ]
}

</script>

<template>
  <section class="panel observation-panel" aria-label="观察记录">
    <div class="panel-title"><h2>观察记录</h2><small>分页显示 · 每页 {{ PAGE_SIZE }} 条</small></div>
    <p class="muted">只展示实际画面时段的判定结果。观察不足不等于事件未发生，未检出也不外推到其他时段或区域。</p>
    <div class="toolbar observation-filter">
      <NSelect v-model:value="sourceId" :options="sourceOptions" clearable placeholder="全部视频源"
        aria-label="按视频源筛选观察记录"/>
      <NSelect v-model:value="verdict" :options="verdictOptions" clearable placeholder="全部结论"
        aria-label="按结论筛选观察记录"/>
      <NButton size="small" :loading="loading" @click="refresh">刷新观察记录</NButton>
    </div>
    <ErrorBanner :error="error" @retry="refresh"/>
    <div v-if="data" class="observation-summary" aria-label="观察结论统计">
      <span v-for="item in verdictOptions" :key="item.value" class="observation-chip">
        {{ item.label }} {{ data.summary[item.value] ?? 0 }}
      </span>
    </div>
    <p v-if="loading && !data" class="muted" role="status">正在读取观察记录…</p>
    <p v-else-if="!error && !data?.items.length" class="muted" role="status">暂无观察记录</p>
    <div v-else-if="!error && data?.items.length" class="table-wrap">
      <table>
        <thead><tr><th>视频源</th><th>结论</th><th>观察时段</th><th>实际帧率</th><th>过曝</th><th>模型组合版本</th><th>需要调整的部分</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in data.items" :key="row.id"
          :class="{ picked: selected?.id === row.id }">
          <td class="wrap">{{ names.get(row.source_id) ?? row.source_id }}</td>
          <td><span :class="['observation-verdict', row.verdict]">{{ labels[row.verdict] }}</span></td>
          <td>{{ window(row) }}</td>
          <td>{{ rate(row) }}</td>
          <td>{{ glare(row) }}</td>
          <td>{{ row.route_version ?? '—' }}</td>
          <td class="wrap">{{ reasons(row) }}</td>
          <td class="observation-actions">
            <NButton text type="primary" size="small" aria-label="查看该条观察的观察条件"
              @click="selected = row">观察条件</NButton>
            <NButton text type="primary" size="small" aria-label="查看该视频源的模型组合"
              @click="emit('openRoute', { sourceId: row.source_id, channelId: row.path_id ?? null })">模型组合</NButton>
          </td>
        </tr></tbody>
      </table>
      <p class="muted">最近一条记录时间 {{ formatDate(data.items[0]?.created_at ?? null) }}</p>
      <div class="observation-pager" aria-label="观察记录分页">
        <NButton size="small" :disabled="!canPrev" @click="prevPage">上一页</NButton>
        <span>第 {{ pageIndex + 1 }} 页</span>
        <NButton size="small" :disabled="!canNext" @click="nextPage">下一页</NButton>
      </div>
    </div>

    <section v-if="selected" class="observation-detail" aria-label="观察条件明细">
      <div class="observation-detail-head">
        <h3>{{ labels[selected.verdict] }} · {{ window(selected) }}</h3>
        <NButton size="tiny" @click="selected = null">关闭</NButton>
      </div>
      <p class="muted">{{ reasons(selected) }}</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>观察条件</th><th>结果</th><th>实测</th><th>要求</th><th>说明</th></tr></thead>
          <tbody><tr v-for="gate in selected.gates" :key="gate.name">
            <td>{{ gateLabels[gate.name] ?? gate.name }}</td>
            <td><span :class="['observation-gate', gate.status]">{{ statusLabels[gate.status] ?? gate.status }}</span></td>
            <td>{{ gateValue(gate.value) }}</td>
            <td>{{ gateValue(gate.threshold) }}</td>
            <td class="wrap">{{ gate.reason ? (gateReasons[gate.reason] ?? gate.reason) : '—' }}</td>
          </tr></tbody>
        </table>
      </div>
      <h4>实测指标</h4>
      <ul class="observation-metrics" aria-label="实测指标">
        <li v-for="[label, value] in metricRows(selected)" :key="label">{{ label }}：{{ value }}</li>
      </ul>
      <p class="muted">
        模型组合版本 {{ selected.route_version ?? '—' }} · 场景记录版本 {{ selected.profile_version ?? '—' }}
        · 模型版本 {{ selected.model_version ?? '—' }} · 执行路径 {{ selected.path_id ?? '—' }}
      </p>
      <p class="muted">同一观察时段内的条件必须全部满足，空结果才允许写成“限定窗口未检出”；未测定的条件只阻止未检出，不阻止检测到。</p>
    </section>
  </section>
</template>

<style scoped>
.observation-panel { margin-bottom: 16px; }
.observation-filter { margin: 12px 0; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.observation-filter .n-select { width: min(100%, 220px); }
.observation-summary { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.observation-pager { display: flex; gap: 12px; align-items: center; margin-top: 8px; font-size: 12px; }
.observation-chip { border: 1px solid rgba(128, 128, 128, .35); border-radius: 12px; padding: 2px 10px; font-size: 12px; }
.observation-verdict { font-weight: 600; }
.observation-verdict.detected { color: #18a058; }
.observation-verdict.not_detected { color: #2080f0; }
.observation-verdict.insufficient { color: #d03050; }
.observation-actions { display: flex; gap: 8px; }
.observation-actions :deep(.n-button), .observation-detail-head :deep(.n-button) { min-width: 24px; min-height: 24px; }
tr.picked { background: rgba(32, 128, 240, .08); }
.observation-detail { margin-top: 16px; border-top: 1px solid rgba(128, 128, 128, .3); padding-top: 12px; }
.observation-detail-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.observation-gate.pass { color: #18a058; }
.observation-gate.fail { color: #d03050; }
.observation-gate.unverified { color: #f0a020; }
.observation-gate.not_applicable { opacity: .6; }
.observation-metrics { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 2px 12px; padding-left: 18px; font-size: 12px; }
h4 { margin: 12px 0 4px; font-size: 13px; }
</style>

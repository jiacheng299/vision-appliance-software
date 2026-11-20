<script setup lang="ts">
import { computed } from 'vue'
import type { RouteState, RouteView } from './api'

const props = defineProps<{ rule: string; evaluation: RouteView | null
  state: RouteState | null }>()

// 与 backend/app/modules/routing/graph.py 的需求图保持一致，仅作呈现。
const chains: Record<string, { label: string; weight: string }[]> = {
  absence: [{ label: '人员数量检测', weight: '1.0' }],
  intrusion: [{ label: '人员检测', weight: '0.5' },
    { label: '跨帧跟踪', weight: '0.3' }, { label: '区域相交确认', weight: '0.2' }],
}
const chain = computed(() => chains[props.rule] ?? [])
const evidence = computed(() => props.evaluation?.evidence ?? null)
const chosen = computed(() => props.evaluation?.chosen ?? null)
const blockedCount = computed(() => props.evaluation?.blocked.length ?? 0)
const evidenceText = computed(() => {
  const row = evidence.value
  if (!row) return '尚无观察记录，场景条件按未测定处理。'
  const span = `${row.window_start.toFixed(1)}–${row.window_end.toFixed(1)} 秒`
  return row.confidence === 'confirmed'
    ? `有效观察窗口 ${span}，观察条件全部满足。`
    : `观察不足窗口 ${span}，仅作提示，不参与场景求解。`
})
function score(value: number | null | undefined) { return value == null ? '—' : value.toFixed(3) }
const hysteresisText = computed(() => {
  const row = props.state
  if (!row) return '绑定任务后可见。'
  const mode = row.mode === 'candidate' ? '候选验证中' : '稳定'
  return row.mode === 'candidate'
    ? `${mode} · 评分增益 ${score(row.delta_j)} · 已积累有效窗口 ${row.valid_windows}`
    : `${mode} · 当前组合持续工作`
})
</script>

<template>
  <section class="patent-points" aria-label="专利技术要点">
    <h3>专利技术要点</h3>
    <dl>
      <div>
        <dt>需求链</dt>
        <dd v-if="chain.length"><span class="patent-chain">{{ chain.map(item => `${item.label} ${item.weight}`).join(' → ') }}</span></dd>
        <dd v-else>—</dd>
      </div>
      <div>
        <dt>有效观察</dt>
        <dd :class="evidence && evidence.confidence !== 'confirmed' ? 'patent-warn' : ''">{{ evidenceText }}</dd>
      </div>
      <div>
        <dt>组合求解</dt>
        <dd v-if="chosen">首选 {{ chosen.label }}，综合评分 {{ score(chosen.score) }}；{{ blockedCount }} 组候选被硬约束排除。</dd>
        <dd v-else>没有可行组合{{ evaluation ? '，需要补充能力或不满足观察条件' : '' }}。</dd>
      </div>
      <div>
        <dt>滞回切换</dt>
        <dd>{{ hysteresisText }}</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.patent-points { margin: 0 0 12px; padding: 10px 12px; border: 1px solid rgba(128,128,128,.35);
  border-left: 3px solid #2367ed; border-radius: 8px; }
h3 { margin: 0 0 6px; font-size: 13px; font-weight: 600; }
dl { margin: 0; display: flex; flex-direction: column; gap: 4px; }
dl > div { display: flex; gap: 8px; align-items: baseline; font-size: 12px; }
dt { flex: 0 0 56px; color: #667085; }
dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.patent-chain { font-weight: 600; }
.patent-warn { color: #b54708; }
@media (max-width: 560px) {
  dl > div { flex-direction: column; gap: 2px; }
}
</style>

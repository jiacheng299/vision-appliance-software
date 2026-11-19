<script setup lang="ts">
import { computed, watch } from 'vue'
import { NTag } from 'naive-ui'
import { agentApi, type ObservationVerdict } from './api'
import { profileApi } from '../sources/profileApi'
import { useResource } from '../../shared/ui/resource'

const props = defineProps<{ agentId: string; sourceId?: string | null; channelId?: string | null
  real: boolean }>()

// 三块数据各取所需：观察结论分布、当前组合版本、场景记录版本
const observations = useResource(() => props.real
  ? agentApi.observations(props.agentId, props.sourceId ? { source_id: props.sourceId } : {}, undefined)
  : Promise.resolve(null))
const routes = useResource(() => props.real
  ? agentApi.routeStates(props.agentId)
  : Promise.resolve([]))
const profile = useResource(() => props.real && props.sourceId
  ? profileApi.read(props.sourceId)
  : Promise.resolve(null))

const verdictCounts = computed(() => {
  const data = observations.data.value
  if (!data) return null
  if (!props.sourceId) return data.summary ?? null
  const counts: Record<ObservationVerdict, number> = { detected: 0, not_detected: 0, insufficient: 0 }
  for (const item of data.items) counts[item.verdict] += 1
  return counts
})
const route = computed(() => {
  const rows = routes.data.value ?? []
  return rows.find(item => (!props.sourceId || item.source_id === props.sourceId)
    && (!props.channelId || item.channel_id === props.channelId)) ?? null
})
const profileVersion = computed(() => profile.data.value?.version ?? null)
const observationScope = computed(() => props.sourceId ? '当前视频最近 30 条' : '任务累计')

function count(key: ObservationVerdict) {
  const value = verdictCounts.value?.[key]
  return typeof value === 'number' ? value : null
}
const hasObservations = computed(() =>
  (['detected', 'not_detected', 'insufficient'] as const).some(key => (count(key) ?? 0) > 0))
watch(() => [props.agentId, props.sourceId, props.channelId, props.real], () => {
  observations.data.value = null
  routes.data.value = null
  profile.data.value = null
  void observations.refresh()
  void routes.refresh()
  void profile.refresh()
})
</script>

<template>
  <section v-if="real" class="task-summary" aria-label="任务可观察性摘要">
    <div class="task-summary-item">
      <span class="task-summary-label">场景记录</span>
      <span v-if="profile.error.value" class="task-summary-error" role="alert">加载失败：{{ profile.error.value }}</span>
      <span v-else-if="profile.loading.value && !profile.data.value" class="muted" role="status">正在读取</span>
      <NTag v-else-if="profileVersion !== null" size="small" :bordered="false">v{{ profileVersion }}</NTag>
      <span v-else class="muted">无记录</span>
    </div>
    <div class="task-summary-item">
      <span class="task-summary-label">最近观察（{{ observationScope }}）</span>
      <span v-if="observations.error.value" class="task-summary-error" role="alert">加载失败：{{ observations.error.value }}</span>
      <span v-else-if="observations.loading.value && !observations.data.value" class="muted" role="status">正在读取</span>
      <template v-else-if="verdictCounts && hasObservations">
        <NTag size="small" :bordered="false" type="success">检测到 {{ count('detected') ?? 0 }}</NTag>
        <NTag size="small" :bordered="false" type="info">未检出 {{ count('not_detected') ?? 0 }}</NTag>
        <NTag size="small" :bordered="false" type="error">观察不足 {{ count('insufficient') ?? 0 }}</NTag>
      </template>
      <span v-else class="muted">无记录</span>
    </div>
    <div class="task-summary-item">
      <span class="task-summary-label">当前组合</span>
      <span v-if="routes.error.value" class="task-summary-error" role="alert">加载失败：{{ routes.error.value }}</span>
      <span v-else-if="routes.loading.value && !routes.data.value" class="muted" role="status">正在读取</span>
      <template v-else-if="route">
        <NTag size="small" :bordered="false">{{ route.active_version }}</NTag>
        <NTag size="small" :bordered="false" :type="route.mode === 'candidate' ? 'warning' : 'default'">
          {{ route.mode === 'candidate' ? '候选验证中' : '稳定' }}
        </NTag>
        <small class="muted">{{ route.active_members.join(' + ') }}</small>
      </template>
      <span v-else class="muted">尚未建立</span>
    </div>
    <p class="task-summary-note muted">
      "观察不足"不等于事件未发生；未检出也不外推到其他时段或区域。
    </p>
  </section>
</template>

<style scoped>
.task-summary { display: flex; gap: 20px; flex-wrap: wrap; align-items: center; padding: 8px 12px; margin-bottom: 10px; border: 1px solid rgba(128, 128, 128, .28); border-radius: 8px; font-size: 12px; }
.task-summary-item { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.task-summary-label { opacity: .7; }
.task-summary-error { color: #d03050; overflow-wrap: anywhere; }
.task-summary-note { flex-basis: 100%; margin: 0; font-size: 11px; }
</style>

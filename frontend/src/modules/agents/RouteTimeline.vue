<script setup lang="ts">
import { computed } from 'vue'
import type { RouteDecision } from './api'
import { formatDate } from '../../shared/ui/resource'

const props = defineProps<{ decisions: RouteDecision[] }>()

const actionLabels: Record<string, string> = {
  hold: '保持', enter: '进入候选', cancel: '取消候选', switch: '切换版本',
}
const kindLabels: Record<string, string> = {
  baseline: '建立基线', refresh: '无漂移刷新', drift: '属性漂移', expiry: '属性过期',
  blocked: '无可行组合', cancel: '人工取消', window: '观察窗口',
}

// 时间线从旧到新读，和人的阅读方向一致
const ordered = computed(() => [...props.decisions].reverse())

function versionChanged(index: number) {
  if (index === 0) return false
  const previous = ordered.value[index - 1]?.route_version
  return !!ordered.value[index]?.route_version && previous !== ordered.value[index]?.route_version
}

interface DriftRow { attribute: string; previous?: string | null; current?: string | null }

function driftRows(item: RouteDecision): DriftRow[] {
  const rows = (item.payload as { drift?: DriftRow[] } | undefined)?.drift
  return Array.isArray(rows) ? rows : []
}

function affected(item: RouteDecision): string[] {
  const rows = (item.payload as { affected?: string[] } | undefined)?.affected
  return Array.isArray(rows) ? rows : []
}

function candidate(item: RouteDecision): string[] {
  const rows = (item.payload as { candidate?: string[] | null } | undefined)?.candidate
  return Array.isArray(rows) ? rows : []
}

function delta(item: RouteDecision) {
  return item.delta_j == null ? null : item.delta_j.toFixed(3)
}
</script>

<template>
  <section class="route-timeline-panel" aria-label="路由版本时间线">
    <h3>路由版本时间线</h3>
    <p class="muted">按发生顺序排列，标出每次决策是否改变了路由版本。</p>
    <p v-if="!ordered.length" class="muted" role="status">还没有路由决策记录。</p>
    <ol v-else class="route-timeline">
      <li v-for="(item, index) in ordered" :key="item.id" :class="{ changed: versionChanged(index) }">
        <span class="route-dot" aria-hidden="true"/>
        <div class="route-entry">
          <div class="route-entry-head">
            <strong>{{ actionLabels[item.action] ?? item.action }}</strong>
            <span class="route-kind">{{ kindLabels[item.kind] ?? item.kind }}</span>
            <span v-if="item.route_version" class="route-version">{{ item.route_version }}</span>
            <small>{{ formatDate(item.created_at) }}<template v-if="delta(item)"> · ΔJ {{ delta(item) }}</template></small>
          </div>
          <p class="route-reason">{{ item.reason }}</p>
          <ul v-if="driftRows(item).length" class="route-drift-rows" aria-label="本次决策的属性变化">
            <li v-for="row in driftRows(item)" :key="row.attribute">
              {{ row.attribute }}：{{ row.previous ?? '未知' }} → {{ row.current ?? '未知' }}
            </li>
          </ul>
          <p v-if="affected(item).length" class="muted">
            受影响子图：{{ affected(item).join('、') }}
            <template v-if="candidate(item).length"> · 候选：{{ candidate(item).join(' + ') }}</template>
          </p>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.route-timeline-panel { margin-bottom: 12px; }
.route-timeline { list-style: none; margin: 0; padding: 0 0 0 14px; position: relative; }
.route-timeline::before { content: ''; position: absolute; left: 4px; top: 4px; bottom: 4px; width: 2px; background: rgba(128, 128, 128, .28); }
.route-timeline li { position: relative; padding: 0 0 12px 8px; }
.route-dot { position: absolute; left: -14px; top: 5px; width: 8px; height: 8px; border-radius: 50%; background: rgba(128, 128, 128, .55); }
.route-timeline li.changed .route-dot { background: #18a058; box-shadow: 0 0 0 3px rgba(24, 160, 88, .18); }
.route-entry-head { display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; font-size: 13px; }
.route-kind { border: 1px solid rgba(128, 128, 128, .35); border-radius: 10px; padding: 0 6px; font-size: 11px; }
.route-version { font-size: 11px; opacity: .85; }
.route-entry-head small { opacity: .7; }
.route-reason { margin: 2px 0 0; font-size: 12px; }
.route-drift-rows { margin: 4px 0 0; padding-left: 18px; font-size: 12px; opacity: .9; }
</style>

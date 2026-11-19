<script setup lang="ts">
import { computed } from 'vue'
import type { TimelineEntry } from './api'
import { formatDate } from '../../shared/ui/resource'

const props = defineProps<{ entries: TimelineEntry[] }>()

const originLabels: Record<string, string> = { profile: '观察条件', route: '模型组合' }
const actionLabels: Record<string, string> = {
  hold: '保持当前组合', enter: '开始验证候选', cancel: '取消候选', switch: '切换模型组合',
}
const kindLabels: Record<string, string> = {
  baseline: '建立初始记录', refresh: '观察条件未变', drift: '观察条件变化', expiry: '观察条件过期',
  blocked: '无可用模型组合', window: '有效观察窗口',
  intrinsic: '基础能力更新', attribute_write: '更新观察条件', attribute_delete: '删除观察条件',
  cancel: '人工取消',
}

// 从旧到新读，和人的阅读方向一致
const ordered = computed(() => [...props.entries].reverse())

function label(entry: TimelineEntry) {
  if (entry.origin === 'route' && entry.action) {
    return actionLabels[entry.action] ?? entry.action
  }
  return kindLabels[entry.kind] ?? entry.kind
}

/** 同一来源（观察条件或模型组合）的版本真的换了，才标一次 */
function versionChanged(index: number) {
  const current = ordered.value[index]
  if (!current) return false
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const previous = ordered.value[cursor]
    if (previous.origin !== current.origin) continue
    return previous.version !== current.version
  }
  return false
}

function delta(entry: TimelineEntry) {
  return entry.delta_j == null ? null : entry.delta_j.toFixed(3)
}
function summary(entry: TimelineEntry) {
  return entry.summary.replace(/ΔJ\s*=\s*/g, '当前评分增益 ')
}
</script>

<template>
  <section class="route-timeline-panel" aria-label="运行调整时间线">
    <h3>观察与组合记录</h3>
    <p class="muted">按时间查看观察条件与模型组合的变化；绿色节点表示对应记录已更新版本。</p>
    <p v-if="!ordered.length" class="muted" role="status">还没有观察条件或模型组合记录。</p>
    <ol v-else class="route-timeline">
      <li v-for="(entry, index) in ordered" :key="entry.id"
        :class="{ changed: versionChanged(index), [entry.origin]: true }">
        <span class="route-dot" aria-hidden="true"/>
        <div class="route-entry">
          <div class="route-entry-head">
            <span class="route-origin">{{ originLabels[entry.origin] ?? entry.origin }}</span>
            <strong>{{ label(entry) }}</strong>
            <span v-if="entry.origin === 'route'" class="route-kind">{{ kindLabels[entry.kind] ?? entry.kind }}</span>
            <span class="route-version">{{ entry.version }}</span>
            <small>{{ formatDate(entry.at) }}<template v-if="delta(entry)"> · 评分增益 {{ delta(entry) }}</template></small>
          </div>
          <p class="route-reason">{{ summary(entry) }}</p>
          <p v-if="entry.attribute" class="route-drift-line" aria-label="观察条件变化">
            {{ entry.attribute }}：{{ entry.previous ?? '未知' }} → {{ entry.current ?? '未知' }}
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
.route-origin { border: 1px solid rgba(128, 128, 128, .35); border-radius: 10px; padding: 0 6px; font-size: 11px; opacity: .8; }
.route-version { font-size: 11px; opacity: .85; }
.route-kind { border: 1px solid rgba(128, 128, 128, .35); border-radius: 10px; padding: 0 6px; font-size: 11px; }
.route-entry-head small { opacity: .7; }
.route-reason { margin: 2px 0 0; font-size: 12px; }
.route-drift-line { margin: 4px 0 0; font-size: 12px; opacity: .9; }
</style>

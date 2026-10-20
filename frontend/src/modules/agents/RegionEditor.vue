<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton } from 'naive-ui'
import type { Region } from './api'
import type { Source } from '../../shared/api/types'
import { safeMediaUrl } from '../../shared/media/url'
const props = defineProps<{ regions: Region[]; source?: Source; disabled?: boolean }>()
const emit = defineEmits<{ change: [regions: Region[]]; pending: [pending: boolean] }>()
const points = ref<[number, number][]>([]), error = ref('')
watch(() => points.value.length, count => emit('pending', count > 0), { immediate: true })
const thumbnail = computed(() => safeMediaUrl(props.source?.thumbnail_url ?? null))
const encoded = (values: number[][]) => values.map(p => `${p[0]! * 1000},${p[1]! * 1000}`).join(' ')
function add(event: MouseEvent) {
  if (props.disabled || !thumbnail.value || points.value.length >= 64) return
  const rect = event.currentTarget instanceof Element ? event.currentTarget.getBoundingClientRect() : null
  if (!rect) return
  points.value.push([Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))])
  error.value = ''
}
function finish() {
  if (points.value.length < 3) { error.value = '至少点击三个点，才能围成区域。'; return }
  emit('change', [...props.regions, { id: crypto.randomUUID(), name: `区域 ${props.regions.length + 1}`, points: points.value.map(p => [...p]) }])
  points.value = []
}
</script>
<template>
  <div class="roi-editor">
    <p class="muted">在缩略图上依次点击边界点，完成后保存区域。区域边界不能交叉。</p>
    <div v-if="thumbnail" class="roi-image" :style="{ aspectRatio: source?.width && source?.height ? `${source.width}/${source.height}` : '16/9' }">
      <img :src="thumbnail" alt="视频源缩略图，用于绘制监测区域"/>
      <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" role="img" aria-label="点击画面绘制多边形区域" @click="add">
        <polygon v-for="region in regions" :key="region.id" :points="encoded(region.points)" class="roi-saved"/>
        <polyline :points="encoded(points)" class="roi-pending"/>
        <circle v-for="(p, index) in points" :key="index" :cx="p[0]*1000" :cy="p[1]*1000" r="8" fill="#fff"/>
      </svg>
    </div>
    <p v-else class="notice">该视频源还没有可用缩略图。请先在视频源管理中导入并处理录像，再绘制区域。</p>
    <div class="agent-actions"><NButton size="small" :disabled="disabled || !points.length" @click="points.pop()">撤销点</NButton><NButton size="small" :disabled="disabled || !points.length || regions.length >= 32" @click="finish">保存区域</NButton><span class="muted">已选 {{points.length}} 个点</span></div>
    <p v-if="error" role="alert">{{error}}</p>
    <div v-for="region in regions" :key="region.id" class="agent-region-row"><span>{{region.name || '监测区域'}} · {{region.points.length}} 个边界点</span><NButton size="tiny" :disabled="disabled" @click="emit('change', regions.filter(r => r.id !== region.id))">移除</NButton></div>
  </div>
</template>

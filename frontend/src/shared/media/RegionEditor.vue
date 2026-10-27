<script setup lang="ts">
import { newId } from '../ids'
import { computed, ref, watch } from 'vue'
import { NButton } from 'naive-ui'
import type { components } from '../api/generated'
type Region = components['schemas']['Region']
import type { Source } from '../api/types'
import { safeMediaUrl } from './url'
import { nearPoint, regionError, type Point } from './regionGeometry'
const props = defineProps<{ regions: Region[]; source?: Source; disabled?: boolean; demo?:boolean }>()
const emit = defineEmits<{ change: [regions: Region[]]; pending: [pending: boolean] }>()
const points = ref<Point[]>([]), error = ref(''), closed=ref(false), notice=ref('')
watch(() => points.value.length, count => emit('pending', count > 0), { immediate: true })
const thumbnail = computed(() => safeMediaUrl(props.source?.thumbnail_url ?? null))
const encoded = (values: number[][]) => values.map(p => `${p[0]! * 1000},${p[1]! * 1000}`).join(' ')
function add(event: MouseEvent) {
  if (props.disabled || (!thumbnail.value&&!props.demo)) return
  if (closed.value) { notice.value='区域已闭合，请保存区域，或撤销闭合后继续调整。'; return }
  const rect = event.currentTarget instanceof Element ? event.currentTarget.getBoundingClientRect() : null
  if (!rect) return
  if(!rect.width||!rect.height)return
  const point:Point=[Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))]
  error.value = ''
  notice.value=''
  if(points.value.length>=2&&nearPoint(point,points.value[0]!,rect.width,rect.height)){
    error.value=regionError(points.value)
    if(!error.value){closed.value=true;notice.value='已吸附起点并闭合，可以保存区域。'}
    return
  }
  const last=points.value.at(-1)
  if(last&&nearPoint(point,last,rect.width,rect.height)){notice.value='相邻点距离小于约10像素，已自动合并。';return}
  if(points.value.length>=64){error.value='已达到64个点，请点击起点闭合。';return}
  points.value.push(point)
}
function undo(){if(props.disabled)return;if(closed.value)closed.value=false;else points.value.pop();error.value='';notice.value=''}
function finish() {
  if(props.disabled||props.regions.length>=32)return
  if(!closed.value){error.value='区域尚未闭合，请沿边界绘制至少三个点，再点击起点附近闭合。';return}
  error.value=regionError(points.value)
  if(error.value)return
  emit('change', [...props.regions, { id: newId(), name: `区域 ${props.regions.length + 1}`, points: points.value.map(p => [...p]) }])
  points.value = []
  closed.value=false;notice.value='封闭区域已添加，请继续保存配置草稿。'
}
</script>
<template>
  <div class="roi-editor">
    <p class="muted">依次点击至少三个边界点，再点击绿色起点附近闭合，最后保存区域。相邻点约10像素内自动合并，边界不能交叉。</p>
    <div v-if="thumbnail||demo" class="roi-image" :style="{ aspectRatio: source?.width && source?.height ? `${source.width}/${source.height}` : '16/9' }">
      <img v-if="thumbnail" :src="thumbnail" alt="视频源缩略图，用于绘制监测区域"/><span v-else class="mock-room-label">模拟画面，仅用于练习划区</span>
      <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" role="img" aria-label="点击画面绘制多边形区域" @click="add">
        <polygon v-for="region in regions" :key="region.id" :points="encoded(region.points)" class="roi-saved"/>
        <polygon v-if="closed" :points="encoded(points)" class="roi-pending roi-closed"/>
        <polyline v-else :points="encoded(points)" class="roi-pending"/>
        <circle v-for="(p, index) in points" :key="index" :cx="p[0]*1000" :cy="p[1]*1000" r="8" fill="#fff"/>
        <circle v-if="points.length" :cx="points[0]![0]*1000" :cy="points[0]![1]*1000" r="12" fill="#39cc98" stroke="#fff" stroke-width="2" vector-effect="non-scaling-stroke"/>
      </svg>
    </div>
    <p v-else class="notice">该视频源还没有可用缩略图。请先在视频源管理中导入并处理录像，再绘制区域。</p>
    <div class="agent-actions"><NButton size="small" :disabled="disabled || !points.length" @click="undo">{{closed?'撤销闭合':'撤销点'}}</NButton><NButton size="small" :disabled="disabled || !points.length || regions.length >= 32" @click="finish">保存区域</NButton><span class="muted">已选 {{points.length}} 个点 · {{closed?'已闭合':'未闭合'}}</span></div>
    <p v-if="notice" class="roi-feedback" role="status">{{notice}}</p>
    <p v-if="error" role="alert">{{error}}</p>
    <div v-for="region in regions" :key="region.id" class="agent-region-row"><span>{{region.name || '监测区域'}} · {{region.points.length}} 个边界点</span><NButton size="tiny" :disabled="disabled" @click="emit('change', regions.filter(r => r.id !== region.id))">移除</NButton></div>
  </div>
</template>

<style scoped>
.roi-editor{font-size:12px}.roi-image{position:relative;margin-top:10px;background:#14243b}.roi-image img,.roi-image svg{position:absolute;width:100%;height:100%;inset:0}.roi-image img{object-fit:fill}.roi-image svg{cursor:crosshair}.roi-saved{fill:#2367ed44;stroke:#7daeff;stroke-width:4;vector-effect:non-scaling-stroke}.roi-pending{fill:none;stroke:#ffce6b;stroke-width:3;vector-effect:non-scaling-stroke}.roi-closed{fill:#ffce6b22}.roi-feedback{color:#2c8a68}.agent-region-row{display:flex;align-items:center;justify-content:space-between;margin-top:8px;padding:8px;background:#f4f7fb}.agent-actions{display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap}.mock-room-label{position:absolute;top:12px;left:12px;color:#ffdf89;font-size:11px}.muted{color:#78859a}.notice{background:#f0f5ff;padding:12px}
</style>

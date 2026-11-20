<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { NButton } from 'naive-ui'
import { profileApi, type ProfileAttribute, type SemanticProfile } from './profileApi'
import { useResource, formatDate } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'

const props = defineProps<{ sourceId: string; resolution: string }>()
const { data, loading, error, refresh } = useResource(() => profileApi.read(props.sourceId))
const busy = ref(false)
const actionError = ref('')
const analyzedNotice = ref('')

// 有效期按当前时间动态倒数，打开页面期间持续更新。
const now = ref(Date.now() / 1000)
const ticker = setInterval(() => { now.value = Date.now() / 1000 }, 1000)
onUnmounted(() => clearInterval(ticker))

const keyLabels: Record<string, string> = {
  lighting: '光照', weather: '天气', season_appearance: '季节外观',
  camera_pose: '相机姿态', background_texture: '背景纹理', occlusion: '遮挡',
}
const stateLabels: Record<string, string> = {
  valid: '有效', expired: '已过期（未知）', unknown: '未知', conflict: '来源冲突',
}
const sourceLabels: Record<string, string> = {
  frame: '画面实测', device: '设备字段', language: '语言推断', probe: '低频探针',
}
// 后端存英文标签；界面展示中文。未收录的标签原样显示，不臆造。
const valueLabels: Record<string, string> = {
  bright: '明亮', daylight: '日光', overcast: '阴天', dim: '昏暗', night: '夜晚',
  strong_glare: '强光眩光',
  cloudy: '多云', rain: '雨', snow: '雪', dry: '干燥', foggy: '雾',
  cool: '偏冷', warm: '偏暖', jackets: '着厚外套', light_clothing: '衣着轻薄',
  fixed: '固定机位', ptz: '云台转动',
  dense: '密集', moderate: '适中', sparse: '稀疏',
  none: '无', partial: '部分遮挡', heavy: '严重遮挡',
}

const attributes = computed<ProfileAttribute[]>(() => data.value?.attributes ?? [])

function number(value: number | null | undefined, digits = 2) {
  return value == null ? '—' : value.toFixed(digits)
}
function keyLabel(key: string) { return keyLabels[key] ?? key }
function valueLabel(label: string) { return valueLabels[label] ?? label }
function expired(row: ProfileAttribute) {
  return row.hard_expiry_at != null && row.hard_expiry_at - now.value <= 0
}
function stateLabel(row: ProfileAttribute) {
  return expired(row) ? '已过期（未知）' : stateLabels[row.state] ?? row.state
}
function stateClass(row: ProfileAttribute) {
  return expired(row) ? 'expired' : row.state
}
function expiry(row: ProfileAttribute) {
  if (row.hard_expiry_at == null) return '不过期'
  const seconds = row.hard_expiry_at - now.value
  return seconds <= 0 ? '已过期' : `剩余 ${Math.max(1, Math.round(seconds))} 秒`
}

async function analyze() {
  if (busy.value) return
  busy.value = true
  actionError.value = ''
  analyzedNotice.value = ''
  try {
    const result = await profileApi.analyze(props.sourceId)
    data.value = result.profile as SemanticProfile
    analyzedNotice.value = result.analyzed.length
      ? `已写入动态属性：${result.analyzed.map(keyLabel).join('、')}`
      : '大模型没有确认新的动态属性。'
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '大模型分析失败'
  } finally { busy.value = false }
}

async function removeAttribute(key: string) {
  if (busy.value) return
  busy.value = true
  actionError.value = ''
  try {
    data.value = await profileApi.deleteAttribute(props.sourceId, key)
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '删除属性失败'
  } finally { busy.value = false }
}
</script>

<template>
  <section class="panel profile-panel" aria-label="时效语义画像">
    <div class="panel-title">
      <h2>时效语义画像</h2>
      <small>版本 {{ data?.version ?? 0 }} · 视场 {{ data?.view_version ?? 'v1' }}</small>
    </div>
    <p class="muted">动态属性由大模型分析连续画面生成，带来源、观测时刻与有效期，过期后只转为"未知"，不会被当作相反事实。</p>
    <ErrorBanner :error="actionError" :retryable="false"/>
    <ErrorBanner :error="error" @retry="refresh"/>
    <div class="profile-toolbar">
      <NButton type="primary" size="small" :loading="busy" aria-label="大模型分析画面"
        @click="analyze">大模型分析画面</NButton>
      <small class="muted">截取该视频源连续 3 帧交给已配置的大模型判断；需要先在系统设置中配置大模型接口。</small>
    </div>
    <p v-if="analyzedNotice" class="profile-notice" role="status">{{ analyzedNotice }}</p>
    <p v-if="loading && !data" class="muted" role="status">正在读取画像…</p>
    <template v-else-if="data">
      <h3>固有层</h3>
      <dl class="profile-intrinsic">
        <div><dt>分辨率</dt><dd>{{ resolution || data.intrinsic?.resolution || '尚未获取' }}</dd></div>
      </dl>
      <h3>动态属性</h3>
      <p v-if="!attributes.length" class="muted" role="status">还没有动态属性。画像为空时不会臆造任何场景条件。</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>属性</th><th>取值</th><th>来源</th><th>状态</th><th>强度</th><th>有效期</th><th></th></tr></thead>
          <tbody><tr v-for="row in attributes" :key="row.key">
            <td>{{ keyLabel(row.key) }}</td>
            <td class="wrap">{{ valueLabel(String(row.value?.label ?? '—')) }}</td>
            <td>{{ sourceLabels[row.source_kind] ?? row.source_kind }}</td>
            <td><span :class="['profile-state', stateClass(row)]">{{ stateLabel(row) }}</span></td>
            <td>{{ number(row.strength) }}</td>
            <td>{{ expiry(row) }}</td>
            <td><NButton text type="primary" size="small" :loading="busy"
              @click="removeAttribute(row.key)">删除</NButton></td>
          </tr></tbody>
        </table>
      </div>
      <p class="muted">最近更新 {{ formatDate(data.updated_at) }}</p>
    </template>
  </section>
</template>

<style scoped>
.profile-panel { margin-top: 0; }
.profile-toolbar { display: flex; gap: 8px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
.profile-notice { margin: 4px 0; font-size: 12px; color: #18a058; }
.profile-intrinsic { margin: 4px 0 0; display: flex; gap: 24px; font-size: 13px; }
.profile-intrinsic dt { color: #667085; font-size: 12px; }
.profile-intrinsic dd { margin: 2px 0 0; font-weight: 600; }
.profile-state.valid { color: #18a058; }
.profile-state.expired { color: #d03050; }
.profile-state.conflict { color: #f0a020; }
h3 { margin: 14px 0 6px; font-size: 13px; }
</style>

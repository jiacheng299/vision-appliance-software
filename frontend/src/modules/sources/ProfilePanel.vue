<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { NButton, NInput, NInputNumber, NSelect } from 'naive-ui'
import { INTRINSIC_KEYS, profileApi, type AttributeDraft, type AttributeSource,
  type ProfileAttribute, type SemanticProfile } from './profileApi'
import { useResource } from '../../shared/ui/resource'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'

const props = defineProps<{ sourceId: string }>()
const { data, loading, error, refresh } = useResource(() => profileApi.read(props.sourceId))
const busy = ref('')
const actionError = ref('')
const intrinsic = reactive<Record<string, string>>({})

watch(data, value => {
  if (!value) return
  for (const key of INTRINSIC_KEYS) intrinsic[key] = String(value.intrinsic?.[key] ?? '')
})

const draft = reactive<{ key: string; label: string; sourceKind: AttributeSource
  confidence: number; tau: number | null; expiresIn: number | null }>({
  key: '', label: '', sourceKind: 'frame', confidence: 0.8, tau: 120, expiresIn: 600,
})
const sourceOptions: { label: string; value: AttributeSource }[] = [
  { label: '画面实测', value: 'frame' },
  { label: '设备字段', value: 'device' },
  { label: '语言推断', value: 'language' },
  { label: '低频探针', value: 'probe' },
]
const stateLabels: Record<string, string> = {
  valid: '有效', expired: '已过期（未知）', unknown: '未知', conflict: '来源冲突',
}
const keyPattern = /^[A-Za-z0-9_.-]{1,64}$/

const attributes = computed<ProfileAttribute[]>(() => data.value?.attributes ?? [])
const canSubmit = computed(() => keyPattern.test(draft.key) && draft.label.trim().length > 0)

function number(value: number | null | undefined, digits = 2) {
  return value == null ? '—' : value.toFixed(digits)
}
function expiry(row: ProfileAttribute) {
  if (row.hard_expiry_at == null) return '不过期'
  const seconds = row.hard_expiry_at - Number(data.value?.evaluated_at ?? 0)
  return seconds <= 0 ? '已过期' : `剩余 ${Math.round(seconds)} 秒`
}

async function saveIntrinsic() {
  if (busy.value) return
  busy.value = 'intrinsic'; actionError.value = ''
  try {
    const values: Record<string, string> = {}
    for (const key of INTRINSIC_KEYS) if (intrinsic[key]?.trim()) values[key] = intrinsic[key].trim()
    await profileApi.updateIntrinsic(props.sourceId, values)
    await refresh()
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '保存固有层失败'
  } finally { busy.value = '' }
}

async function addAttribute() {
  if (!canSubmit.value || busy.value) return
  busy.value = 'attribute'; actionError.value = ''
  const body: AttributeDraft = { value: draft.label.trim(), source_kind: draft.sourceKind,
    confidence: draft.confidence, tau_seconds: draft.tau, expires_in_seconds: draft.expiresIn }
  try {
    await profileApi.upsertAttribute(props.sourceId, draft.key.trim(), body)
    draft.key = ''; draft.label = ''
    await refresh()
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '写入属性失败'
  } finally { busy.value = '' }
}

async function removeAttribute(key: string) {
  if (busy.value) return
  busy.value = `remove:${key}`; actionError.value = ''
  try {
    await profileApi.deleteAttribute(props.sourceId, key)
    await refresh()
  } catch (problem) {
    actionError.value = problem instanceof Error ? problem.message : '删除属性失败'
  } finally { busy.value = '' }
}
</script>

<template>
  <section class="panel profile-panel" aria-label="时效语义画像">
    <div class="panel-title">
      <h2>时效语义画像</h2>
      <small>版本 {{ data?.version ?? 0 }} · 视场 {{ data?.view_version ?? 'v1' }}</small>
    </div>
    <p class="muted">固有层不随时间变化；动态属性必须带来源、观测时刻与有效期，过期后只转为"未知"，不会被当作相反事实。</p>
    <ErrorBanner :error="actionError" :retryable="false"/>
    <ErrorBanner :error="error" @retry="refresh"/>
    <p v-if="loading && !data" class="muted" role="status">正在读取画像…</p>
    <template v-else-if="data">
      <h3>固有层</h3>
      <div class="profile-grid">
        <label v-for="key in INTRINSIC_KEYS" :key="key" class="profile-field">
          <span>{{ key }}</span>
          <NInput v-model:value="intrinsic[key]" :placeholder="key === 'resolution' ? '1920x1080' : ''" size="small"/>
        </label>
      </div>
      <div class="toolbar"><NButton size="small" :loading="busy === 'intrinsic'" @click="saveIntrinsic">保存固有层</NButton></div>

      <h3>动态属性</h3>
      <p v-if="!attributes.length" class="muted" role="status">还没有动态属性。画像为空时不会臆造任何场景条件。</p>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>属性</th><th>取值</th><th>来源</th><th>状态</th><th>强度</th><th>有效期</th><th></th></tr></thead>
          <tbody><tr v-for="row in attributes" :key="row.key">
            <td>{{ row.key }}</td>
            <td class="wrap">{{ String(row.value?.label ?? '—') }}</td>
            <td>{{ sourceOptions.find(option => option.value === row.source_kind)?.label ?? row.source_kind }}</td>
            <td><span :class="['profile-state', row.state]">{{ stateLabels[row.state] ?? row.state }}</span></td>
            <td>{{ number(row.strength) }}</td>
            <td>{{ expiry(row) }}</td>
            <td><NButton text type="primary" size="small" :loading="busy === `remove:${row.key}`"
              @click="removeAttribute(row.key)">删除</NButton></td>
          </tr></tbody>
        </table>
      </div>

      <h3>写入一项属性</h3>
      <div class="profile-grid">
        <label class="profile-field"><span>属性名</span>
          <NInput v-model:value="draft.key" placeholder="lighting" size="small"/></label>
        <label class="profile-field"><span>取值</span>
          <NInput v-model:value="draft.label" placeholder="strong_glare" size="small"/></label>
        <label class="profile-field"><span>来源</span>
          <NSelect v-model:value="draft.sourceKind" :options="sourceOptions" size="small"/></label>
        <label class="profile-field"><span>置信度</span>
          <NInputNumber v-model:value="draft.confidence" :min="0" :max="1" :step="0.05" size="small"/></label>
        <label class="profile-field"><span>衰减常数（秒）</span>
          <NInputNumber v-model:value="draft.tau" :min="1" size="small"/></label>
        <label class="profile-field"><span>有效期（秒）</span>
          <NInputNumber v-model:value="draft.expiresIn" :min="1" size="small"/></label>
      </div>
      <div class="toolbar">
        <NButton type="primary" size="small" :disabled="!canSubmit" :loading="busy === 'attribute'"
          @click="addAttribute">写入属性</NButton>
        <small v-if="!canSubmit" class="muted">属性名需为字母/数字/下划线/点/短横线，且取值不能为空。</small>
      </div>
    </template>
  </section>
</template>

<style scoped>
.profile-panel { margin-top: 16px; }
.profile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; margin: 8px 0; }
.profile-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.profile-field span { opacity: .75; }
.profile-state.valid { color: #18a058; }
.profile-state.expired { color: #d03050; }
.profile-state.conflict { color: #f0a020; }
.toolbar { display: flex; gap: 8px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
h3 { margin: 14px 0 6px; font-size: 13px; }
</style>

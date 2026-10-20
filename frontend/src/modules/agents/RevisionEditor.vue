<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInput, NInputNumber, NSelect } from 'naive-ui'
import { agentApi, type Revision } from './api'
import { copyConfig, draftError, newChannel } from './draft'
import { humanError } from '../../shared/api/client'
import type { Source } from '../../shared/api/types'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import RegionEditor from './RegionEditor.vue'
const props = defineProps<{ revision: Revision; sources: Source[] }>()
const emit = defineEmits<{ close: []; saved: [revision: Revision]; dirty: [dirty: boolean]; saving: [saving: boolean] }>()
const config = ref(copyConfig(props.revision.config)), error = ref(''), saving = ref(false)
const pendingRegions = ref<Record<string, boolean>>({})
const pending = computed(() => (config.value.channels ?? []).some(channel => pendingRegions.value[channel.channel_id ?? '']))
const dirty = computed(() => pending.value || JSON.stringify(config.value) !== JSON.stringify(props.revision.config))
watch(dirty, value => emit('dirty', value), { immediate: true })
const options = computed(() => props.sources.map(s => ({ label: s.name, value: s.id })))
function close() { if (!saving.value && (!dirty.value || window.confirm('尚有未保存的配置，确定放弃这些修改？'))) emit('close') }
function changeSource(index: number, sourceId: string | null) {
  const channel = config.value.channels?.[index]
  if (!channel) return
  pendingRegions.value[channel.channel_id ?? ''] = false
  channel.source_id = sourceId; channel.regions = []; channel.start_media_ms = null; channel.end_media_ms = null
}
async function save() {
  if (saving.value) return
  if (pending.value) { error.value = '还有正在绘制的区域，请先保存区域或撤销全部边界点，再保存草稿。'; return }
  error.value = draftError(config.value)
  if (error.value) return
  saving.value = true; emit('saving', true)
  try { const result = await agentApi.save(props.revision, config.value); emit('dirty', false); emit('saved', result) }
  catch (e) { error.value = humanError(e) }
  finally { saving.value = false; emit('saving', false) }
}
</script>
<template>
  <NDrawer :show="true" :width="760" :mask-closable="false" :close-on-esc="false" @update:show="close">
    <NDrawerContent :title="`编辑配置 v${revision.revision_no}`" closable @close="close">
      <p class="notice">保存只更新这份草稿，不会启动或重启监测。视频源和需求可以先留空，之后补齐。</p>
      <ErrorBanner :error="error" :retryable="false"/>
      <fieldset :disabled="saving" class="agent-editor-fields">
      <div v-for="(channel, index) in config.channels" :key="channel.channel_id" class="agent-channel-form">
        <div class="panel-title"><h3>第 {{index + 1}} 路监测</h3><NButton size="small" :disabled="saving" @click="config.channels?.splice(index, 1)">移除通道</NButton></div>
        <div class="field"><label :for="`channel-name-${index}`">通道名称</label><NInput :input-props="{ id: `channel-name-${index}` }" v-model:value="channel.name" :maxlength="160" :disabled="saving"/></div>
        <div class="field"><label :id="`source-label-${index}`">视频源</label><NSelect :aria-labelledby="`source-label-${index}`" :value="channel.source_id" :options="options" :disabled="saving" clearable placeholder="选择已保存的录像或摄像头" @update:value="changeSource(index, $event)"/><p v-if="channel.source_id && !sources.some(s => s.id === channel.source_id)" class="hint">原视频源已归档或当前不可用。原引用保留，可重新选择。</p></div>
        <div class="field"><label :for="`requirement-${index}`">希望监测什么</label><NInput :input-props="{ id: `requirement-${index}` }" v-model:value="channel.requirement_text" type="textarea" :maxlength="8000" :disabled="saving" placeholder="例如：有人在指定区域停留超过 30 秒时报警"/></div>
        <div class="field-grid"><div class="field"><label :for="`target-${index}`">监测对象（待校验）</label><NInput :input-props="{ id: `target-${index}` }" v-model:value="channel.target" :maxlength="160" :disabled="saving" placeholder="例如：人员"/></div><div class="field"><label :for="`rule-${index}`">触发规则（待校验）</label><NInput :input-props="{ id: `rule-${index}` }" v-model:value="channel.rule" :maxlength="160" :disabled="saving" placeholder="例如：区域滞留"/></div></div>
        <div class="field"><label>持续时长（秒，可暂不填写）</label><NInputNumber v-model:value="channel.duration_seconds" :min="1" :max="86400" :precision="0" :disabled="saving" aria-label="持续时长（秒）"/></div>
        <template v-if="sources.find(s => s.id === channel.source_id)?.kind === 'file'">
          <div class="field-grid"><div class="field"><label>录像开始位置（秒）</label><NInputNumber :value="channel.start_media_ms == null ? null : channel.start_media_ms/1000" :min="0" :precision="3" :disabled="saving" aria-label="录像开始位置（秒）" @update:value="channel.start_media_ms = $event == null ? null : Math.round($event * 1000)"/></div><div class="field"><label>录像结束位置（秒）</label><NInputNumber :value="channel.end_media_ms == null ? null : channel.end_media_ms/1000" :min="0" :precision="3" :disabled="saving" aria-label="录像结束位置（秒）" @update:value="channel.end_media_ms = $event == null ? null : Math.round($event * 1000)"/></div></div>
        </template>
        <div class="field"><label>监测区域</label><RegionEditor :key="channel.source_id ?? 'none'" :regions="channel.regions ?? []" :source="sources.find(s => s.id === channel.source_id)" :disabled="saving" @pending="pendingRegions[channel.channel_id ?? ''] = $event" @change="channel.regions = $event"/></div>
        <p class="muted">{{channel.capability_ref ? '已有模型版本引用将保留。模型服务接入前暂不能更换或验证。' : '模型服务尚未接入，暂不能选择模型。填写规则不代表系统已经支持此能力。'}}</p>
      </div>
      <NButton dashed block :disabled="saving || (config.channels?.length ?? 0) >= 16" @click="config.channels?.push(newChannel())">添加一路监测</NButton>
      </fieldset>
      <template #footer><div class="agent-actions"><NButton :disabled="saving" @click="close">取消</NButton><NButton type="primary" :loading="saving" :disabled="!dirty" @click="save">保存草稿</NButton></div></template>
    </NDrawerContent>
  </NDrawer>
</template>

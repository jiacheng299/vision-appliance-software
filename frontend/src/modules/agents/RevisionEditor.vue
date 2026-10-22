<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInput, NInputNumber, NSelect } from 'naive-ui'
import { agentApi, type Revision, type CapabilityCatalog, type Channel } from './api'
import { agentError } from './state'
import { copyConfig, draftError, newChannel } from './draft'
import type { Source } from '../../shared/api/types'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import RegionEditor from './RegionEditor.vue'
const props = defineProps<{ revision: Revision; sources: Source[] }>()
const emit = defineEmits<{ close: []; saved: [revision: Revision]; dirty: [dirty: boolean]; saving: [saving: boolean] }>()
const config = ref(copyConfig(props.revision.config)), error = ref(''), saving = ref(false)
const catalog=ref<CapabilityCatalog|null>(null),catalogError=ref('')
async function loadCatalog(){try{catalog.value=await agentApi.catalog();catalogError.value=''}catch(e){catalogError.value=agentError(e)}}
void loadCatalog()
const refKey=(value:unknown)=>JSON.stringify(value)
function capability(channel:Channel){return catalog.value?.items.find(item=>refKey(item.reference)===refKey(channel.capability_ref))}
function selectCapability(channel:Channel,value:string|null){channel.capability_ref=catalog.value?.items.find(item=>refKey(item.reference)===value)?.reference??null}
const businessLabels:Record<string,string>={person:'人员',vehicle:'车辆',intrusion:'区域入侵',dwell:'区域滞留',absence:'人员在岗'}
const businessLabel=(value:string)=>businessLabels[value]??value
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
  catch (e) { error.value = agentError(e) }
  finally { saving.value = false; emit('saving', false) }
}
</script>
<template>
  <NDrawer :show="true" :width="760" :mask-closable="false" :close-on-esc="false" @update:show="close">
    <NDrawerContent :title="`编辑配置 v${revision.revision_no}`" closable @close="close">
      <p class="notice">保存只更新这份草稿，不会启动或重启监测。视频源和需求可以先留空，之后补齐。</p>
      <ErrorBanner :error="error" :retryable="false"/>
      <ErrorBanner :error="catalogError" @retry="loadCatalog"/>
      <fieldset :disabled="saving" class="agent-editor-fields">
      <div v-for="(channel, index) in config.channels" :key="channel.channel_id" class="agent-channel-form">
        <div class="panel-title"><h3>第 {{index + 1}} 路监测</h3><NButton size="small" :disabled="saving" @click="config.channels?.splice(index, 1)">移除通道</NButton></div>
        <div class="field"><label :for="`channel-name-${index}`">通道名称</label><NInput :input-props="{ id: `channel-name-${index}` }" v-model:value="channel.name" :maxlength="160" :disabled="saving"/></div>
        <div class="field"><label :id="`source-label-${index}`">视频源</label><NSelect :aria-labelledby="`source-label-${index}`" :value="channel.source_id" :options="options" :disabled="saving" clearable placeholder="选择已保存的录像或摄像头" @update:value="changeSource(index, $event)"/><p v-if="channel.source_id && !sources.some(s => s.id === channel.source_id)" class="hint">原视频源已归档或当前不可用。原引用保留，可重新选择。</p></div>
        <div class="field"><label :for="`requirement-${index}`">希望监测什么</label><NInput :input-props="{ id: `requirement-${index}` }" v-model:value="channel.requirement_text" type="textarea" :maxlength="8000" :disabled="saving" placeholder="例如：有人在指定区域停留超过 30 秒时报警"/></div>
        <div class="field"><label>模型与绑定模板（来自模型服务）</label><NSelect :value="channel.capability_ref?refKey(channel.capability_ref):null" :options="catalog?.items.map(item=>({label:`${item.name} · ${item.reference.model_version}`,value:refKey(item.reference)}))??[]" :disabled="saving||!!catalogError" clearable placeholder="选择经过校验的能力" aria-label="选择模型与模板" @update:value="selectCapability(channel,$event)"/><p v-if="channel.capability_ref&&!capability(channel)" class="hint">当前引用暂不在可用目录中，原引用保留，但必须重新校验后才能发布。</p></div>
        <div v-if="capability(channel)" class="field-grid"><div class="field"><label>从模型声明选择目标</label><NSelect v-model:value="channel.target" :options="capability(channel)!.targets.map(value=>({label:businessLabel(value),value}))" :disabled="saving" aria-label="模型支持的监测对象"/></div><div class="field"><label>从模板声明选择规则</label><NSelect v-model:value="channel.rule" :options="capability(channel)!.rules.map(value=>({label:businessLabel(value),value}))" :disabled="saving" aria-label="模板支持的规则"/></div></div>
        <div class="field-grid"><div class="field"><label :for="`target-${index}`">监测对象（待校验）</label><NInput :input-props="{ id: `target-${index}` }" v-model:value="channel.target" :maxlength="160" :disabled="saving" placeholder="例如：人员"/></div><div class="field"><label :for="`rule-${index}`">触发规则（待校验）</label><NInput :input-props="{ id: `rule-${index}` }" v-model:value="channel.rule" :maxlength="160" :disabled="saving" placeholder="例如：区域滞留"/></div></div>
        <div class="field"><label>持续时长（秒，可暂不填写）</label><NInputNumber v-model:value="channel.duration_seconds" :min="1" :max="86400" :precision="0" :disabled="saving" aria-label="持续时长（秒）"/></div>
        <template v-if="sources.find(s => s.id === channel.source_id)?.kind === 'file'">
          <div class="field-grid"><div class="field"><label>录像开始位置（秒）</label><NInputNumber :value="channel.start_media_ms == null ? null : channel.start_media_ms/1000" :min="0" :precision="3" :disabled="saving" aria-label="录像开始位置（秒）" @update:value="channel.start_media_ms = $event == null ? null : Math.round($event * 1000)"/></div><div class="field"><label>录像结束位置（秒）</label><NInputNumber :value="channel.end_media_ms == null ? null : channel.end_media_ms/1000" :min="0" :precision="3" :disabled="saving" aria-label="录像结束位置（秒）" @update:value="channel.end_media_ms = $event == null ? null : Math.round($event * 1000)"/></div></div>
        </template>
        <div class="field"><label>监测区域</label><RegionEditor :key="channel.source_id ?? 'none'" :regions="channel.regions ?? []" :source="sources.find(s => s.id === channel.source_id)" :disabled="saving" :demo="catalog?.data_origin==='mock'" @pending="pendingRegions[channel.channel_id ?? ''] = $event" @change="channel.regions = $event"/></div>
        <p class="muted">{{catalog ? '能力字段来自模型服务。更换模型不会自动删减原始需求，保存后必须重新验证。' : '能力目录暂不可用，原引用保留。填写规则不代表系统已支持此能力。'}}</p>
      </div>
      <NButton dashed block :disabled="saving || (config.channels?.length ?? 0) >= 16" @click="config.channels?.push(newChannel())">添加一路监测</NButton>
      </fieldset>
      <template #footer><div class="agent-actions"><NButton :disabled="saving" @click="close">取消</NButton><NButton type="primary" :loading="saving" :disabled="!dirty" @click="save">保存草稿</NButton></div></template>
    </NDrawerContent>
  </NDrawer>
</template>

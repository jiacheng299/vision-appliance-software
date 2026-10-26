<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInput, NInputNumber, NSelect } from 'naive-ui'
import { agentApi, type Revision, type CapabilityCatalog, type Channel } from './api'
import { agentError } from './state'
import { copyConfig, draftError, newChannel } from './draft'
import type { Source } from '../../shared/api/types'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import RegionEditor from './RegionEditor.vue'
import { channelSources, setChannelSources, MAX_CHANNEL_SOURCES } from './channelSources'
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
const pending = computed(() => (config.value.channels ?? []).some(channel => Object.entries(pendingRegions.value).some(([key,value])=>key.startsWith(`${channel.channel_id}:`)&&value)))
const dirty = computed(() => pending.value || JSON.stringify(config.value) !== JSON.stringify(props.revision.config))
watch(dirty, value => emit('dirty', value), { immediate: true })
const options = computed(() => props.sources.map(s => ({ label: s.name, value: s.id })))
function close() { if (!saving.value && (!dirty.value || window.confirm('尚有未保存的配置，确定放弃这些修改？'))) emit('close') }
function changeSources(index:number,values:string[]|string){
  const channel=config.value.channels?.[index];if(!channel)return
  const ids=typeof values==='string'?[values]:values
  if(ids.length>MAX_CHANNEL_SOURCES){error.value='一个通道最多选择16个视频源。';return}
  const removed=channelSources(channel).filter(b=>!ids.includes(b.source_id))
  if(removed.some(b=>pendingRegions.value[`${channel.channel_id}:${b.source_id}`])&&!window.confirm('移除视频源将放弃其正在绘制的区域，确定继续？'))return
  for(const b of removed)delete pendingRegions.value[`${channel.channel_id}:${b.source_id}`]
  setChannelSources(channel,ids)
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
  <NDrawer :show="true" :width="760" :mask-closable="!saving" :close-on-esc="!saving" @update:show="close">
    <NDrawerContent :title="`编辑配置 v${revision.revision_no}`" closable @close="close">
      <p class="notice">保存仅更新当前草稿，不启动或重启监测。草稿允许暂缺视频源与监测需求，发布前须完成配置与验证。</p>
      <ErrorBanner :error="error" :retryable="false"/>
      <ErrorBanner :error="catalogError" @retry="loadCatalog"/>
      <fieldset :disabled="saving" class="agent-editor-fields">
      <div v-for="(channel, index) in config.channels" :key="channel.channel_id" class="agent-channel-form">
        <div class="panel-title"><h3>通道 {{index + 1}}</h3><NButton size="small" :disabled="saving" @click="config.channels?.splice(index, 1)">移除通道</NButton></div>
        <div class="field"><label :for="`channel-name-${index}`">通道名称</label><NInput :input-props="{ id: `channel-name-${index}` }" v-model:value="channel.name" :maxlength="160" :disabled="saving"/></div>
        <div class="field"><label :id="`source-label-${index}`">通道内视频源（可多选）</label><NSelect multiple :aria-labelledby="`source-label-${index}`" :value="channelSources(channel).map(b=>b.source_id)" :options="options" :disabled="saving" clearable placeholder="选择监控直播或录像，可混合选择" @update:value="changeSources(index, $event)"/><p class="hint">本通道的所有视频共用下方需求、模型和规则，统一启停；区域与录像区间在各视频中分别设置。</p></div>
        <div class="field"><label :for="`requirement-${index}`">监测需求</label><NInput :input-props="{ id: `requirement-${index}` }" v-model:value="channel.requirement_text" type="textarea" :maxlength="8000" :disabled="saving" placeholder="例如：有人在指定区域停留超过 30 秒时报警"/></div>
        <div class="field"><label>分析模型与规则模板</label><NSelect :value="channel.capability_ref?refKey(channel.capability_ref):null" :options="catalog?.items.map(item=>({label:`${item.name} · ${item.reference.model_version}`,value:refKey(item.reference)}))??[]" :disabled="saving||!!catalogError" clearable placeholder="选择分析模型及配套模板" aria-label="选择模型与模板" @update:value="selectCapability(channel,$event)"/><p v-if="channel.capability_ref&&!capability(channel)" class="hint">当前引用暂不在可用目录中，原引用保留，但必须重新校验后才能发布。</p></div>
        <div v-if="capability(channel)" class="field-grid"><div class="field"><label>从模型声明选择目标</label><NSelect v-model:value="channel.target" :options="capability(channel)!.targets.map(value=>({label:businessLabel(value),value}))" :disabled="saving" aria-label="模型支持的监测对象"/></div><div class="field"><label>从模板声明选择规则</label><NSelect v-model:value="channel.rule" :options="capability(channel)!.rules.map(value=>({label:businessLabel(value),value}))" :disabled="saving" aria-label="模板支持的规则"/></div></div>
        <div class="field-grid"><div class="field"><label :for="`target-${index}`">监测对象（待校验）</label><NInput :input-props="{ id: `target-${index}` }" v-model:value="channel.target" :maxlength="160" :disabled="saving" placeholder="例如：人员"/></div><div class="field"><label :for="`rule-${index}`">触发规则（待校验）</label><NInput :input-props="{ id: `rule-${index}` }" v-model:value="channel.rule" :maxlength="160" :disabled="saving" placeholder="例如：区域滞留"/></div></div>
        <div class="field"><label>触发条件持续时长（秒，选填）</label><NInputNumber v-model:value="channel.duration_seconds" :min="1" :max="86400" :precision="0" :disabled="saving" aria-label="持续时长（秒）"/></div>
        <section v-for="binding in channelSources(channel)" :key="binding.source_id" class="channel-source-editor">
          <h4>{{sources.find(s=>s.id===binding.source_id)?.name??binding.source_id}}</h4><p v-if="!sources.some(s=>s.id===binding.source_id)" class="hint">原视频源已归档或不可用，历史引用保留，可从上方取消选择。</p>
          <template v-if="sources.find(s=>s.id===binding.source_id)?.kind==='file'"><div class="field-grid"><div class="field"><label>录像开始位置（秒）</label><NInputNumber :value="binding.start_media_ms==null?null:binding.start_media_ms/1000" :min="0" :precision="3" :disabled="saving" aria-label="录像开始位置（秒）" @update:value="binding.start_media_ms=$event==null?null:Math.round($event*1000)"/></div><div class="field"><label>录像结束位置（秒）</label><NInputNumber :value="binding.end_media_ms==null?null:binding.end_media_ms/1000" :min="0" :precision="3" :disabled="saving" aria-label="录像结束位置（秒）" @update:value="binding.end_media_ms=$event==null?null:Math.round($event*1000)"/></div></div></template>
          <div class="field"><label>此视频的监测区域</label><RegionEditor :regions="binding.regions??[]" :source="sources.find(s=>s.id===binding.source_id)" :disabled="saving" :demo="catalog?.data_origin==='mock'" @pending="pendingRegions[`${channel.channel_id}:${binding.source_id}`]=$event" @change="binding.regions=$event"/></div>
        </section>
        <p class="muted">{{catalog ? '能力字段来自模型服务。更换模型不会自动删减原始需求，保存后必须重新验证。' : '能力目录暂不可用，原引用保留。填写规则不代表系统已支持此能力。'}}</p>
      </div>
      <NButton dashed block :disabled="saving || (config.channels?.length ?? 0) >= 16" @click="config.channels?.push(newChannel())">添加通道</NButton>
      </fieldset>
      <template #footer><div class="agent-actions"><NButton :disabled="saving" @click="close">取消</NButton><NButton type="primary" :loading="saving" :disabled="!dirty" @click="save">保存草稿</NButton></div></template>
    </NDrawerContent>
  </NDrawer>
</template>

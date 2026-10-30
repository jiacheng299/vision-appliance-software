<script setup lang="ts">
import { computed } from 'vue'
import { Info } from 'lucide-vue-next'
import ParameterFields from '../agents/ParameterFields.vue'
import type { ParameterDefinition,ParameterSetting } from '../agents/templatesApi'
import type { CapabilityCatalog } from '../agents/api'
const props=defineProps<{settings:ParameterSetting[];definitions:ParameterDefinition[];model?:CapabilityCatalog['items'][number];sourceCount:number;rule:string;disabled?:boolean}>()
const emit=defineEmits<{'update:settings':[settings:ParameterSetting[]]}>()
const primary=new Set(['target','rule','duration_seconds','confidence_threshold','min_count','alarm_interval_seconds'])
const basic=computed(()=>props.settings.filter(s=>primary.has(s.key)||s.required))
const advanced=computed(()=>props.settings.filter(s=>!primary.has(s.key)&&!s.required))
function update(values:ParameterSetting[]){
  const changes=new Map(values.map(v=>[v.key,v]))
  emit('update:settings',props.settings.map(s=>changes.has(s.key)?{...s,value:changes.get(s.key)!.value}:s))
}
</script>
<template>
  <aside class="tc-conditions" aria-label="共用检测条件">
    <h2>共用检测条件</h2><p class="tc-conditions-subtitle">应用于全部 {{sourceCount}} 路视频</p>
    <ParameterFields :settings="basic" :definitions="definitions" :model="model" :disabled="disabled" @update:settings="update"/>
    <div v-if="rule==='absence'" class="tc-restoration"><span>恢复确认时长</span><strong>与缺岗确认时长一致</strong></div>
    <details v-if="advanced.length" class="tc-advanced"><summary>高级参数 <span>{{advanced.length}} 项</span></summary><ParameterFields :settings="advanced" :definitions="definitions" :model="model" :disabled="disabled" @update:settings="update"/></details>
    <p class="tc-conditions-note"><Info :size="16"/><span>共用规则，区域与报警独立。<small>每路视频分别计时和生成报警事件。</small></span></p>
  </aside>
</template>
<style scoped>
.tc-conditions{background:#fff;border:1px solid #e4eaf3;border-radius:9px;padding:18px;min-width:0}.tc-conditions h2{font-size:16px;color:#263951;margin-bottom:6px}.tc-conditions-subtitle{font-size:11px;color:#8492a8;margin-bottom:14px}.tc-conditions :deep(.parameter-row){padding:12px 0;border:0;border-top:1px solid #edf1f6;background:transparent;margin:0;border-radius:0}.tc-conditions :deep(.parameter-heading){margin-bottom:7px;gap:5px}.tc-conditions :deep(.parameter-heading label){font-size:12px;line-height:1.7}.tc-conditions :deep(.hint){font-size:10px;line-height:1.6;color:#8d9bb0;margin-top:6px}.tc-conditions :deep(.n-input-number){width:100%}.tc-restoration{display:grid;gap:8px;font-size:12px;padding:13px 0;color:#6b7d96;border-top:1px solid #edf1f6}.tc-restoration strong{font-size:11px;font-weight:400;background:#f4f6fa;padding:9px;color:#8998ad;border-radius:5px}.tc-advanced{margin-top:15px;border:1px solid #e4eaf3;border-radius:5px;padding:11px}.tc-advanced summary{font-size:12px;cursor:pointer;color:#4f647f}.tc-advanced summary span{color:#8d9bb0;margin-left:7px;font-size:11px}.tc-conditions-note{display:flex;align-items:flex-start;gap:8px;background:#eff5ff;color:#4279d9;font-size:11px;line-height:1.8;padding:12px;border-radius:5px;margin-top:18px}.tc-conditions-note svg{flex:none;margin-top:3px}.tc-conditions-note small{display:block;color:#8b9bb3;font-size:10px}
</style>

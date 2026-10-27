<script setup lang="ts">
import { computed } from 'vue'
import { NCheckbox,NInput,NInputNumber,NSelect } from 'naive-ui'
import type { ParameterDefinition,ParameterSetting } from './templatesApi'
import type { CapabilityCatalog } from './api'
const props=withDefaults(defineProps<{settings:ParameterSetting[];definitions:ParameterDefinition[];model?:CapabilityCatalog['items'][number];selectable?:boolean;disabled?:boolean}>(),{selectable:false,disabled:false})
const emit=defineEmits<{'update:settings':[value:ParameterSetting[]]}>()
const definition=(key:string)=>props.definitions.find(d=>d.key===key)
const choices=computed(()=>props.definitions.map(d=>({label:`${d.category} · ${d.label}`,value:d.key})))
function choose(keys:string[]){const old=new Map(props.settings.map(s=>[s.key,s]));emit('update:settings',keys.map(key=>old.get(key)??{key,value:null,required:false}))}
function setValue(index:number,value:ParameterSetting['value']){emit('update:settings',props.settings.map((s,i)=>i===index?{...s,value}:s))}
function required(index:number,value:boolean){emit('update:settings',props.settings.map((s,i)=>i===index?{...s,required:value}:s))}
function options(d:ParameterDefinition){
  const declared=d.key==='target'?props.model?.targets:d.key==='rule'?props.model?.rules:undefined
  return declared?.length?declared.map(value=>({value,label:d.options?.find(o=>o.value===value)?.label??value})):d.options??[]
}
function unsupported(key:string){return props.model&&!['target','rule','duration_seconds'].includes(key)&&!props.model.parameter_keys?.includes(key)}
</script>
<template>
  <div class="parameter-fields">
    <div v-if="selectable" class="field"><label>选择配置项</label><NSelect multiple filterable :value="settings.map(s=>s.key)" :options="choices" :disabled="disabled" placeholder="从配置项池中选择，可多选" aria-label="选择模板配置项" @update:value="choose"/><p class="hint">配置项池由开发者维护。可选择所需项目、设置默认值，并指定任务创建时是否必填。</p></div>
    <div v-if="!settings.length" class="parameter-empty">{{selectable?'尚未选择可选配置项。模型默认检测对象和规则将在发布时确认。':'此模板未开放额外配置项，任务采用模板的默认条件。'}}</div>
    <article v-for="(setting,index) in settings" :key="setting.key" class="parameter-row">
      <template v-if="definition(setting.key)">
        <div class="parameter-heading"><label :id="`parameter-${setting.key}`">{{definition(setting.key)!.label}}<span v-if="definition(setting.key)!.unit">（{{definition(setting.key)!.unit}}）</span><small v-if="setting.required" class="required-label">必填</small></label><NCheckbox v-if="selectable" :checked="setting.required" :disabled="disabled" @update:checked="required(index,$event)">任务必填</NCheckbox></div>
        <NSelect v-if="definition(setting.key)!.type==='select'" :value="typeof setting.value==='string'?setting.value:null" :options="options(definition(setting.key)!)" :disabled="disabled" clearable :aria-labelledby="`parameter-${setting.key}`" :aria-label="definition(setting.key)!.label" placeholder="请选择" @update:value="setValue(index,$event)"/>
        <NInputNumber v-else-if="['number','integer'].includes(definition(setting.key)!.type)" :value="typeof setting.value==='number'?setting.value:null" :min="definition(setting.key)!.minimum??undefined" :max="definition(setting.key)!.maximum??undefined" :step="definition(setting.key)!.step" :precision="definition(setting.key)!.type==='integer'?0:3" :disabled="disabled" :aria-label="definition(setting.key)!.label" @update:value="setValue(index,$event)"/>
        <NSelect v-else-if="definition(setting.key)!.type==='boolean'" :value="typeof setting.value==='boolean'?String(setting.value):null" :options="[{label:'启用',value:'true'},{label:'不启用',value:'false'}]" :disabled="disabled" clearable :aria-label="definition(setting.key)!.label" placeholder="请选择" @update:value="setValue(index,$event==null?null:$event==='true')"/>
        <NInput v-else :value="typeof setting.value==='string'?setting.value:''" :disabled="disabled" :maxlength="11" :aria-label="definition(setting.key)!.label" placeholder="08:00-18:00" @update:value="setValue(index,$event||null)"/>
        <p class="hint">{{definition(setting.key)!.description}}</p><p v-if="unsupported(setting.key)" class="parameter-support">所选模型尚未声明支持此配置项，执行前必须通过能力验证。</p>
      </template><p v-else class="error-banner">未知配置项 {{setting.key}}，请联系开发者核对目录版本。</p>
    </article>
  </div>
</template>

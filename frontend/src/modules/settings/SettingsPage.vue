<script setup lang="ts">
import { computed,onUnmounted,reactive,ref,watch } from 'vue'
import { onBeforeRouteLeave,onBeforeRouteUpdate,useRoute } from 'vue-router'
import { NButton,NCheckbox,NCheckboxGroup,NInputNumber,useMessage } from 'naive-ui'
import { api } from '../../shared/api'
import type { Settings,SettingsSection } from '../../shared/api/types'
import { humanError } from '../../shared/api/client'
import { useResource } from '../../shared/ui/resource'
import { validateSettings } from './validation'
import { settingsPayload } from './form'
import Icon from '../../shared/ui/Icon.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
const route=useRoute(),message=useMessage()
const sections=[{key:'general',label:'基本设置',icon:'settings',description:'探索下一阶段的智能验证能力'},{key:'storage',label:'存储与导出',icon:'database',description:'管理媒体保留策略与上传限制'},{key:'resources',label:'资源与连接',icon:'server',description:'配置任务并发与视频连接策略'},{key:'security',label:'接入安全',icon:'shield',description:'功能区域预留，暂不提供配置'},{key:'diagnostics',label:'诊断信息',icon:'activity',description:'查看本地环境与组件就绪情况'}]
const section=computed(()=>String(route.params.section??'general') as SettingsSection)
const current=computed(()=>sections.find(s=>s.key===section.value)!)
const snapshot=ref<Settings|null>(null),busy=ref(false),saving=ref(false),error=ref('')
const draft=reactive({retention_days:30,max_upload_mb:1024,export_formats:[] as string[],max_concurrent_jobs:2,connection_timeout_seconds:30,reconnect_attempts:3})
const {data:diagnostics,error:diagnosticError,refresh:refreshDiagnostics}=useResource(()=>api.getSettings('diagnostics'))
const plannedCapabilities=[
  {title:'智能场景适配',icon:'bot',description:'根据现场画面与验证目标，推荐场景模板和监测参数。'},
  {title:'多模态联合分析',icon:'video',description:'结合画面、文字描述与事件上下文，辅助理解复杂场景。'},
  {title:'误报反馈学习',icon:'refresh',description:'汇总人工核查与误报反馈，为后续规则优化提供依据。'},
  {title:'边缘算力调优',icon:'cpu',description:'结合设备负载，辅助规划模型选择与多路任务资源分配。'},
]
const writable=computed(()=>['storage','resources'].includes(section.value))
const editedValues=computed(()=>settingsPayload(section.value,{...draft},snapshot.value?.row_version??0).values)
const dirty=computed(()=>writable.value&&snapshot.value&&JSON.stringify(editedValues.value)!==JSON.stringify(settingsPayload(section.value,snapshot.value.values,snapshot.value.row_version).values))
let generation=0
function assign(value:Settings){
  snapshot.value=value
  for(const [key,item] of Object.entries(value.values)){
    if(key in draft){const target=draft as Record<string,unknown>;target[key]=Array.isArray(item)?[...item]:item}
  }
}
async function load(){const version=++generation;busy.value=true;error.value='';snapshot.value=null;if(['general','security'].includes(section.value)){busy.value=false;return}try{const result=await api.getSettings(section.value);if(version===generation)assign(result)}catch(e){if(version===generation)error.value=humanError(e)}finally{if(version===generation)busy.value=false}}
watch(section,load,{immediate:true})
async function save(){
  if(!writable.value||!snapshot.value)return
  error.value=validateSettings(section.value,editedValues.value);if(error.value)return
  saving.value=true
  try{assign(await api.saveSettings(section.value,editedValues.value,snapshot.value.row_version));message.success('设置已保存')}catch(e){error.value=humanError(e)}finally{saving.value=false}
}
function reset(){if(snapshot.value)assign({...snapshot.value,values:JSON.parse(JSON.stringify(snapshot.value.values)) as Record<string,unknown>});error.value=''}
function leave(){return !dirty.value||window.confirm('有尚未保存的设置，确定放弃这些修改吗？')}
onBeforeRouteLeave(leave);onBeforeRouteUpdate(leave)
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload);onUnmounted(()=>{generation++;window.removeEventListener('beforeunload',beforeUnload)})
</script>
<template><div class="page-heading"><div><h1>系统设置</h1><p>配置系统偏好和运行环境，保持工作空间稳定运行</p></div><span class="clock">设置保存在本机工作空间</span></div><div class="settings-workspace"><nav class="settings-nav" aria-label="设置分类"><RouterLink v-for="item in sections" :key="item.key" :to="`/settings/${item.key}`"><Icon :name="item.icon"/>{{item.label}}</RouterLink></nav><section class="panel settings-form"><div class="section-intro"><h2>{{current.label}}</h2><p>{{current.description}}</p></div><ErrorBanner :error="error" @retry="load"/><div v-if="busy" class="loading-line"/><div v-if="section==='general'" class="capability-preview"><div class="notice">以下为能力规划展示，尚未实现，当前不会执行分析、学习或自动调优。</div><article v-for="item in plannedCapabilities" :key="item.title" class="capability-card"><div class="capability-heading"><span class="stat-icon"><Icon :name="item.icon"/></span><span class="status">规划中</span></div><h3>{{item.title}}</h3><p>{{item.description}}</p><NButton size="small" disabled>暂未开放</NButton></article></div><EmptyState v-else-if="section==='security'" title="暂未开放" description="此区域暂时留空，后续按实际需求补充。" icon="shield" large/><form v-if="snapshot" @submit.prevent="save"><template v-if="section==='storage'"><div class="field"><label>媒体保留天数</label><NInputNumber v-model:value="draft.retention_days" :min="1" :max="3650" :disabled="!writable"/><div class="hint">设置保留策略；此设置本身不会立即清理已有媒体。</div></div><div class="field"><label>单个上传文件上限（MB）</label><NInputNumber v-model:value="draft.max_upload_mb" :min="1" :max="102400" :disabled="!writable"/></div><div class="field"><label>报告导出格式</label><NCheckboxGroup v-model:value="draft.export_formats" :disabled="!writable"><NCheckbox value="html" label="HTML"/><NCheckbox value="json" label="JSON"/><NCheckbox value="csv" label="CSV"/></NCheckboxGroup><div class="hint">用于后续报告模块的导出策略，当前尚未接入报告生成。</div></div><hr class="form-divider"/><div class="notice">存储位置由本机部署配置管理。此页面不接受任意服务器目录路径。</div><div v-for="key in ['media_directory','storage_directory','export_directory']" :key="key"><div v-if="snapshot.values[key]" class="info-row"><span>{{key==='export_directory'?'导出目录':'存储目录'}}</span><span>{{snapshot.values[key]}}</span></div></div></template><template v-else-if="section==='resources'"><div class="field"><label>最大并发处理数</label><NInputNumber v-model:value="draft.max_concurrent_jobs" :min="1" :max="8" :disabled="!writable"/><div class="hint">并发数量受设备实际性能限制，此设置不代表性能承诺。</div></div><div class="field"><label>连接超时（秒）</label><NInputNumber v-model:value="draft.connection_timeout_seconds" :min="1" :max="60" :disabled="!writable"/></div><div class="field"><label>自动重连次数</label><NInputNumber v-model:value="draft.reconnect_attempts" :min="0" :max="20" :disabled="!writable"/></div><div class="notice">并发与自动重连策略仅保存，执行能力将在后续模块接入；当前摄像头连接测试由后台处理。</div></template><template v-else><div class="info-row"><span>软件版本</span><span>{{snapshot.values.version||'未知'}}</span></div><div v-for="item in [{key:'worker_online',label:'后台处理进程'},{key:'ffmpeg_available',label:'媒体处理组件'},{key:'media_gateway_configured',label:'实时媒体网关'}]" :key="item.key" class="info-row"><span>{{item.label}}</span><span class="status" :class="snapshot.values[item.key]?'good':'warn'"><span class="dot"/>{{snapshot.values[item.key]?'已就绪':'未就绪'}}</span></div><div class="notice" style="margin-top:20px">此处展示本机组件配置与状态。完整运行采样和服务诊断请查看运行状态页。</div><RouterLink to="/runtime" style="display:inline-block;margin-top:18px">查看运行状态 ›</RouterLink></template><div v-if="writable" class="settings-actions"><span v-if="dirty" style="margin-right:auto;font-size:11px;color:#d88c31">有未保存的修改</span><NButton :disabled="!writable||saving" @click="reset">重置</NButton><NButton type="primary" attr-type="submit" :loading="saving" :disabled="!writable||!dirty">保存设置</NButton></div></form></section><div class="stack"><section class="panel"><div class="panel-title"><h2>部署与组件信息</h2><span class="status">本地部署</span></div><ErrorBanner :error="diagnosticError" @retry="refreshDiagnostics"/><div class="info-row"><span>软件版本</span><span>{{diagnostics?.values.version??'等待读取'}}</span></div><div class="info-row"><span>部署方式</span><span>本地工作空间</span></div><div class="info-row"><span>授权状态</span><span>未配置授权服务</span></div><div class="info-row"><span>模型运行时</span><span>尚未接入</span></div><div class="info-row"><span>媒体处理组件</span><span>{{diagnostics?diagnostics.values.ffmpeg_available?'已就绪':'未就绪':'等待读取'}}</span></div></section><section class="panel"><div class="panel-title"><h2>配置说明</h2></div><div class="service-row"><Icon name="shield" style="color:#3985ed;flex-shrink:0"/><div><h3>按需开放访问</h3><small>摄像头仅连接已允许的本机或私网地址。</small></div></div><div class="service-row"><Icon name="database" style="color:#3985ed;flex-shrink:0"/><div><h3>设置持久保存</h3><small>保存后刷新可读取。尚未接入的策略会单独说明，并发修改会提示重试。</small></div></div></section><div class="notice"><Icon name="info" :size="16" style="vertical-align:middle;margin-right:5px"/>部署目录、监听地址与媒体网关由本机部署配置管理。</div></div></div></template>

<style scoped>
.capability-preview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.capability-preview>.notice{grid-column:1/-1}
.capability-card{padding:18px;border:1px solid #e6edf6;border-radius:9px;background:linear-gradient(145deg,#f7faff,#fff)}
.capability-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.capability-heading .stat-icon{width:40px;height:40px;border-radius:10px}
.capability-card h3{font-size:14px;margin-bottom:8px}
.capability-card p{font-size:12px;color:#78859a;line-height:1.8;min-height:66px;margin-bottom:16px}
@media(max-width:700px){.capability-preview{grid-template-columns:1fr}.capability-card p{min-height:0}}
</style>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { NButton, NCheckbox, NCheckboxGroup, NSelect } from 'naive-ui'
import { agentApi, type ExportJob, type Run } from './api'
import { agentError, label, received, requestKey } from './state'
import { safeMediaUrl } from '../../shared/media/url'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
const props=defineProps<{agentId:string;runs:Run[];canWrite:boolean;isDemo:boolean}>()
const selectedRuns=ref<string[]>([]),contents=ref<string[]>(['report']),jobs=ref<ExportJob[]>([]),error=ref(''),busy=ref(false),notice=ref('')
const destination=ref('browser'),destinationOptions=ref<{label:string;value:string}[]>([]),destinationError=ref('')
async function loadDestinations(){try{const result=await agentApi.exportDestinations();destinationOptions.value=result.items.map(d=>({label:d.label,value:d.kind==='browser'?'browser':`host:${d.alias}`}));destinationError.value=''}catch(e){destinationError.value=agentError(e)}}
void loadDestinations()
let timer:ReturnType<typeof setTimeout>|undefined,stopped=false,generation=0
const terminal=new Set(['succeeded','failed','canceled'])
function saveIds(){sessionStorage.setItem(`vision.agent.exports.${props.agentId}`,JSON.stringify(jobs.value.map(j=>j.id).slice(0,30)))}
function track(job:ExportJob){jobs.value=[job,...jobs.value.filter(j=>j.id!==job.id)].slice(0,30);saveIds()}
async function poll(){
  const current=generation,id=props.agentId
  for(const job of jobs.value.filter(j=>!terminal.has(j.state))){try{const result=await agentApi.exportStatus(id,job.id);if(current===generation&&!stopped)jobs.value=jobs.value.map(j=>j.id===job.id?result:j)}catch(e){if(current===generation)error.value=agentError(e)}}
  if(!stopped&&current===generation)timer=setTimeout(()=>void poll(),2000)
}
watch(()=>props.agentId,async()=>{
  generation++;clearTimeout(timer);jobs.value=[];error.value='';const current=generation
  let ids:string[]=[];try{ids=JSON.parse(sessionStorage.getItem(`vision.agent.exports.${props.agentId}`)??'[]') as string[]}catch{/* invalid local tracking state */}
  for(const id of ids.slice(0,30)){try{const job=await agentApi.exportStatus(props.agentId,id);if(current===generation)jobs.value.push(job)}catch(e){if(current===generation)error.value=agentError(e)}}
  if(current===generation&&!stopped)void poll()
},{immediate:true})
onUnmounted(()=>{stopped=true;generation++;clearTimeout(timer)})
async function create(){
  if(busy.value)return
  if(!selectedRuns.value.length||!contents.value.length){error.value='请选择运行范围，并至少选择一种导出内容。';return}
  const body={run_ids:selectedRuns.value,contents:contents.value as ('report'|'images'|'clips')[],destination:destination.value.startsWith('host:')?'host' as const:'browser' as const,destination_alias:destination.value.startsWith('host:')?destination.value.slice(5):null},scope=`export.${props.agentId}`
  busy.value=true;error.value='';notice.value=''
  try{const job=await agentApi.export(props.agentId,body,requestKey(scope,body));received(scope);track(job);notice.value='导出已受理，请等待作业成功后下载。'}catch(e){error.value=agentError(e)}finally{busy.value=false}
}
async function action(job:ExportJob,kind:'cancel'|'retry'){
  if(busy.value)return
  busy.value=true;error.value='';const scope=`export.${job.id}.${kind}`
  try{const result=await agentApi.exportAction(props.agentId,job.id,kind,requestKey(scope,{job_id:job.id,kind}));received(scope);track(result)}catch(e){error.value=agentError(e)}finally{busy.value=false}
}
</script>
<template>
  <section class="panel"><h2>导出验证结果</h2><p class="notice">{{isDemo?'演示模式只生成带有 MOCK 标记的模拟清单，不生成正式报告、截图或片段。':'报告、截图和片段由公共导出服务生成。网页不能承诺直接写入浏览器所在电脑的任意目录。'}}</p>
    <template v-if="canWrite"><div class="field"><label>导出哪些实际运行</label><NSelect v-model:value="selectedRuns" multiple :options="runs.map(r=>({label:`${r.channel_name} · v${r.revision_no} · ${r.id}`,value:r.id}))" aria-label="导出运行范围"/></div><div class="field"><label>导出内容（可分别选择）</label><NCheckboxGroup v-model:value="contents"><NCheckbox value="report" label="报告"/><NCheckbox value="images" label="截图"/><NCheckbox value="clips" label="事件片段"/></NCheckboxGroup></div><div class="field"><label>保存位置</label><NSelect v-model:value="destination" :options="destinationOptions" aria-label="导出保存位置" :disabled="busy||!!destinationError"/></div><p class="muted">当前电脑由浏览器选择保存路径；服务主机只能使用后台提供的允许目录别名，不接受任意主机文件路径。</p><ErrorBanner :error="destinationError" @retry="loadDestinations"/><div class="agent-actions"><NButton @click="selectedRuns=[];notice='已选择暂不导出，原运行和反馈继续保留。'">暂不导出</NButton><NButton type="primary" :loading="busy" :disabled="!selectedRuns.length||!contents.length||!!destinationError||!destinationOptions.length" @click="create">{{isDemo?'提交模拟导出':'提交导出'}}</NButton></div></template>
    <p v-if="notice" class="notice" role="status">{{notice}}</p><ErrorBanner :error="error" :retryable="false"/>
    <article v-for="job in jobs" :key="job.id" class="run-history-row"><div class="panel-title"><strong>{{job.data_origin==='mock'?'模拟导出':'导出作业'}} · {{label(job.state)}}</strong><small>{{job.completed_items}} / {{job.total_items??'未知'}} 项</small></div><p>{{job.message}}</p><small>{{job.id}}</small><div class="agent-actions"><NButton v-if="canWrite&&!terminal.has(job.state)" :disabled="busy" size="small" @click="action(job,'cancel')">取消作业</NButton><NButton v-if="canWrite&&['failed','canceled'].includes(job.state)" :disabled="busy" size="small" @click="action(job,'retry')">重试（保留原快照）</NButton><a v-if="job.state==='succeeded'&&safeMediaUrl(job.download_url??null)" :href="safeMediaUrl(job.download_url??null)!" download>{{job.data_origin==='mock'?'下载模拟清单 JSON（非报告）':'下载导出结果'}}</a></div></article>
    <p v-if="!jobs.length" class="muted">当前浏览器尚未跟踪导出作业。</p>
  </section>
</template>

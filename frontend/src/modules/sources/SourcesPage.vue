<script setup lang="ts">
import { computed, nextTick, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton,NCheckbox,NInput,NPopconfirm,NProgress,NSelect,useMessage } from 'naive-ui'
import { api,uploadTransport } from '../../shared/api'
import type { Source,Upload } from '../../shared/api/types'
import { humanError } from '../../shared/api/client'
import { useResource,formatDate,formatBytes,duration } from '../../shared/ui/resource'
import { safeMediaUrl } from '../../shared/media/url'
import { uploadFile,uploadErrorMessage } from './upload'
import { cameraPatch,validateCamera } from './validation'
import EmptyState from '../../shared/ui/EmptyState.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import Icon from '../../shared/ui/Icon.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
import MediaPlayer from '../../shared/media/MediaPlayer.vue'
const route=useRoute(),router=useRouter(),message=useMessage()
const search=ref(String(route.query.q??'')),kind=ref(''),status=ref(''),tab=ref<'file'|'camera'>('file')
const {data,loading,error,refresh}=useResource(()=>api.sources(search.value,kind.value,status.value))
const selected=ref<Source|null>(null),detailError=ref(''),detailBusy=ref(false),saving=ref(false),testing=ref(false),testMessage=ref(''),testState=ref(''),clearCredentials=ref(false)
const edit=reactive({name:'',address:'',username:'',password:''}),camera=reactive({name:'',address:'',username:'',password:''})
const creating=ref(false),createError=ref(''),upload=ref<Upload|null>(null),uploading=ref(false),uploadError=ref(''),uploadFilename=ref('')
let abort:AbortController|undefined,stopped=false,searchTimer:ReturnType<typeof setTimeout>|undefined,detailGeneration=0
const statusOptions=computed(()=>[{label:'全部状态',value:''},...((kind.value==='camera'?['unverified','online','disconnected','failed']:kind.value==='file'?['ready','probing','transcoding','failed']:['ready','online','unverified','probing','failed']).map(value=>({label:({ready:'就绪',online:'在线',unverified:'未验证',disconnected:'已断开',failed:'失败',probing:'探测中',transcoding:'转码中'} as Record<string,string>)[value]!,value})))])
function fill(source:Source){selected.value=source;Object.assign(edit,{name:source.name,address:source.address??'',username:'',password:''});clearCredentials.value=false}
async function loadDetail(){
  const id=String(route.params.id??'');const generation=++detailGeneration
  detailError.value='';testMessage.value=''
  if(!id){selected.value=null;return}
  detailBusy.value=true
  try{const source=await api.source(id);if(generation===detailGeneration)fill(source)}catch(e){if(generation===detailGeneration){selected.value=null;detailError.value=humanError(e)}}finally{if(generation===detailGeneration)detailBusy.value=false}
}
watch(()=>route.params.id,loadDetail,{immediate:true})
watch(()=>route.query.q,value=>{search.value=String(value??'')})
watch([search,kind,status],()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>void refresh(),250)})
async function choose(source:Source){await router.push(`/sources/${source.id}`)}
async function save(){
  if(!selected.value)return
  detailError.value=selected.value.kind==='camera'?validateCamera(edit):!edit.name.trim()?'请输入视频源名称。':''
  if(detailError.value)return
  saving.value=true
  try{const input=selected.value.kind==='camera'?cameraPatch(edit,selected.value.row_version,clearCredentials.value):{name:edit.name.trim(),row_version:selected.value.row_version};fill(await api.updateSource(selected.value.id,input));message.success('视频源配置已保存');await refresh()}catch(e){detailError.value=humanError(e)}finally{saving.value=false}
}
async function archive(){
  if(!selected.value)return
  try{await api.archiveSource(selected.value.id);message.success('视频源已归档');await router.push('/sources');await refresh()}catch(e){detailError.value=humanError(e)}
}
async function test(){
  if(!selected.value)return
  testing.value=true;detailError.value='';testMessage.value='';testState.value='pending'
  const sourceId=selected.value.id
  try{
    let result=await api.testSource(sourceId)
    for(let i=0;i<120&&!stopped;i++){
      if(!['pending','queued','running','connecting'].includes(result.state))break
      await new Promise<void>(resolve=>setTimeout(resolve,1000));if(stopped)return
      result=await api.sourceTest(result.id)
    }
    if(stopped||selected.value?.id!==sourceId)return
    testState.value=result.state
    testMessage.value=result.message??(['failed'].includes(result.state)?'测试未通过，请检查连接和服务状态。':result.state==='pending'||result.state==='running'?'测试仍在处理，请稍后刷新查看来源状态。':'连接测试已处理，请以视频源实际状态和诊断为准。')
    fill(await api.source(sourceId));await refresh()
  }catch(e){detailError.value=humanError(e)}finally{testing.value=false}
}
async function create(){
  createError.value=validateCamera(camera);if(createError.value)return
  creating.value=true
  try{const source=await api.createCamera({name:camera.name.trim(),kind:'camera',address:camera.address.trim(),...(camera.username?{username:camera.username}:{}),...(camera.password?{password:camera.password}:{})});Object.assign(camera,{name:'',address:'',username:'',password:''});message.success('摄像头已保存，请执行连接测试');await refresh();await choose(source)}catch(e){createError.value=humanError(e)}finally{creating.value=false}
}
async function importFile(event:Event){
  const input=event.target as HTMLInputElement,file=input.files?.[0];if(!file||uploading.value)return
  uploadError.value='';uploadFilename.value=file.name;uploading.value=true;upload.value=null;abort=new AbortController()
  try{const result=await uploadFile(file,uploadTransport,state=>{upload.value=state},{signal:abort.signal});message.success('视频已完成探测并导入');await refresh();if(result.source_id)await router.push(`/sources/${result.source_id}`)}catch(e){uploadError.value=uploadErrorMessage(e)}finally{uploading.value=false;input.value=''}
}
async function goImport(){await nextTick();document.querySelector('#source-import')?.scrollIntoView({behavior:'smooth',block:'start'})}
onUnmounted(()=>{stopped=true;detailGeneration++;clearTimeout(searchTimer);abort?.abort()})
</script>
<template>
<div class="page-heading">
<div>
<h1>视频源管理</h1>
<p>统一管理本地录像与摄像头，支持连接测试、预览和基础信息维护</p>
</div>
<NButton type="primary" size="small" @click="goImport">
<template #icon>
<Icon name="plus" :size="16"/>
</template>新增视频源</NButton>
</div>
<ErrorBanner :error="error" @retry="refresh"/>
<div class="source-workspace">
<section class="panel">
<div class="panel-title">
<h2>视频源列表 <small>（{{data?.items.length??0}}）</small>
</h2>
<NButton text size="small" :loading="loading" @click="refresh">
<Icon name="refresh" :size="15"/>
</NButton>
</div>
<div class="toolbar">
<NInput v-model:value="search" class="search" placeholder="搜索源名称或地址…" aria-label="搜索视频源">
<template #prefix>
<Icon name="search" :size="15"/>
</template>
</NInput>
<NSelect v-model:value="kind" :options="[{label:'全部类型',value:''},{label:'本地文件',value:'file'},{label:'摄像头',value:'camera'}]" aria-label="视频源类型"/>
<NSelect v-model:value="status" :options="statusOptions" aria-label="视频源状态"/>
</div>
<div v-if="loading&&!data" class="loading-line"/>
<div v-if="data?.items.length" class="table-wrap">
<table>
<thead>
<tr>
<th>来源名称</th>
<th>类型</th>
<th>状态</th>
<th>最近检测</th>
<th>操作</th>
</tr>
</thead>
<tbody>
<tr v-for="source in data.items" :key="source.id" class="source-row" :class="{selected:source.id===selected?.id}" @click="choose(source)">
<td>
<div class="source-name">
<span class="source-thumb">
<img v-if="safeMediaUrl(source.thumbnail_url)" :src="safeMediaUrl(source.thumbnail_url)!" alt=""/>
<Icon v-else :name="source.kind==='camera'?'camera':'film'"/>
</span>
<div>{{source.name}}<span class="source-meta">{{source.address||formatBytes(source.size_bytes)}}</span>
</div>
</div>
</td>
<td>
<span class="status" :style="{color:source.kind==='camera'?'#4286df':'#8b69ce',background:source.kind==='camera'?'#edf5ff':'#f5f0ff'}">{{source.kind==='camera'?'RTSP':'本地文件'}}</span>
</td>
<td>
<StatusBadge :value="source.status"/>
</td>
<td style="font-size:10px;color:#8b97a9">{{formatDate(source.observed_at)}}</td>
<td>
<RouterLink :to="`/sources/${source.id}`" @click.stop>详情</RouterLink>
</td>
</tr>
</tbody>
</table>
</div>
<EmptyState v-else :title="search||kind||status?'没有匹配的视频源':'还没有视频源'" :description="search||kind||status?'尝试调整搜索内容或筛选条件。':'在下方导入本地录像，或填写摄像头连接信息。'" icon="video" large/>
<div v-if="data?.next_cursor" class="notice">当前展示前 100 项，请通过搜索缩小范围。</div>
</section>
<section class="panel source-detail">
<div class="detail-heading">
<h2>视频源详情</h2>
<StatusBadge v-if="selected" :value="selected.status"/>
</div>
<ErrorBanner :error="detailError" @retry="loadDetail"/>
<div v-if="detailBusy" class="loading-line"/>
<div v-for="detail in selected ? [selected] : []" :key="detail.id">
<div class="field">
<label for="source-name">视频源名称</label>
<NInput id="source-name" v-model:value="edit.name" placeholder="视频源名称"/>
</div>
<template v-if="detail.kind==='camera'">
<div class="field">
<label for="source-address">视频源地址</label>
<NInput id="source-address" v-model:value="edit.address" placeholder="rtsp://192.168.1.10:554/live"/>
</div>
<div class="field-grid">
<div class="field">
<label>用户名</label>
<NInput v-model:value="edit.username" :disabled="clearCredentials" placeholder="留空保留原凭据" autocomplete="off"/>
</div>
<div class="field">
<label>密码</label>
<NInput v-model:value="edit.password" :disabled="clearCredentials" type="password" show-password-on="click" placeholder="留空保留原密码" autocomplete="new-password"/>
</div>
</div>
<NCheckbox v-model:checked="clearCredentials" style="font-size:11px">明确清除已保存的用户名和密码</NCheckbox>
</template>
<div class="button-row">
<NButton v-if="detail.kind==='camera'" :loading="testing" @click="test">
<template #icon>
<Icon name="play" :size="14"/>
</template>测试连接</NButton>
<NButton type="primary" :loading="saving" @click="save">保存配置</NButton>
</div>
<div v-if="testMessage" class="notice" style="margin-top:12px" role="status">{{testMessage}}</div>
<div v-if="detail.error_message" class="notice" style="margin-top:12px">{{detail.error_message}}</div>
<dl class="detail-meta">
<div>
<dt>分辨率</dt>
<dd>{{detail.width&&detail.height?`${detail.width} × ${detail.height}`:'尚未获取'}}</dd>
</div>
<div>
<dt>帧率</dt>
<dd>{{detail.fps?`${detail.fps} FPS`:'尚未获取'}}</dd>
</div>
<div v-if="detail.kind==='file'">
<dt>文件大小</dt>
<dd>{{formatBytes(detail.size_bytes)}}</dd>
</div>
<div v-if="detail.kind==='file'">
<dt>时长</dt>
<dd>{{duration(detail.duration_ms)}}</dd>
</div>
<div class="wide">
<dt>创建时间</dt>
<dd>{{formatDate(detail.created_at)}}</dd>
</div>
<div v-if="detail.sha256" class="wide">
<dt>SHA-256</dt>
<dd style="font-size:10px">{{detail.sha256}}</dd>
</div>
</dl>
<h3 style="margin-bottom:10px">视频预览</h3>
<MediaPlayer v-if="['ready','online','unverified'].includes(detail.status)" :key="detail.id" :source="detail"/>
<div v-else class="media-player">
<Icon name="video"/>
<span>当前状态暂不可预览，请等待处理或检查错误。</span>
</div>
<div style="text-align:right;margin-top:17px">
<NPopconfirm @positive-click="archive">
<template #trigger>
<NButton size="small" text type="error">归档此视频源</NButton>
</template>归档后将从来源列表移除，确定继续？</NPopconfirm>
</div>
</div>
<EmptyState v-if="!selected" title="选择一个视频源" description="从左侧列表打开详情，查看元信息、编辑连接或预览视频。" large icon="video"/>
</section>
</div>
<section id="source-import" class="panel import-section">
<div class="import-tabs" role="tablist" aria-label="视频源接入方式">
<button :class="{active:tab==='file'}" role="tab" :aria-selected="tab==='file'" @click="tab='file'">本地录像</button>
<button :class="{active:tab==='camera'}" role="tab" :aria-selected="tab==='camera'" @click="tab='camera'">摄像头接入</button>
</div>
<template v-if="tab==='file'">
<div class="upload-zone">
<Icon name="upload" :size="28"/>
<strong>{{uploading?'正在上传并处理视频…':'点击选择本地录像'}}</strong>
<span>文件将在本机保存并执行媒体探测，完成后可预览</span>
<input type="file" accept="video/*,.mkv,.avi,.mov,.ts" aria-label="导入本地视频" :disabled="uploading" @change="importFile"/>
</div>
<div v-if="upload" class="upload-progress">
<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:9px">
<span>{{uploadFilename}}</span>
<StatusBadge :value="upload.state"/>
</div>
<NProgress type="line" :percentage="Math.min(100,Math.round(upload.received_bytes/upload.size_bytes*100))" :processing="uploading" :show-indicator="true"/>
<div style="display:flex;justify-content:space-between;margin-top:8px;font-size:11px;color:#8a99ad">
<span>{{formatBytes(upload.received_bytes)}} / {{formatBytes(upload.size_bytes)}} · 上传完成后仍需探测</span>
<NButton v-if="uploading" text size="tiny" @click="abort?.abort()">取消</NButton>
</div>
</div>
<div v-if="uploadError" class="error-banner" style="margin-top:13px" role="alert">{{uploadError}}</div>
</template>
<form v-else style="max-width:740px" @submit.prevent="create">
<div class="field-grid">
<div class="field">
<label>视频源名称</label>
<NInput v-model:value="camera.name" placeholder="例如：园区入口"/>
</div>
<div class="field">
<label>RTSP 地址</label>
<NInput v-model:value="camera.address" placeholder="rtsp://192.168.1.10:554/live"/>
</div>
</div>
<div class="field-grid">
<div class="field">
<label>用户名（可选）</label>
<NInput v-model:value="camera.username" placeholder="摄像头用户名" autocomplete="off"/>
</div>
<div class="field">
<label>密码（可选）</label>
<NInput v-model:value="camera.password" type="password" show-password-on="click" placeholder="摄像头密码" autocomplete="new-password"/>
</div>
</div>
<div class="notice">地址须位于设置允许的网段内。保存后请执行连接测试；实时预览需要本地媒体网关就绪。</div>
<div v-if="createError" class="error-banner" style="margin-top:12px" role="alert">{{createError}}</div>
<NButton type="primary" attr-type="submit" :loading="creating" style="margin-top:15px">保存摄像头</NButton>
</form>
</section>
</template>

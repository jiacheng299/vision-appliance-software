<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import type Hls from 'hls.js'
import { NButton } from 'naive-ui'
import { safeMediaUrl } from '../../shared/media/url'
import { formatDate } from '../../shared/ui/resource'
import { agentApi, type Playback } from './api'
import { agentError } from './state'
import DetectionPreview from './DetectionPreview.vue'
const props=withDefaults(defineProps<{identity:string;agentId:string;load:()=>Promise<Playback>;mediaKind?:'image'|'video';isLive?:boolean;alertActive?:boolean;alertLabel?:string}>(),{mediaKind:'video',isLive:false,alertActive:false,alertLabel:'人员缺岗'})
const emit=defineEmits<{position:[mediaMs:number]}>()
const session=ref<Playback|null>(null),error=ref(''),loading=ref(false),video=ref<HTMLVideoElement|null>(null),surface=ref<HTMLElement|null>(null),ratio=ref(16/9)
let generation=0,timer:ReturnType<typeof setTimeout>|undefined,hls:Hls|null=null,peer:RTCPeerConnection|null=null,whepUrl:string|null=null,controller:AbortController|null=null
let targetTimer:ReturnType<typeof setTimeout>|undefined
const mediaVersion=ref(0)
const view=ref<'detection'|'original'>('detection'),preview=ref<InstanceType<typeof DetectionPreview>|null>(null)
const canDetect=computed(()=>props.isLive&&props.mediaKind==='video'&&session.value?.detection_available===true)
const usingDetection=computed(()=>canDetect.value&&view.value==='detection')
async function switchView(){view.value=view.value==='detection'?'original':'detection';disposeMedia();await nextTick();if(!usingDetection.value)await attach(generation)}
let recoveryTimer:ReturnType<typeof setTimeout>|undefined,recoveryAttempts=0
function mediaFailure(message:string,current:number){
  if(current!==generation)return
  error.value=message
  if(!props.isLive||recoveryTimer||recoveryAttempts>=3)return
  recoveryAttempts++
  error.value=`视频暂时中断，正在自动重连（${recoveryAttempts}/3）…`
  recoveryTimer=setTimeout(()=>{recoveryTimer=undefined;if(current===generation)void refresh()},1000*recoveryAttempts)
}
function mediaError(event:Event){
  const player=event.target as HTMLVideoElement
  if(player!==video.value||!player.error||player.error.code===1)return
  mediaFailure('视频无法播放或已断流，请重试。',generation)
}
function playing(event:Event){
  if(event.target!==video.value)return
  error.value='';recoveryAttempts=0;clearTimeout(recoveryTimer);recoveryTimer=undefined
}
const polygon=(points:number[][])=>points.map(p=>`${p[0]! *1000},${p[1]! *1000}`).join(' ')
function localUrl(value:string|null|undefined):string|null {
  if(!value)return null
  try{const url=new URL(value,location.origin);return url.origin===location.origin?safeMediaUrl(url.pathname+url.search):null}catch{return null}
}
const url=computed(()=>localUrl(session.value?.playback_url))
const observedClock=ref(Date.now())
const observationTimer=setInterval(()=>{observedClock.value=Date.now()},1000)
const targetsFresh=computed(()=>session.value?.data_origin==='mock'||(session.value?.observed_at&&observedClock.value-Date.parse(session.value.observed_at)<3000))
async function updateTargets(current:number){
  if(current!==generation||!props.isLive||!session.value)return
  try{
    const value=await props.load()
    try{
      if(current!==generation||!props.isLive||!session.value)return
      if(value.agent_id!==props.agentId||value.run_id!==session.value.run_id)return
      // Update only overlay metadata; retain the active player and media session.
      session.value={...session.value,regions:value.regions,targets:value.targets,observed_at:value.observed_at}
    }finally{if(value.id!==session.value?.id)release(value)}
  }catch{if(current===generation&&session.value)session.value={...session.value,targets:[]}}
  finally{if(current===generation&&props.isLive)targetTimer=setTimeout(()=>void updateTargets(current),1000)}
}
function position(){if(session.value&&!loading.value&&video.value)emit('position',Math.round(video.value.currentTime*1000)+session.value.media_origin_ms)}
function disposeMedia(){
  hls?.destroy();hls=null;peer?.close();peer=null;controller?.abort();controller=null
  if(whepUrl){void fetch(whepUrl,{method:'DELETE',credentials:'same-origin'}).catch(()=>{});whepUrl=null}
  if(video.value){video.value.pause();video.value.srcObject=null;video.value.removeAttribute('src');video.value.load()}
}
function release(old:Playback|null){if(old)void agentApi.releasePlayback(old.agent_id,old.id).catch(()=>{})}
async function attach(current:number){
  if(!session.value||session.value.protocol==='mock'||props.mediaKind==='image')return
  if(!url.value||!video.value){error.value='媒体服务没有返回受保护的本地播放地址。';return}
  const player=video.value
  if(session.value.protocol==='webrtc'){
    peer=new RTCPeerConnection({iceServers:[]});const connection=peer
    connection.addTransceiver('video',{direction:'recvonly'});connection.addTransceiver('audio',{direction:'recvonly'})
    connection.ontrack=event=>{if(current===generation)player.srcObject=event.streams[0]??new MediaStream([event.track])}
    await connection.setLocalDescription(await connection.createOffer())
    if(connection.iceGatheringState!=='complete')await new Promise<void>(resolve=>{
      const timeout=setTimeout(resolve,1500)
      connection.addEventListener('icegatheringstatechange',()=>{if(connection.iceGatheringState==='complete'){clearTimeout(timeout);resolve()}},{once:true})
    })
    if(current!==generation)return
    controller=new AbortController()
    const response=await fetch(url.value,{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/sdp'},body:connection.localDescription?.sdp})
    if(!response.ok)throw new Error('WHEP_FAILED')
    const locationHeader=response.headers.get('Location')
    if(locationHeader){const path=localUrl(new URL(locationHeader,new URL(url.value,location.origin)).href);if(!path)throw new Error('UNSAFE_WHEP_SESSION');whepUrl=path}
    await connection.setRemoteDescription({type:'answer',sdp:await response.text()})
    void player.play().catch(()=>{})
  }else if(session.value.protocol==='hls'&&!player.canPlayType('application/vnd.apple.mpegurl')){
    const {default:Hls}=await import('hls.js')
    if(current!==generation)return
    if(!Hls.isSupported()){error.value='当前浏览器无法播放此 HLS 流，请使用支持媒体扩展的浏览器。';return}
    hls=new Hls({xhrSetup:(request,target)=>{if(!localUrl(target))throw new Error('UNSAFE_MEDIA_URL');request.withCredentials=true}})
    hls.on(Hls.Events.ERROR,(_event,data)=>{if(data.fatal)mediaFailure('视频流已中断，请重试播放。报警和配置仍可独立查看。',current)})
    hls.on(Hls.Events.MANIFEST_PARSED,()=>{if(current===generation&&props.isLive)void player.play().catch(()=>{})})
    hls.loadSource(url.value);hls.attachMedia(player)
  }else player.src=url.value
}
async function refresh(){
  const request=++generation;clearTimeout(timer);clearTimeout(targetTimer);clearTimeout(recoveryTimer);recoveryTimer=undefined;disposeMedia();mediaVersion.value=request;loading.value=true;error.value=''
  const old=session.value;session.value=null;release(old)
  if(!props.identity){loading.value=false;return}
  try{
    const value=await props.load()
    if(request!==generation){release(value);return}
    if(value.agent_id!==props.agentId)throw new Error('SESSION_SCOPE_INVALID')
    session.value=value;await nextTick();if(!usingDetection.value)await attach(request)
    if(request!==generation)return
    const expires=Date.parse(value.expires_at)
    if(!Number.isFinite(expires)||expires<=Date.now())throw new Error('SESSION_EXPIRED')
    timer=setTimeout(()=>void refresh(),Math.max(1000,expires-Date.now()-30000))
    if(props.isLive&&value.data_origin==='mock')targetTimer=setTimeout(()=>void updateTargets(request),1000)
  }catch(e){if(request===generation){disposeMedia();error.value=(e as {response?:unknown}).response?agentError(e):'无法建立有效的播放会话，请重试或检查视频网关。'}}
  finally{if(request===generation)loading.value=false}
}
async function fullscreen(){try{await surface.value?.requestFullscreen()}catch{error.value='当前环境无法进入全屏。'}}
function screenshot(){
  if(usingDetection.value){preview.value?.screenshot();return}
  if(!video.value||video.value.readyState<2||session.value?.data_origin==='mock'){error.value='当前没有可截图的真实画面。';return}
  try{
    const canvas=document.createElement('canvas');canvas.width=video.value.videoWidth;canvas.height=video.value.videoHeight
    canvas.getContext('2d')?.drawImage(video.value,0,0)
    canvas.toBlob(blob=>{if(!blob)return;const target=URL.createObjectURL(blob),link=document.createElement('a');link.href=target;link.download=`preview-${Date.now()}.png`;link.click();setTimeout(()=>URL.revokeObjectURL(target),1000)},'image/png')
  }catch{error.value='此画面暂不允许浏览器截图，请通过事件证据服务查看。'}
}
watch(()=>props.identity,()=>{view.value='detection';recoveryAttempts=0;void refresh()},{immediate:true})
watch(()=>props.isLive,value=>{clearTimeout(targetTimer);if(value&&session.value?.data_origin==='mock')targetTimer=setTimeout(()=>void updateTargets(generation),1000)})
onUnmounted(()=>{generation++;clearTimeout(timer);clearTimeout(targetTimer);clearTimeout(recoveryTimer);clearInterval(observationTimer);disposeMedia();release(session.value)})
</script>
<template>
  <div class="run-player">
    <div ref="surface" class="run-player-surface" :class="{'alert-active':alertActive}">
      <div class="run-frame" :class="{'alert-active':alertActive}" :style="{aspectRatio:ratio,'--frame-ratio':ratio}">
        <div v-if="alertActive" class="run-alert-banner" role="alert">{{alertLabel}}</div>
        <DetectionPreview v-if="usingDetection&&session?.run_id" ref="preview" :agent-id="agentId" :run-id="session.run_id" @ratio="ratio=$event"/>
        <template v-else-if="session?.protocol==='mock'"><div class="mock-room"><span class="mock-room-label">模拟场景示意图 · 非真实{{mediaKind==='image'?'截图':'视频'}}</span><div class="mock-floor"/><span class="mock-person"/></div></template>
        <img v-else-if="session&&mediaKind==='image'&&url" :src="url" alt="事件证据截图" @error="error='证据图片暂时无法读取，请重试。'"/>
        <video v-else-if="session" :key="mediaVersion" ref="video" @timeupdate="position" controls playsinline :autoplay="isLive" muted @playing="playing" @loadedmetadata="ratio=video?.videoWidth&&video?.videoHeight?video.videoWidth/video.videoHeight:16/9" @error="mediaError"/>
        <div v-else class="run-player-placeholder">{{loading?'正在申请受保护的播放会话…':'暂无可用画面'}}</div>
        <svg v-if="session&&!usingDetection" class="run-overlays" :class="{'alert-active':alertActive}" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="后端提供的监测区域与目标位置">
          <polygon v-for="region in session.regions" :key="region.id" :points="polygon(region.points)" class="roi-saved"/>
          <template v-if="session.data_origin==='mock'&&targetsFresh"><rect v-for="box in session.targets" :key="box.id" :x="box.x*1000" :y="box.y*1000" :width="box.width*1000" :height="box.height*1000" fill="none" stroke="#72ef9d" stroke-width="3" vector-effect="non-scaling-stroke"/></template>
        </svg>
      </div>
    </div>
    <label v-if="session?.protocol==='mock'&&session.duration_ms!=null&&mediaKind==='video'" class="mock-position">模拟回放位置（仅演示）<input type="range" :min="0" :max="session.duration_ms" step="100" aria-label="模拟回放位置" @input="emit('position',Number(($event.target as HTMLInputElement).value)+session.media_origin_ms)"/></label><p v-if="error" class="error-banner" role="alert">{{error}}</p>
    <p v-if="session?.message" class="muted">{{session.message}}</p><p v-if="session?.observed_at&&session.data_origin==='mock'" class="muted">叠加数据观测时间：{{formatDate(session.observed_at)}}</p>
    <div class="agent-actions"><NButton v-if="canDetect" size="small" @click="switchView">{{usingDetection?'切换原始视频':'切换检测画面'}}</NButton><NButton size="small" :loading="loading" @click="refresh">{{error?'重试播放':'刷新会话'}}</NButton><NButton size="small" :disabled="!session" @click="fullscreen">全屏</NButton><NButton v-if="mediaKind==='video'" size="small" :disabled="!session||session.data_origin==='mock'" title="保存当前预览帧，不会自动创建事件证据" @click="screenshot">截图</NButton></div>
  </div>
</template>

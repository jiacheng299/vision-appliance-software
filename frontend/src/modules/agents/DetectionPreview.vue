<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { agentApi } from './api'
import { detectionFrames,type DetectionFrame } from './detectionStream'
import { formatDate } from '../../shared/ui/resource'
const props=defineProps<{agentId:string;runId:string}>()
const emit=defineEmits<{ratio:[value:number]}>()
const url=ref(''),observedAt=ref('')
let generation=0,controller:AbortController|undefined,retryTimer:ReturnType<typeof setTimeout>|undefined,expiry:ReturnType<typeof setTimeout>|undefined
const pendingUrls=new Set<string>()
function clearFrame(){if(url.value)URL.revokeObjectURL(url.value);url.value='';observedAt.value=''}
function reset(){generation++;controller?.abort();clearTimeout(retryTimer);clearTimeout(expiry);clearFrame();for(const p of pendingUrls)URL.revokeObjectURL(p);pendingUrls.clear()}
function retry(current:number){if(current!==generation)return;reset();retryTimer=setTimeout(()=>void connect(generation),1000)}
function watchFrame(current:number,delay=3000){clearTimeout(expiry);expiry=setTimeout(()=>retry(current),delay)}
async function connect(current:number){
  if(current!==generation)return
  controller=new AbortController();watchFrame(current)
  let latest:DetectionFrame|undefined,painting=false
  async function paint(){
    painting=true
    try {
      while(current===generation&&latest){
        const frame=latest;latest=undefined
        if(Date.now()-Date.parse(frame.observedAt)>=3000)continue
        const next=URL.createObjectURL(frame.image);pendingUrls.add(next)
        const image=new Image()
        await new Promise<void>((resolve,reject)=>{
          const timeout=setTimeout(()=>reject(new Error('Decode timeout')),1000)
          image.onload=()=>{clearTimeout(timeout);resolve()}
          image.onerror=()=>{clearTimeout(timeout);reject(new Error('Image decode failed'))}
          image.src=next
        })
        if(current!==generation)return
        const age=Math.max(0,Date.now()-Date.parse(frame.observedAt))
        if(age>=3000){pendingUrls.delete(next);URL.revokeObjectURL(next);continue}
        const old=url.value;url.value=next;observedAt.value=frame.observedAt;pendingUrls.delete(next)
        if(old)URL.revokeObjectURL(old)
        if(image.naturalWidth&&image.naturalHeight)emit('ratio',image.naturalWidth/image.naturalHeight)
        // Expiry follows actual displayed frames, never a separate health response.
        watchFrame(current,3000-age)
      }
    } catch {retry(current)}
    finally {painting=false}
  }
  try {
    const response=await fetch(agentApi.detectionStreamUrl(props.agentId,props.runId),{signal:controller.signal,credentials:'same-origin',cache:'no-store'})
    if(current!==generation){void response.body?.cancel();return}
    for await(const frame of detectionFrames(response,controller.signal)){
      if(current!==generation)return
      // The reader keeps draining; slow painting retains only the most recent pending frame.
      latest=frame;if(!painting)void paint()
    }
  } catch {/* The same watchdog handles connection, decode and source failures. */}
  finally {retry(current)}
}
function screenshot(){if(url.value){const link=document.createElement('a');link.href=url.value;link.download=`detection-${Date.now()}.jpg`;link.click()}}
defineExpose({screenshot})
watch(()=>[props.agentId,props.runId],()=>{reset();void connect(generation)},{immediate:true})
onUnmounted(reset)
</script>
<template>
  <div class="detection-preview">
    <img v-if="url" :src="url" alt="与行人检测框同帧的检测画面"/>
    <div v-else class="run-player-placeholder">等待新的检测画面…</div>
    <span class="detection-clock">连续检测画面 · 目标 20 帧/秒<span v-if="observedAt"> · {{formatDate(observedAt)}}</span></span>
  </div>
</template>
<style scoped>
.detection-preview{position:absolute;inset:0}.detection-preview img{display:block;width:100%;height:100%;object-fit:contain}.detection-clock{position:absolute;bottom:8px;left:8px;background:#14243acc;color:#fff;padding:4px 7px;font-size:11px;pointer-events:none}
</style>

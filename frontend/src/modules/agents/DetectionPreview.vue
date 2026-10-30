<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { agentApi } from './api'
import { formatDate } from '../../shared/ui/resource'
const props=defineProps<{agentId:string;runId:string}>()
const emit=defineEmits<{ratio:[value:number]}>()
const url=ref(''),observedAt=ref('')
let generation=0,controller:AbortController|undefined,timer:ReturnType<typeof setTimeout>|undefined,expiry:ReturnType<typeof setTimeout>|undefined
const pending=new Set<string>()
function clearFrame(){if(url.value)URL.revokeObjectURL(url.value);url.value='';observedAt.value='';clearTimeout(expiry)}
function reset(){generation++;controller?.abort();clearTimeout(timer);clearFrame();for(const value of pending)URL.revokeObjectURL(value);pending.clear()}
async function poll(current:number){
  const started=performance.now()
  try {
    const frame=await agentApi.detectionFrame(props.agentId,props.runId,controller!.signal)
    if(current!==generation)return
    if(!frame){clearFrame();return}
    const stamp=Date.parse(frame.observedAt),age=Number.isFinite(stamp)?Math.max(0,Date.now()-stamp):0
    if(age>=3000){clearFrame();return}
    if(url.value&&observedAt.value===frame.observedAt)return
    const next=URL.createObjectURL(frame.image);pending.add(next)
    const image=new Image()
    await new Promise<void>((resolve,reject)=>{image.onload=()=>resolve();image.onerror=()=>reject(new Error('Image decode failed'));image.src=next})
    if(current!==generation)return
    // Replace pixels and their burned-in boxes together, after the JPEG is decoded.
    const old=url.value;url.value=next;observedAt.value=frame.observedAt;pending.delete(next)
    if(old)URL.revokeObjectURL(old)
    if(image.naturalWidth&&image.naturalHeight)emit('ratio',image.naturalWidth/image.naturalHeight)
    clearTimeout(expiry);expiry=setTimeout(clearFrame,Math.max(0,3000-age-(performance.now()-started)))
  } catch {
    if(current===generation){clearFrame();for(const value of pending)URL.revokeObjectURL(value);pending.clear()}
  } finally {
    if(current===generation)timer=setTimeout(()=>void poll(current),Math.max(0,1000/3-(performance.now()-started)))
  }
}
function screenshot(){if(url.value){const link=document.createElement('a');link.href=url.value;link.download=`detection-${Date.now()}.jpg`;link.click()}}
defineExpose({screenshot})
watch(()=>[props.agentId,props.runId],()=>{reset();controller=new AbortController();void poll(generation)},{immediate:true})
onUnmounted(reset)
</script>
<template>
  <div class="detection-preview">
    <img v-if="url" :src="url" alt="与行人检测框同帧的检测画面"/>
    <div v-else class="run-player-placeholder">等待新的检测画面…</div>
    <span class="detection-clock">检测画面 · 目标 3 帧/秒<span v-if="observedAt"> · {{formatDate(observedAt)}}</span></span>
  </div>
</template>
<style scoped>
.detection-preview{position:absolute;inset:0}.detection-preview img{display:block;width:100%;height:100%;object-fit:contain}.detection-clock{position:absolute;bottom:8px;left:8px;background:#14243acc;color:#fff;padding:4px 7px;font-size:11px;pointer-events:none}
</style>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { NButton } from 'naive-ui'
import { api } from '../api'
import { humanError } from '../api/client'
import { safeMediaUrl } from './url'
import type { Source } from '../api/types'
import Icon from '../ui/Icon.vue'
const props=defineProps<{source:Source;autoOpen?:boolean}>()
const playback=ref<string|null>(null), error=ref(''), loading=ref(false)
let generation=0
watch(()=>[props.source.id,props.autoOpen],()=>{generation++;playback.value=null;error.value='';loading.value=false;if(props.autoOpen)void preview()},{immediate:true})
onUnmounted(()=>generation++)
async function preview(){
  const version=++generation;loading.value=true;error.value=''
  try {
    const session=await api.mediaSession(props.source.id)
    if(version!==generation)return
    const url=safeMediaUrl(session.playback_url)
    if(!url)error.value='预览地址不符合本地媒体访问规则，请检查服务配置。'
    else if(session.protocol==='webrtc')error.value='当前基础版本尚未接入 WebRTC 播放器。'
    else playback.value=url
  }catch(e){if(version===generation)error.value=humanError(e)}finally{if(version===generation)loading.value=false}
}
</script>
<template><div class="media-player"><video v-if="playback" :key="playback" :src="playback" controls preload="metadata" playsinline @error="error='浏览器无法播放当前媒体，请检查编码或媒体服务。';playback=null"/><template v-else><Icon name="video"/><span>{{error || (source.kind==='camera'?'点击预览以打开视频源':'视频已导入，可打开预览')}}</span><NButton size="small" :loading="loading" type="primary" @click="preview">{{error?'重试预览':'打开预览'}}</NButton></template></div></template>

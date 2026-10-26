<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton } from 'naive-ui'
import type Hls from 'hls.js'
import { api } from '../api'
import { humanError } from '../api/client'
import { safeMediaUrl } from './url'
import type { Source } from '../api/types'
import Icon from '../ui/Icon.vue'
const props = defineProps<{ source: Source; autoStart?: boolean; loop?: boolean }>()
const playback = ref<string | null>(null), error = ref(''), loading = ref(false)
const video = ref<HTMLVideoElement | null>(null), live = ref(false)
let generation = 0
let hls: Hls | null = null

function release() {
  hls?.destroy()
  hls = null
  if (video.value) {
    video.value.pause()
    video.value.removeAttribute('src')
    video.value.load()
  }
  playback.value = null
}

function reset() {
  generation++
  release()
  loading.value = false
  error.value = ''
}

function fail(message: string, version: number) {
  if (version !== generation) return
  reset()
  error.value = message
}

watch([() => props.source.id, () => props.autoStart], () => {
  reset()
  if (props.autoStart) void preview()
}, { flush: 'sync' })
onMounted(() => { if (props.autoStart) void preview() })
onBeforeUnmount(reset)

function mediaError(event: Event) {
  if (event.target === video.value) {
    fail('浏览器无法播放当前媒体，请检查编码或媒体服务。', generation)
  }
}

async function preview() {
  reset()
  const version = generation
  loading.value = true
  try {
    const session = await api.mediaSession(props.source.id)
    if (version !== generation) return
    const url = safeMediaUrl(session.playback_url)
    if (!url) {
      fail('预览地址不符合本地媒体访问规则，请检查服务配置。', version)
      return
    }
    if (session.protocol === 'webrtc') {
      fail('当前基础版本尚未接入 WebRTC 播放器。', version)
      return
    }
    live.value = session.protocol === 'hls'
    playback.value = url
    await nextTick()
    if (version !== generation || !video.value) return
    const element = video.value
    if (!live.value || element.canPlayType('application/vnd.apple.mpegurl')) {
      element.src = url
      if (live.value || props.autoStart) void element.play().catch(() => {})
      return
    }
    const { default: HlsPlayer } = await import('hls.js')
    if (version !== generation || video.value !== element) return
    if (!HlsPlayer.isSupported()) {
      fail('当前浏览器不支持 HLS 视频预览，请使用支持媒体扩展的浏览器。', version)
      return
    }
    const player = new HlsPlayer()
    hls = player
    player.on(HlsPlayer.Events.ERROR, (_event, data) => {
      if (!data.fatal) return
      fail(data.type === 'networkError'
        ? '视频流网络连接失败，请检查摄像头和媒体服务后重试。'
        : '视频流无法解码或播放，请检查摄像头编码和媒体服务后重试。', version)
    })
    player.on(HlsPlayer.Events.MANIFEST_PARSED, () => {
      if (version === generation) void element.play().catch(() => {})
    })
    player.loadSource(url)
    player.attachMedia(element)
  } catch (e) {
    fail(humanError(e), version)
  } finally {
    if (version === generation) loading.value = false
  }
}
</script>
<template>
  <div class="media-player">
    <video v-if="playback" :key="generation" ref="video" controls preload="metadata" playsinline :muted="live || autoStart" :autoplay="live || autoStart" :loop="loop" @error="mediaError" />
    <template v-else>
      <Icon name="video" />
      <span>{{ error || (source.kind === 'camera' ? '点击预览以打开视频源' : '视频已导入，可打开预览') }}</span>
      <NButton size="small" :loading="loading" type="primary" @click="preview">{{ error ? '重试预览' : '打开预览' }}</NButton>
    </template>
  </div>
</template>

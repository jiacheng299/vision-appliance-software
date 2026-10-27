<script setup lang="ts">
import { computed, onUnmounted, reactive } from 'vue'
import { NButton } from 'naive-ui'
import { api } from '../../shared/api'
import type { Source } from '../../shared/api/types'
import { humanError } from '../../shared/api/client'
import { useResource, formatDate, formatBytes, percent } from '../../shared/ui/resource'
import { useRealtime } from '../../shared/realtime/useRealtime'
import { safeMediaUrl } from '../../shared/media/url'
import MediaPlayer from '../../shared/media/MediaPlayer.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import Icon from '../../shared/ui/Icon.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
const {data,loading,error,refresh}=useResource(api.dashboard,{coalesce:true})
const {data:runtime}=useResource(api.runtime)
const {connected}=useRealtime(()=>void refresh())
const clock=new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'})
const used=computed(()=>runtime.value?runtime.value.disk.used_bytes/runtime.value.disk.total_bytes*100:0)
const retries=reactive<Record<string,{attempt:number;busy:boolean;error:string}>>({})
let stopped=false
async function retry(source:Source){
  retries[source.id]??={attempt:0,busy:false,error:''}
  const state=retries[source.id]!
  if(state.busy)return
  state.busy=true;state.error=''
  try{
    if(source.kind==='camera'){
      await api.testSource(source.id)
      if(stopped)return
      await refresh()
    }
    if(!stopped)state.attempt++
  }catch(e){if(!stopped)state.error=humanError(e)}
  finally{if(!stopped)state.busy=false}
}
const polling=setInterval(()=>void refresh(),15000);onUnmounted(()=>{stopped=true;clearInterval(polling)})
</script>
<template><div class="page-heading"><div><h1>快速监控看板</h1><p>实时掌握视频源、监控画面与事件动态</p></div><span class="clock">{{clock}}</span></div><ErrorBanner :error="error" @retry="refresh"/><div v-if="loading&&!data" class="loading-line" aria-label="正在加载看板"/><div class="stats-grid"><div class="panel stat"><div class="stat-icon"><Icon name="monitor" :size="27"/></div><div><div class="stat-label">视频源在线数</div><div class="stat-value">{{data?.counts.sources_online??'—'}} <small>/ {{data?.counts.sources_total??'—'}}</small></div><div class="stat-note">{{data?.counts.sources_total?'已接入视频源':'等待接入视频源'}}</div></div></div><div class="panel stat"><div class="stat-icon green"><Icon name="cpu" :size="27"/></div><div><div class="stat-label">GPU 使用率</div><div class="stat-value" style="font-size:26px">{{percent(runtime?.gpu_percent)}}</div><div class="stat-note">{{runtime?.gpu_percent==null?'尚无 GPU 采集器':'来自本机实测'}}</div></div></div><div class="panel stat"><div class="stat-icon purple"><Icon name="database" :size="27"/></div><div><div class="stat-label">存储空间</div><div class="stat-value" style="font-size:22px">{{runtime?formatBytes(runtime.disk.used_bytes):'—'}}</div><div class="stat-note">{{runtime?`共 ${formatBytes(runtime.disk.total_bytes)} · 已用 ${used.toFixed(1)}%`:'等待资源采样'}}</div></div></div><div class="panel stat"><div class="stat-icon orange"><Icon name="siren" :size="27"/></div><div><div class="stat-label">今日事件</div><div class="stat-value">{{data?.counts.today_events??'—'}}</div><div class="stat-note">{{data?.counts.active_runs??'—'}} 路任务运行中</div></div></div></div><div class="dashboard-main"><section class="panel"><div class="panel-title"><h2>实时监控画面 <small>（{{Math.min(data?.sources.length??0,4)}} 路）</small></h2><RouterLink to="/sources" style="font-size:12px">管理视频源 <span aria-hidden="true">›</span></RouterLink></div><div v-if="data?.sources.length" class="video-grid"><article v-for="source in data.sources.slice(0,4)" :key="source.id" class="source-tile"><div class="tile-media"><MediaPlayer :key="`${source.id}:${retries[source.id]?.attempt??0}`" v-if="source.status==='ready' || (source.kind==='camera' && ['online','unverified'].includes(source.status))" :source="source" auto-start loop/><img v-else-if="safeMediaUrl(source.thumbnail_url)" :src="safeMediaUrl(source.thumbnail_url)!" :alt="`${source.name} 视频缩略图`"/><Icon v-else :name="source.kind==='camera'?'camera':'film'"/><StatusBadge :value="source.status"/></div><div class="tile-footer"><RouterLink :to="`/sources/${source.id}`">{{source.name}}</RouterLink><NButton size="tiny" secondary :aria-label="`${source.kind==='camera'?'重新连接':'重新播放'}：${source.name}`" :loading="retries[source.id]?.busy || source.status==='connecting'" :disabled="retries[source.id]?.busy || source.status==='connecting' || (source.kind==='file' && source.status!=='ready')" @click="retry(source)">{{source.status==='connecting'?'连接中':source.kind==='camera'?'重新连接':'重新播放'}}</NButton></div><p v-if="retries[source.id]?.error || (source.kind==='camera' && ['failed','disconnected'].includes(source.status))" class="tile-error" role="alert">{{retries[source.id]?.error || source.error_message || '视频源未连接，请点击重新连接重试。'}}</p></article></div><EmptyState v-else icon="video" title="还没有接入视频源" description="导入本地录像或连接现场摄像头，开始准备验证素材。" large><NButton size="small" type="primary" @click="$router.push('/sources')"><template #icon><Icon name="plus" :size="16"/></template>添加视频源</NButton></EmptyState><div style="display:flex;justify-content:space-between;margin-top:14px;font-size:10px;color:#8b99ad"><span>{{connected?'状态通知已连接':'状态通知重连中，定时刷新已启用'}}</span><span>画面自动静音播放 · 录像循环播放 · 最多显示 4 路</span></div></section><div class="stack"><section class="panel"><div class="panel-title"><h2>最近事件</h2><RouterLink to="/dashboard/events" style="font-size:12px">查看全部 ›</RouterLink></div><template v-if="data?.recent_events.length"><div v-for="event in data.recent_events.slice(0,5)" :key="event.id" class="event-row"><span class="dot" style="color:#e79549;margin-top:7px"/><div><h3><RouterLink v-if="event.agent_id" :to="`/agents/${event.agent_id}/live`">{{event.event_type}}</RouterLink><template v-else>{{event.event_type}}</template></h3><p>{{event.source_name}} · {{formatDate(event.occurred_at)}}</p><p>{{event.reason}}</p></div></div></template><EmptyState v-else :title="data?.events_available===false?'报警服务尚未接入':'暂无事件记录'" :description="data?.events_available===false?'无法读取事件，不代表事件数量为零。':'接入并运行监测任务后，事件会显示在这里。'" compact icon="bell"/></section><section class="panel"><div class="panel-title"><h2>任务概览</h2><small>当前工作空间</small></div><div class="task-counts"><div>进行中<strong>{{data?.task_summary.running??'—'}}</strong></div><div>已完成<strong>{{data?.task_summary.completed??'—'}}</strong></div><div>等待中<strong>{{data?.task_summary.waiting??'—'}}</strong></div></div><p class="muted" style="font-size:10px;margin-top:13px">{{data?.runtime_available===false?'监测执行服务尚未接入，运行数量未知。':data?.data_origin==='mock'?'运行与事件来自智能体的同一模拟服务，不代表真实识别。':'运行与事件由公共执行服务提供。'}}</p></section></div></div><section class="panel quick-panel"><div class="panel-title"><h2>快捷操作</h2></div><div class="quick-grid"><RouterLink to="/sources" class="quick-card"><span class="stat-icon"><Icon name="plus"/></span><div><strong>添加视频源</strong><small>导入录像或接入摄像头</small></div></RouterLink><RouterLink to="/runtime" class="quick-card"><span class="stat-icon green"><Icon name="activity"/></span><div><strong>查看运行状态</strong><small>了解本机资源与服务</small></div></RouterLink><RouterLink to="/create" class="quick-card"><span class="stat-icon purple"><Icon name="bot"/></span><div><strong>创建监测任务</strong><small>选择视频并验证业务配置</small></div></RouterLink><RouterLink to="/settings/general" class="quick-card"><span class="stat-icon"><Icon name="settings"/></span><div><strong>系统设置</strong><small>维护运行与接入策略</small></div></RouterLink></div></section></template>

<style scoped>
.tile-media :deep(.media-player){height:100%;border-radius:0;padding:0}
.tile-media :deep(.media-player video){display:block}
.tile-media :deep(.status){pointer-events:none}
.tile-footer{gap:8px}
.tile-footer>a{min-width:0;overflow-wrap:anywhere}
.tile-footer :deep(.n-button){flex-shrink:0}
.tile-error{padding:0 10px 10px;color:#b74747;font-size:11px;overflow-wrap:anywhere}
</style>

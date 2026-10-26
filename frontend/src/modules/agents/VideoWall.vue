<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import type { Revision, Run } from './api'
import { agentApi } from './api'
import type { Source } from '../../shared/api/types'
import { actualRuns, activeStates } from './state'
import { wallGroups } from './channelSources'
import { safeMediaUrl } from '../../shared/media/url'
import MediaPlayer from '../../shared/media/MediaPlayer.vue'
import RunPlayer from './RunPlayer.vue'
import AgentStatus from './AgentStatus.vue'
const props=defineProps<{agentId:string;revision:Revision;runs:Run[];sources:Source[];runtimeAvailable:boolean}>()
const page=ref(0),capacity=ref(4),opened=ref<string[]>([]),surface=ref<HTMLElement|null>(null),error=ref('')
const groups=computed(()=>wallGroups(props.revision.config,actualRuns(props.runs)))
const all=computed(()=>groups.value.flatMap(g=>g.tiles.map(t=>({...t,groupId:g.id,groupName:g.name}))))
const pages=computed(()=>Math.max(1,Math.ceil(all.value.length/capacity.value)))
const visible=computed(()=>all.value.slice(page.value*capacity.value,(page.value+1)*capacity.value))
const pageGroups=computed(()=>groups.value.map(g=>({...g,tiles:visible.value.filter(t=>t.groupId===g.id)})).filter(g=>g.tiles.length))
watch([()=>props.agentId,()=>props.revision.id,capacity],()=>{page.value=0;opened.value=[]})
watch(page,()=>{opened.value=[]})
watch(pages,n=>{if(page.value>=n)page.value=n-1})
const source=(id:string)=>props.sources.find(s=>s.id===id)
function state(run:Run){return !props.runtimeAvailable||(['running','reconnecting'].includes(run.state)&&(!run.last_heartbeat_at||Date.now()-Date.parse(run.last_heartbeat_at)>30000))?'unknown':run.state}
async function fullscreen(){try{await surface.value?.requestFullscreen()}catch{error.value='当前浏览器无法进入全屏。'}}
</script>
<template>
  <section ref="surface" class="panel video-wall" aria-label="视频监控墙">
    <div class="panel-title"><div><h2>视频监控墙 <small>{{all.length}} 路画面 · 按通道分组</small></h2><p class="muted">同组共用监测规则；预览视频不会启动分析。未运行画面只显示源预览。</p></div><div class="agent-actions"><NSelect v-model:value="capacity" :options="[{label:'每页1画面',value:1},{label:'每页4画面',value:4},{label:'每页9画面',value:9}]" aria-label="监控墙画面数量" style="width:140px"/><NButton size="small" @click="opened=visible.map(t=>t.key)">打开本页画面</NButton><NButton size="small" @click="opened=[]">关闭本页画面</NButton><NButton size="small" @click="fullscreen">全屏监控墙</NButton></div></div>
    <p v-if="error" class="error-banner">{{error}}</p>
    <section v-for="group in pageGroups" :key="group.id" class="wall-group"><h3>{{group.name}} <small>同一套规则 · 各视频独立分析与报警</small></h3>
      <div class="wall-grid" :class="{'wall-nine':capacity===9,'wall-single':capacity===1}"><article v-for="tile in group.tiles" :key="tile.key" class="wall-tile">
        <div class="wall-tile-heading"><strong>{{source(tile.binding.source_id)?.name??tile.binding.source_id}}</strong><AgentStatus v-if="tile.run" :value="state(tile.run)"/><span v-else class="status">未启动监测</span></div>
        <small v-if="tile.run">实际配置 v{{tile.run.revision_no}} · Run {{tile.run.id}}</small><small v-else>所选配置中的视频源 · 仅预览</small>
        <template v-if="opened.includes(tile.key)">
          <RunPlayer v-if="tile.run" :key="tile.run.id" :identity="`${tile.run.id}:${tile.run.state}:${runtimeAvailable}`" :agent-id="agentId" :load="()=>agentApi.playback(agentId,tile.run!.id)" :is-live="tile.run.source_kind==='camera'&&state(tile.run)==='running'"/>
          <MediaPlayer v-else-if="source(tile.binding.source_id)" :source="source(tile.binding.source_id)!" auto-start/>
          <p v-else class="wall-unavailable">视频源已归档或当前不可用，历史引用保留。</p>
          <p v-if="tile.run&&!activeStates.has(tile.run.state)" class="muted">已结束运行的回放入口，非实时分析。</p>
          <NButton size="tiny" @click="opened=opened.filter(key=>key!==tile.key)">关闭画面</NButton>
        </template>
        <button v-else class="wall-poster" :aria-label="`打开画面：${source(tile.binding.source_id)?.name??tile.binding.source_id}`" @click="opened.push(tile.key)"><img v-if="safeMediaUrl(source(tile.binding.source_id)?.thumbnail_url??null)" :src="safeMediaUrl(source(tile.binding.source_id)?.thumbnail_url??null)!" alt="视频源缩略图"/><span>打开画面</span></button>
      </article></div>
    </section>
    <p v-if="!all.length" class="muted">请先在通道中添加视频源。</p>
    <div v-if="pages>1" class="wall-pagination"><NButton :disabled="page===0" @click="page--">上一页</NButton><span>{{page+1}} / {{pages}} 页</span><NButton :disabled="page+1>=pages" @click="page++">下一页</NButton></div>
  </section>
</template>

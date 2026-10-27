<script setup lang="ts">
import { newId } from '../../shared/ids'
import { computed, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { NButton, NDrawer, NDrawerContent, NInput, NSelect } from 'naive-ui'
import type { Source } from '../../shared/api/types'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
import { humanError } from '../../shared/api/client'
import { agentApi, type AgentDetail } from './api'
import { emptyConfig, newChannel } from './draft'
import { MAX_CHANNEL_SOURCES, setChannelSources } from './channelSources'

const props=defineProps<{sources:Source[];sourcesError:string}>()
const emit=defineEmits<{close:[];created:[agent:AgentDetail]}>()
const name=ref(''),description=ref(''),selectedSources=ref<string[]>([]),creating=ref(false),error=ref('')
const dirty=computed(()=>!!name.value||!!description.value||selectedSources.value.length>0)
const config=computed(()=>{
  const result=emptyConfig()
  if(selectedSources.value.length){const channel=newChannel();channel.name='通道 1';setChannelSources(channel,selectedSources.value);result.channels=[channel]}
  return result
})
let token='',encodedBody='',completed=false
function mayClose(){return completed||(!creating.value&&(!dirty.value||window.confirm('草稿尚未创建，确定放弃已填写的内容？')))}
function close(){if(mayClose())emit('close')}
onBeforeRouteLeave(()=>mayClose())
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value||creating.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>window.removeEventListener('beforeunload',beforeUnload))
async function create(){
  if(creating.value)return
  if(!name.value.trim()){error.value='请填写智能体名称，例如“仓库火灾探测”。';return}
  if(selectedSources.value.length>MAX_CHANNEL_SOURCES){error.value='一个通道最多选择16个视频源。';return}
  const body={name:name.value.trim(),description:description.value.trim(),config:config.value}
  const encoded=JSON.stringify(body)
  if(!token||encodedBody!==encoded){token=newId();encodedBody=encoded}
  creating.value=true;error.value=''
  try{const agent=await agentApi.create(body,token);completed=true;emit('created',agent)}
  catch(e){error.value=humanError(e)}finally{creating.value=false}
}
</script>
<template>
  <NDrawer :show="true" placement="right" width="min(100vw, max(640px, 50vw))" class="agent-create-drawer" :mask-closable="!creating" :close-on-esc="!creating" @update:show="show=>{if(!show)close()}">
    <NDrawerContent title="新建智能体草稿" :closable="!creating" @close="close">
      <div class="agent-create-intro"><span class="agent-create-eyebrow">智能体创建</span><h2>智能体基础配置</h2><p>配置智能体基本信息及首个通道的视频源，监测规则与检测区域在配置页设置。</p></div>
      <ol class="agent-create-steps" aria-label="配置层级"><li><strong>智能体</strong><span>监测业务定义</span></li><li><strong>通道</strong><span>共享监测规则</span></li><li><strong>视频源</strong><span>监控直播或录像</span></li></ol>
      <form id="agent-create-form" class="agent-create-form" @submit.prevent="create">
        <section class="agent-create-section"><h3>基本信息</h3><div class="field"><label for="agent-name">智能体名称 <span class="required-label">必填</span></label><NInput :input-props="{id:'agent-name'}" v-model:value="name" :maxlength="160" :disabled="creating" placeholder="例如：仓库火灾探测" autofocus/></div><div class="field"><label for="agent-description">用途说明 <span class="muted">选填</span></label><NInput :input-props="{id:'agent-description'}" v-model:value="description" type="textarea" :autosize="{minRows:3,maxRows:6}" :maxlength="2000" :disabled="creating" placeholder="例如：监测仓库内的烟雾和明火，发现异常及时报警"/></div></section>
        <section class="agent-create-section"><h3>首个通道</h3><p class="hint">同一通道内的视频源共享监测规则，分别执行分析并生成报警。</p><div class="field"><label id="agent-create-sources">视频源 <span class="muted">支持多选，可在配置页补充</span></label><NSelect v-model:value="selectedSources" multiple filterable :options="sources.map(s=>({label:`${s.name} · ${s.kind==='camera'?'监控直播':'录像文件'}`,value:s.id}))" :disabled="creating" clearable aria-labelledby="agent-create-sources" aria-label="创建时选择视频源" placeholder="选择摄像头直播或录像文件"/><p class="hint">已选择 {{selectedSources.length}} / {{MAX_CHANNEL_SOURCES}} 个视频源。其他通道在配置页添加。</p><p v-if="props.sourcesError" class="hint">视频源列表加载失败。可创建空草稿，视频源在配置页补充。</p></div></section>
        <ErrorBanner :error="error" :retryable="false"/>
      </form>
      <template #footer><div class="agent-create-footer"><p>保存为草稿，不启动视频分析。</p><div class="agent-actions"><NButton :disabled="creating" @click="close">取消</NButton><NButton type="primary" attr-type="submit" form="agent-create-form" :loading="creating" :disabled="creating">创建并配置</NButton></div></div></template>
    </NDrawerContent>
  </NDrawer>
</template>

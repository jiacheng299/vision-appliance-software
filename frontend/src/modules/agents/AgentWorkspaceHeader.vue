<script setup lang="ts">
import { NButton, NSelect } from 'naive-ui'
import Icon from '../../shared/ui/Icon.vue'
import { formatDate } from '../../shared/ui/resource'
import AgentStatus from './AgentStatus.vue'
import type { AgentDetail, Revision } from './api'
defineProps<{agent:AgentDetail;revision:Revision;status:string;disabled:boolean;loading:boolean;canWrite:boolean}>()
const emit=defineEmits<{select:[id:string];refresh:[];rename:[];archive:[]}>()
const sections=[
  {key:'live',label:'画面与报警',description:'查看各路实况与系统事件',icon:'monitor'},
  {key:'config',label:'监测配置',description:'视频来源、规则与监测区域',icon:'sliders'},
  {key:'history',label:'版本与运行历史',description:'追溯配置变更与运行记录',icon:'clock'},
  {key:'events',label:'人工核查',description:'当前版本暂未开放',icon:'shield',disabled:true},
  {key:'reports',label:'结果导出',description:'选择运行并跟踪导出进度',icon:'disk'},
]
</script>
<template>
  <header class="agent-workspace-header">
    <div class="agent-heading-card">
      <div class="agent-heading-main"><RouterLink class="agent-back-link" to="/agents">‹ 返回智能体列表</RouterLink><div class="agent-heading-title"><span class="agent-heading-icon"><Icon name="bot" :size="26"/></span><div><span class="agent-eyebrow">智能体工作空间</span><h1>{{agent.name}}</h1></div></div><p>{{agent.description||'管理监测需求，查看画面、报警与实际运行版本。'}}</p></div>
      <div class="agent-header-actions"><NButton :loading="loading" :disabled="disabled" @click="emit('refresh')">刷新</NButton><template v-if="canWrite"><NButton v-if="!agent.archived_at" :disabled="disabled" @click="emit('rename')">修改名称</NButton><NButton :disabled="disabled" @click="emit('archive')">{{agent.archived_at?'恢复智能体':'归档'}}</NButton></template></div>
    </div>
    <div class="agent-overview-grid">
      <div class="agent-overview-cell"><span class="agent-meta-label">当前状态</span><AgentStatus :value="status"/></div>
      <div class="agent-overview-cell agent-version-cell"><label class="agent-meta-label">查看配置版本</label><NSelect :value="revision.id" :options="agent.revisions.map(r=>({label:`v${r.revision_no} · ${r.state==='published'?'已发布':'草稿'}`,value:r.id}))" :disabled="disabled" aria-label="选择配置版本" @update:value="emit('select',$event)"/></div>
      <div class="agent-overview-cell"><span class="agent-meta-label">监测通道</span><strong>{{revision.config.channels?.length??0}} <small>路配置</small></strong></div>
      <div class="agent-overview-cell"><span class="agent-meta-label">最后保存</span><span class="agent-meta-date">{{formatDate(revision.updated_at)}}</span></div>
    </div>
    <nav class="agent-section-nav" aria-label="智能体详情导航">
      <template v-for="item in sections" :key="item.key">
        <button v-if="item.disabled" class="agent-section-link unavailable" disabled title="人工核查当前版本暂未开放"><Icon :name="item.icon" :size="20"/><span><strong>{{item.label}}</strong><small>{{item.description}}</small></span></button>
        <RouterLink v-else class="agent-section-link" :to="`/agents/${agent.id}/${item.key}`"><Icon :name="item.icon" :size="20"/><span><strong>{{item.label}}</strong><small>{{item.description}}</small></span></RouterLink>
      </template>
    </nav>
  </header>
</template>

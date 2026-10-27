<script setup lang="ts">
import { api } from '../../shared/api'
import { useResource,formatDate } from '../../shared/ui/resource'
import EmptyState from '../../shared/ui/EmptyState.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
const {data,error,loading,refresh}=useResource(api.events)
</script>
<template><div class="page-heading"><div><h1>事件记录</h1><p>查看视频监测事件与来源信息</p></div><RouterLink to="/dashboard">返回看板</RouterLink></div><ErrorBanner :error="error" @retry="refresh"/><section class="panel"><div class="panel-title"><h2>最近事件 <small>（{{data?.items.length??0}}）</small></h2></div><div v-if="loading" class="loading-line"/><div v-if="data?.items.length" class="table-wrap"><table><thead><tr><th>事件</th><th>视频源</th><th>发生时间</th><th>触发依据</th><th>证据状态</th></tr></thead><tbody><tr v-for="event in data.items" :key="event.id"><td><RouterLink v-if="event.agent_id" :to="`/agents/${event.agent_id}/live`">{{event.event_type}}</RouterLink><template v-else>{{event.event_type}}</template></td><td>{{event.source_name}}</td><td>{{formatDate(event.occurred_at)}}</td><td class="wrap">{{event.reason}}</td><td>{{event.evidence_status}}</td></tr></tbody></table></div><EmptyState v-else large :title="data?.available===false?'报警服务尚未接入':'暂无事件记录'" description="可在智能体详情查看各次运行的完整事件。" icon="bell"/></section></template>

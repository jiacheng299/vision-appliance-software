<script setup lang="ts">
import { ref } from 'vue'
import { NButton } from 'naive-ui'
import { agentApi, type AgentDetail, type Comparison, type Revision, type Run } from './api'
import { activeStates, agentError, label, received, requestKey } from './state'
import { formatDate } from '../../shared/ui/resource'
import AgentStatus from './AgentStatus.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import ErrorBanner from '../../shared/ui/ErrorBanner.vue'
const props=defineProps<{agent:AgentDetail;runs:Run[];canWrite:boolean;runtimeAvailable:boolean;selectedRevisionId:string}>()
const emit=defineEmits<{select:[id:string];view:[run:Run];retry:[run:Run];retest:[revision:Revision]}>()
const busy=ref(''),error=ref(''),comparison=ref<Comparison|null>(null)
const metrics:Record<string,string>={system_events:'系统事件',correct:'已核查正确',false_positive:'已核查误报',missed:'人工漏报',missing_evidence:'证据不完整'}
async function retest(run:Run){
  if(busy.value)return
  busy.value=run.id;error.value='';const scope=`retest.${props.agent.id}`,body={baseline_run_id:run.id,row_version:props.agent.row_version}
  try{const revision=await agentApi.retest(props.agent,run.id,requestKey(scope,body));received(scope);emit('retest',revision)}catch(e){error.value=agentError(e)}finally{busy.value=''}
}
async function compare(run:Run){
  if(!run.baseline_run_id||busy.value)return
  busy.value=run.id;error.value=''
  try{comparison.value=await agentApi.comparison(props.agent.id,run.baseline_run_id,run.id)}catch(e){error.value=agentError(e)}finally{busy.value=''}
}
</script>
<template>
  <section class="panel"><h2>配置版本</h2><div class="table-wrap"><table><thead><tr><th>版本</th><th>状态</th><th>来源</th><th>更新时间</th><th>操作</th></tr></thead><tbody><tr v-for="r in agent.revisions" :key="r.id"><td>v{{r.revision_no}}</td><td><AgentStatus :value="r.state"/></td><td>{{r.baseline_run_id?'关联复测基线':r.base_revision_id?`复制自 v${agent.revisions.find(base=>base.id===r.base_revision_id)?.revision_no??'?'}`:'初始版本'}}</td><td>{{formatDate(r.updated_at)}}</td><td><NButton size="small" @click="emit('select',r.id)">{{selectedRevisionId===r.id?'正在查看':'查看配置'}}</NButton></td></tr></tbody></table></div>
    <h2 class="agent-section-title">逐路运行记录</h2><ErrorBanner :error="error" :retryable="false"/><p v-if="!runtimeAvailable" class="notice">运行服务不可用，当前记录可能是缓存。暂不能进行重跑或建立复测。</p>
    <EmptyState v-if="!runs.length" title="暂无可用运行记录" description="草稿或已发布配置不等于一次运行，只有运行服务受理后才会产生 Run。"/>
    <article v-for="run in runs" :key="run.id" class="run-history-row"><div class="panel-title"><h3>{{run.channel_name}} · 实际 v{{run.revision_no}}</h3><AgentStatus :value="runtimeAvailable?run.state:'unknown'"/></div><p class="run-meta">{{run.id}}</p><p>开始 {{formatDate(run.started_at??null)}} · 结束 {{formatDate(run.ended_at??null)}}</p><p>{{run.message}}</p><p v-if="run.error_code" class="muted">原因编号 {{run.error_code}}</p><p v-if="run.baseline_run_id" class="muted">复测基线 {{run.baseline_run_id}}</p><details><summary>查看这次运行实际使用的配置</summary><div v-for="c in run.config_snapshot.channels?.filter(c=>c.channel_id===run.channel_id)" :key="c.channel_id"><p>需求：{{c.requirement_text}}</p><p>视频源 {{c.source_id}} · {{c.target}} / {{c.rule}} · 时长 {{c.duration_seconds??'未设置'}} 秒</p><p>模型 {{c.capability_ref?.model_id}} / {{c.capability_ref?.model_version}} · 模板 {{c.capability_ref?.template_id}} / {{c.capability_ref?.template_version}}</p></div></details><div class="agent-actions"><NButton size="small" @click="emit('view',run)">画面 / 回放</NButton><template v-if="canWrite&&!agent.archived_at"><NButton size="small" :disabled="activeStates.has(run.state)||!runtimeAvailable||!!busy" @click="emit('retry',run)">用此版本重新运行</NButton><NButton size="small" :disabled="activeStates.has(run.state)||!runtimeAvailable||!!busy" :loading="busy===run.id" @click="retest(run)">创建复测草稿</NButton></template><NButton v-if="run.baseline_run_id" size="small" :disabled="!!busy" @click="compare(run)">查看基线对照</NButton></div></article>
  </section>
  <section v-if="comparison" class="panel agent-section-title"><h2>基线与复测对照</h2><p class="notice">{{comparison.limitation}} {{comparison.comparable?'同范围原始计数可供核查。':'不具备直接比较效果的条件。'}}</p><p class="run-meta">基线 {{comparison.baseline_run_id}} / 复测 {{comparison.candidate_run_id}}</p><table><thead><tr><th>指标</th><th>基线</th><th>复测</th></tr></thead><tbody><tr v-for="(name,key) in metrics" :key="key"><td>{{name}}</td><td>{{comparison.baseline[key]??'未知'}}</td><td>{{comparison.candidate[key]??'未知'}}</td></tr></tbody></table><p class="muted">没有完整真值与匹配规则时，不计算准确率或召回率。人工漏报不计入系统检出。</p></section>
</template>

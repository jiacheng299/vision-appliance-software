<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { Check,Grid2X2,Search,UserRound,FileText,Info } from 'lucide-vue-next'
import { NButton } from 'naive-ui'
import type { AgentTemplate,TemplateRevision,TemplateMatchResult } from '../agents/templatesApi'
import { templatesApi } from '../agents/templatesApi'
import { label } from '../agents/state'
import { humanError } from '../../shared/api/client'
const props=defineProps<{templates:AgentTemplate[];selectedId:string|null;version?:TemplateRevision|null;disabled?:boolean}>()
const emit=defineEmits<{select:[id:string];matched:[id:string]}>()
const query=ref('')
const available=computed(()=>props.templates.filter(t=>(!t.archived_at&&t.published_revision?.state==='published')||(props.disabled&&t.id===props.selectedId)))
const filtered=computed(()=>available.value.filter(t=>(`${t.name} ${t.description} ${t.published_revision?.config.summary??''}`).toLowerCase().includes(query.value.trim().toLowerCase())))
const selected=computed(()=>props.templates.find(t=>t.id===props.selectedId))
const version=computed(()=>props.version??selected.value?.published_revision)
const conditions=computed(()=>Object.fromEntries((version.value?.config.parameters??[]).map(p=>[p.key,p.value])))
const businessLabels:Record<string,string>={person:'人员',vehicle:'车辆',fire:'火源',smoke:'烟雾',absence:'人员在岗',intrusion:'区域入侵',presence:'目标出现',dwell:'区域停留'}
function business(value:unknown){const key=String(value??'');return businessLabels[key]??(label(key)||'由模板指定')}

// 自然语言匹配：只负责选择模板，成功后仍走既有的模板+固定版本路径。
const mode=ref<'manual'|'natural'>('manual')
const requirement=ref('')
const matchedText=ref('')
const matcherConfigured=ref<boolean|null>(null)
const matcherStatusError=ref('')
const matching=ref(false)
const matchOutcome=ref<TemplateMatchResult|null>(null)
const matchError=ref('')
const matchStale=computed(()=>!!matchOutcome.value&&requirement.value.trim()!==matchedText.value)
const matchTarget=computed(()=>matchOutcome.value?.template_id?props.templates.find(t=>t.id===matchOutcome.value!.template_id):undefined)
onMounted(async()=>{
  try{matcherConfigured.value=(await templatesApi.matcherStatus()).configured}
  catch{matcherConfigured.value=false;matcherStatusError.value='无法读取大模型配置状态，可在系统设置的大模型接口中检查。'}
})
function switchMode(value:'manual'|'natural'){if(props.disabled)return;mode.value=value;matchError.value=''}
async function runMatch(){
  const text=requirement.value.trim()
  if(!text||matching.value)return
  matching.value=true;matchError.value='';matchOutcome.value=null
  try{
    const result=await templatesApi.match({requirement_text:text})
    matchOutcome.value=result;matchedText.value=text
    if(result.status==='matched'&&result.template_id){
      if(props.selectedId&&props.selectedId!==result.template_id
          &&!window.confirm('将替换当前所选模板，已填写的条件与视频源配置会被重置，确定继续？'))return
      emit('matched',result.template_id)
    }
  }catch(problem){
    const message=humanError(problem)
    matchError.value=message.includes('配置')||/503|401/.test(message)
      ? `${message}（系统设置 → 大模型接口）`
      : message
  }finally{matching.value=false}
}
</script>
<template>
  <section class="template-selection">
    <h2>第一步，确定使用的模板</h2><p class="selection-subtitle">两种选择方式，最终都使用已有的已发布模板</p>
    <div class="selection-methods" role="radiogroup" aria-label="模板选择方式">
      <button type="button" :class="['selection-method',{selected:mode==='manual'}]" role="radio" :aria-checked="mode==='manual'" :disabled="disabled" @click="switchMode('manual')"><Grid2X2 :size="26"/><span><strong>手动选择</strong><small>从已发布模板中选择适合的监测能力</small></span><Check v-if="mode==='manual'" :size="18"/></button>
      <button type="button" :class="['selection-method',{selected:mode==='natural'}]" role="radio" :aria-checked="mode==='natural'" aria-label="自然语言匹配" :disabled="disabled" @click="switchMode('natural')"><FileText :size="26"/><span><strong>自然语言匹配</strong><small>输入文字需求，自动匹配已发布的模板</small></span><Check v-if="mode==='natural'" :size="18"/></button>
    </div>

    <section v-if="mode==='natural'" class="selection-natural" aria-label="自然语言匹配面板">
      <label class="selection-search"><FileText :size="17"/><input v-model="requirement" type="text" maxlength="2000" :disabled="disabled||matching" aria-label="监测需求" placeholder="例如：监测人员在岗，连续无人30秒报警" @keyup.enter="runMatch"/></label>
      <div class="selection-actions">
        <NButton type="primary" size="small" :loading="matching" :disabled="disabled||!requirement.trim()||matching" aria-label="开始匹配模板" @click="runMatch">匹配模板</NButton>
        <small v-if="matcherConfigured===false" class="selection-hint" role="status">{{ matcherStatusError||'自然语言匹配需要先在系统设置的大模型接口中配置 Kimi 或 DeepSeek 官方 API Key。' }}<RouterLink to="/settings/llm">前往配置</RouterLink></small>
      </div>
      <p v-if="matchError" class="selection-match-error" role="alert">{{ matchError }}</p>
      <p v-if="matchStale" class="selection-hint" role="status">需求已修改，当前匹配结果对应旧文本；请重新匹配，或保持已选模板继续。</p>

      <article v-if="matchOutcome&&matchOutcome.status==='matched'&&matchTarget" class="selection-outcome ok" aria-label="匹配结果">
        <h3>已匹配模板</h3>
        <div class="selection-detail-title"><span class="selection-icon"><UserRound :size="27"/></span><div><h2>{{ matchTarget.name }}</h2><span class="selection-version">模板版本 v{{ matchTarget.published_revision?.revision_no }} · 已发布 · 置信度 {{ Math.round(matchOutcome.confidence*100) }}%（模型自评）</span></div></div>
        <p class="selection-subtitle">{{ matchOutcome.reason }}</p>
        <p class="selection-info"><Info :size="17"/>已固定到该发布版本；模板日后发布新版本不会影响本任务。匹配只完成模板选择，不代表已验证可执行，能否启动以第三步验证结果为准。</p>
      </article>
      <article v-else-if="matchOutcome&&matchOutcome.status==='no_match'" class="selection-outcome blocked" aria-label="匹配结果">
        <h3>没有可完整覆盖该需求的已发布模板</h3>
        <p class="selection-subtitle">{{ matchOutcome.reason }}</p>
        <ul v-if="matchOutcome.uncovered_requirements.length" class="selection-uncovered"><li v-for="item in matchOutcome.uncovered_requirements" :key="item">{{ item }}</li></ul>
        <p class="selection-info"><Info :size="17"/>本次仅做了模板比对，系统未执行任何分析，也不会按猜测启动任务。你可以修改需求重新匹配、切回手动选择模板，或到智能体管理新建并发布模板。</p>
      </article>
    </section>

    <div v-else class="selection-columns">
      <section class="selection-library">
        <label class="selection-search"><Search :size="17"/><input v-model="query" type="search" aria-label="搜索模板" placeholder="搜索模板名称或监测能力"/></label>
        <h3>选择已有模板 <small>（{{filtered.length}} 个）</small></h3>
        <div class="selection-list" role="listbox" aria-label="已发布模板">
          <button v-for="t in filtered" :key="t.id" type="button" role="option" :aria-selected="selectedId===t.id" :aria-label="`选择模板：${t.name}`" :disabled="disabled" :class="['selection-template',{selected:selectedId===t.id}]" @click="emit('select',t.id)">
            <span class="selection-icon"><UserRound :size="25"/></span><span class="selection-template-copy"><strong>{{t.name}}</strong><span class="selection-version">v{{selectedId===t.id&&version?version.revision_no:t.published_revision?.revision_no}} · 已发布</span><small>{{t.description||t.published_revision?.config.summary||'查看模板详情及检测条件'}}</small></span><Check v-if="selectedId===t.id" class="selection-check" :size="20"/>
          </button>
          <p v-if="!filtered.length" class="selection-empty">{{available.length?'没有匹配的模板，请尝试其他关键词。':'暂无已发布模板，请先到智能体管理发布模板。'}}</p>
        </div>
        <p class="selection-subtitle">共 {{available.length}} 个已发布模板</p>
      </section>
      <aside class="selection-detail" aria-label="模板详情">
        <h3>模板详情</h3>
        <template v-if="version&&selected">
          <div class="selection-detail-title"><span class="selection-icon"><UserRound :size="27"/></span><div><h2>{{selected.name}}</h2><span class="selection-version">模板版本 v{{version.revision_no}} · 已发布</span></div></div>
          <p class="selection-subtitle">{{version.config.summary||selected.description}}</p>
          <dl><div><dt>监测目标</dt><dd>{{business(conditions.target??version.config.default_target)}}</dd></div><div><dt>监测规则</dt><dd>{{business(conditions.rule??version.config.default_rule)}}</dd></div><div v-if="conditions.duration_seconds!=null"><dt>默认确认时长</dt><dd>{{conditions.duration_seconds}} 秒</dd></div><div><dt>开放配置项</dt><dd>{{version.config.parameters?.length??0}} 项</dd></div><div><dt>支持多路视频</dt><dd>各路独立监测与报警</dd></div></dl>
          <p class="selection-info"><Info :size="17"/>下一步可配置视频源、监测区域和模板开放的条件值。</p>
        </template>
        <p v-else class="selection-empty">从左侧选择一个模板，查看其监测能力与条件。</p>
      </aside>
    </div>
  </section>
</template>
<style scoped>
.template-selection{padding:24px;background:#fff;border:1px solid #e5ebf4;border-radius:10px}.template-selection h2{font-size:19px;margin:0 0 7px;color:#17233b}.template-selection h3{font-size:14px;margin:17px 0 12px}.selection-subtitle{font-size:12px;color:#7b889f;line-height:1.7;margin:0 0 15px}.selection-methods{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:20px 0}.selection-method{display:flex;align-items:center;gap:16px;padding:22px;text-align:left;font:inherit;color:#34445f;background:#fff;border:1px solid #e2e8f2;border-radius:8px}.selection-method.selected{border-color:#397bff;background:#f3f7ff;color:#2367ed}.selection-method span{flex:1}.selection-method strong{display:block;font-size:15px}.selection-method small{display:block;color:#7b889f;font-size:12px;margin-top:8px}.selection-method:disabled{cursor:not-allowed;opacity:.75}.selection-natural{border:1px solid #e4eaf3;border-radius:8px;padding:18px;display:grid;gap:12px;align-content:start}.selection-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.selection-hint{font-size:12px;color:#7b889f;line-height:1.7}.selection-hint a{margin-left:6px}.selection-match-error{padding:10px 12px;border:1px solid #f3d9d9;background:#fff6f5;color:#b75151;border-radius:6px;font-size:12px}.selection-outcome{border:1px solid #d5e2f5;border-left:3px solid #2367ed;border-radius:6px;padding:14px 16px;background:#f7faff}.selection-outcome h3{margin:0 0 6px;font-size:14px}.selection-outcome.blocked{border-color:#ecd9b8;border-left-color:#d88c31;background:#fffcf5}.selection-outcome .selection-info{margin-bottom:0}.selection-uncovered{margin:0 0 10px;padding-left:18px;font-size:12px;color:#8a6a2f;line-height:1.9}.selection-columns{display:grid;grid-template-columns:1.05fr 1fr;gap:24px}.selection-search{display:flex;gap:10px;align-items:center;border:1px solid #dfe7f1;padding:10px 12px;border-radius:6px;color:#8a98ad}.selection-search input{border:0;outline:0;background:transparent;min-width:0;width:100%;font:inherit;color:#263951}.selection-list{min-height:240px;display:grid;align-content:start;gap:10px}.selection-template{display:flex;align-items:center;gap:15px;padding:17px;width:100%;text-align:left;border:1px solid #e2e8f2;border-radius:7px;background:#fff;font:inherit;color:#1d2c46;cursor:pointer}.selection-template.selected{background:#eef5ff;border-color:#b9d0ff;box-shadow:inset 3px 0 #2367ed}.selection-template:disabled{cursor:default}.selection-icon{display:grid;place-items:center;flex:none;width:48px;height:48px;border-radius:8px;background:#edf4ff;color:#2367ed}.selection-template-copy{flex:1;min-width:0}.selection-template-copy strong{font-size:15px;overflow-wrap:anywhere}.selection-template-copy small{display:block;color:#7b889f;font-size:12px;margin-top:9px;line-height:1.5}.selection-version{display:inline-block;background:#e9f8ee;color:#2c975d;font-size:11px;padding:4px 8px;border-radius:14px;margin:5px}.selection-check{color:#2367ed;flex:none}.selection-detail{border:1px solid #e4eaf3;border-radius:8px;padding:18px}.selection-detail h3{margin-top:0}.selection-detail-title{display:flex;align-items:center;gap:14px;margin:20px 0 8px}.selection-detail-title h2{font-size:19px;overflow-wrap:anywhere}.selection-detail dl{margin:18px 0}.selection-detail dl>div{display:grid;grid-template-columns:110px 1fr;gap:14px;padding:12px 0;border-top:1px solid #edf1f6;font-size:12px;line-height:1.6}.selection-detail dt{color:#7b889f}.selection-detail dd{margin:0;color:#34445f;overflow-wrap:anywhere}.selection-info{display:flex;gap:8px;padding:12px;background:#f0f6ff;color:#3974d9;font-size:12px;line-height:1.6;border-radius:6px}.selection-info svg{flex:none}.selection-empty{padding:28px 8px;color:#7b889f;font-size:13px;line-height:1.8}.selection-template:focus-visible,.selection-method:focus-visible{outline:3px solid #94b7ff;outline-offset:2px}@media(max-width:800px){.selection-methods,.selection-columns{grid-template-columns:1fr}.template-selection{padding:16px}.selection-list{min-height:0}}
</style>

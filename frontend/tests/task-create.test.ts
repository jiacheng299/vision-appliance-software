import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { newGroup, selectSources, bindings, copyForNewTask, cleanTaskName, draftIssue, retryKey } from '../src/modules/task-create/state'
const m=vi.hoisted(()=>({route:{query:{}},router:{replace:vi.fn(),push:vi.fn()},detail:vi.fn(),create:vi.fn(),validate:vi.fn(),confirm:vi.fn(),submit:vi.fn(),operation:vi.fn(),plan:vi.fn(),templates:vi.fn(),get:vi.fn(),catalog:vi.fn(),sources:vi.fn()}))
vi.mock('vue-router',()=>({useRoute:()=>m.route,useRouter:()=>m.router,onBeforeRouteLeave:vi.fn()}))
vi.mock('../src/shared/environment',()=>({environment:ref({data_origin:'mock'}),loadEnvironment:vi.fn()}))
vi.mock('../src/shared/api/client',()=>({client:{get:m.get},humanError:()=> '服务不可用'}))
vi.mock('../src/modules/model-management/api',()=>({modelApi:{plan:m.plan,templates:m.templates},memberError:()=> '服务不可用'}))
vi.mock('../src/modules/agents/api',()=>({listAgentSources:m.sources,agentApi:{catalog:m.catalog,list:async()=>({items:[]}),create:m.create,detail:m.detail,validate:m.validate,confirm:m.confirm,submit:m.submit,operation:m.operation,seed:vi.fn(),validation:vi.fn()}}))
vi.mock('naive-ui',async()=>{
 const {defineComponent}=await import('vue')
 return {
 NButton:defineComponent({props:['disabled','loading','type'],template:'<button :disabled="disabled||loading"><slot/></button>'}),
 NInput:defineComponent({props:['value'],emits:['update:value'],template:'<input :value="value" @input="$emit(\'update:value\',$event.target.value)"/>'}),
 NInputNumber:defineComponent({props:['value'],emits:['update:value'],template:'<input type="number" :value="value" @input="$emit(\'update:value\',$event.target.value===\'\'?null:Number($event.target.value))"/>'}),
 NCheckbox:defineComponent({props:['checked','disabled'],emits:['update:checked'],template:'<label><input type="checkbox" :checked="checked" :disabled="disabled" @change="$emit(\'update:checked\',$event.target.checked)"/><slot/></label>'}),
 NSelect:defineComponent({name:'NSelect',props:['value','options','multiple','disabled'],emits:['update:value'],template:'<select :disabled="disabled" :value="value" :multiple="multiple"><option v-for="o in options" :key="o.value" :value="o.value">{{o.label}}</option></select>'})}
})
import TaskCreatePage from '../src/modules/task-create/TaskCreatePage.vue'
const reference={model_id:'m',model_version:'1',template_id:'t',template_version:'1'}
const preset={id:'preset-dwell',name:'人员区域停留检测',target:'person',rule:'dwell',capability_ref:reference,requires_region:true,requires_duration:true,limitations:['mock only']}
const cap={items:[{name:'mock',reference,targets:['person'],rules:['dwell'],requires_region:['dwell'],requires_duration:['dwell'],limitations:['mock only']}],fingerprint:'fp',data_origin:'mock'}
let stored:Record<string,unknown>,revision:Record<string,unknown>
const wrappers:ReturnType<typeof mount>[]=[]
beforeEach(()=>{
 vi.clearAllMocks();sessionStorage.clear();m.route.query={}
 m.sources.mockResolvedValue([{id:'s',name:'模拟录像',kind:'file',width:1920,height:1080,duration_ms:100000,status:'ready'}]);m.catalog.mockResolvedValue(cap);m.templates.mockResolvedValue({items:[preset],fingerprint:'fp',data_origin:'mock'})
 m.create.mockImplementation(async body=>{revision={id:'r',agent_id:'a',row_version:1,state:'draft',config:body.config};stored={id:'a',name:body.name,description:body.description,row_version:1,latest_revision:revision};return stored});m.detail.mockImplementation(async()=>stored);m.get.mockImplementation(async()=>({data:revision}))
 m.validate.mockResolvedValue({id:'v',revision_id:'r',verdict:'executable',config_hash:'hash',capability_fingerprint:'fp',missing_conditions:[],unsupported_conditions:[],evidence_limitations:['mock'],expires_at:'2099-01-01T00:00:00Z',data_origin:'mock'})
 m.confirm.mockImplementation(async()=>({...revision,state:'published',row_version:2}));m.submit.mockResolvedValue({id:'op',state:'pending',channels:[],message:'accepted'});m.operation.mockResolvedValue({id:'op',state:'pending',channels:[],message:'pending'})
 m.plan.mockImplementation(async c=>({id:'plan',strategy:'template',channel:{...c,target:'person',rule:'dwell',capability_ref:reference,execution_plan:{plan_id:'plan',executor_kind:'template',reason:'优先匹配已有模板',limitations:['mock only'],requires_region:true,requires_duration:true}},verdict:c.duration_seconds?'executable':'clarification_required',missing_conditions:c.duration_seconds?[]:['请明确持续时长'],reason:'优先匹配已有模板',limitations:['mock only'],expires_at:'2099-01-01T00:00:00Z',data_origin:'mock'}))
})
afterEach(()=>{for(const w of wrappers.splice(0))w.unmount();vi.restoreAllMocks()})
async function wizard(){const w=mount(TaskCreatePage,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'},RegionEditor:{template:'<div>ROI editor</div>'},MediaPlayer:true}}});wrappers.push(w);await flushPromises();return w}
async function button(w:ReturnType<typeof mount>,text:string){const b=w.findAll('button').find(b=>b.text()===text);expect(b,`button ${text}`).toBeTruthy();await b!.trigger('click');await flushPromises()}
async function ready(w:ReturnType<typeof mount>){
 await w.get('input[aria-label="任务名称"]').setValue('门口任务')
 w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='检测视频')!.vm.$emit('update:value','s');await nextTick()
 await button(w,'下一步')
 w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='固定任务模板')!.vm.$emit('update:value',preset.id);await nextTick()
 await w.get('input[aria-label="持续时长"]').setValue('30');await button(w,'下一步')
 await w.get('input[type="checkbox"]').setValue(true);await button(w,'保存并验证可执行性')
}
async function natural(w:ReturnType<typeof mount>,text:string){await button(w,'下一步');await w.get('button[aria-label="自然语言任务模式"]').trigger('click');await w.get('input[aria-label="监测需求"]').setValue(text);await button(w,'生成执行方案')}
describe('wizard execution guards',()=>{
 it('recovers an interrupted create with the original idempotency key after refresh',async()=>{const body={name:'恢复任务',description:'',config:{schema_version:'1.0',channels:[newGroup()]}};sessionStorage.setItem('vision.create.new',JSON.stringify({signature:JSON.stringify(body),key:'original-key'}));const w=await wizard();expect(m.create).toHaveBeenCalledWith(body,'original-key');expect(w.get('input[aria-label="任务名称"]').element).toHaveProperty('value','恢复任务');expect(sessionStorage.getItem('vision.create.new')).toBeNull()})

 it('invalidates executable evaluation when a business field changes',async()=>{const w=await wizard();await ready(w);expect(w.text()).toContain('可执行');await button(w,'上一步');await button(w,'上一步');await w.get('input[aria-label="持续时长"]').setValue('60');await button(w,'下一步');await button(w,'下一步');expect(w.findAll('button').find(b=>b.text()==='确认并启动')!.attributes('disabled')).toBeDefined();expect(w.text()).toContain('需要重新验证');expect(m.submit).not.toHaveBeenCalled()})
 it('does not call a pending operation successful or submit it twice',async()=>{const w=await wizard();await ready(w);await w.findAll('input[type="checkbox"]').at(-1)!.setValue(true);await button(w,'确认并启动');expect(m.submit).toHaveBeenCalledTimes(1);expect(w.text()).toContain('已受理');expect(m.router.push).not.toHaveBeenCalled();expect(w.text()).not.toContain('启动完成')})
 it('does not invent a duration for vague natural language',async()=>{const w=await wizard();await natural(w,'有人在区域内停留太久报警');expect(w.get('input[aria-label="持续时长"]').element).toHaveProperty('value','');expect(w.text()).toContain('请明确持续时长')})
 it('blocks an unsupported verdict',async()=>{m.validate.mockResolvedValue({id:'v',verdict:'unsupported',missing_conditions:[],unsupported_conditions:['未支持'],evidence_limitations:[],expires_at:'2099-01-01T00:00:00Z'});const w=await wizard();await ready(w);expect(w.text()).toContain('暂不支持');expect(w.findAll('button').find(b=>b.text()==='确认并启动')!.attributes('disabled')).toBeDefined()})
})
describe('two task entry modes',()=>{
 it('shows a direct template selection by default without requiring natural-language parsing',async()=>{const w=await wizard();await button(w,'下一步');expect(w.find('select[aria-label="固定任务模板"]').exists()).toBe(true);expect(w.find('input[aria-label="监测需求"]').exists()).toBe(false);expect(m.plan).not.toHaveBeenCalled()})
 it('shows the existing-template route for a fully matched natural-language request',async()=>{const w=await wizard();await natural(w,'有人在区域内停留太久报警');expect(w.text()).toContain('已匹配已有模板');expect(m.plan).toHaveBeenCalledOnce()})
 it('shows a multimodal execution plan without a mandatory small-model selector',async()=>{m.plan.mockImplementation(async c=>({id:'p',strategy:'multimodal',channel:{...c,target:'visual_subject',rule:'multimodal_observation',capability_ref:null,execution_plan:{plan_id:'p',executor_kind:'multimodal',deployment_id:'local-vlm',deployment_version:'2',instruction:c.requirement_text,reason:'无法完整匹配模板，使用多模态执行',limitations:['mock']}},verdict:'executable',missing_conditions:[],reason:'无法完整匹配模板，使用多模态执行',limitations:['mock']}));const w=await wizard();await natural(w,'识别红衣服的人是否抽烟');expect(w.text()).toContain('由多模态大模型执行');expect(w.text()).toContain('local-vlm');await button(w,'下一步');expect(w.text()).toContain('自然语言 → 多模态大模型执行');expect(w.find('select[aria-label="模型与模板"]').exists()).toBe(false)})
 it('keeps a server plan when canonical fields arrive after the plan in JSON order',async()=>{const respond=m.plan.getMockImplementation()!;m.plan.mockImplementation(async c=>{const result=await respond(c);result.channel={execution_plan:result.channel.execution_plan,source_id:null,...Object.fromEntries(Object.entries(result.channel).filter(([key])=>key!=='execution_plan'))};return result});const w=await wizard();await natural(w,'有人在区域内停留太久报警');expect(w.find('[data-testid="execution-plan"]').exists()).toBe(true);expect(w.text()).toContain('已匹配已有模板');await button(w,'生成执行方案');expect(w.find('[data-testid="execution-plan"]').exists()).toBe(true)})
 it('clears a generated route after the original requirement changes',async()=>{const w=await wizard();await natural(w,'有人在区域内停留太久报警');expect(w.find('[data-testid="execution-plan"]').exists()).toBe(true);await w.get('input[aria-label="监测需求"]').setValue('识别红衣服的人');await nextTick();expect(w.find('[data-testid="execution-plan"]').exists()).toBe(false);expect(w.text()).toContain('尚未生成当前需求')})
})
describe('grouped draft and idempotency',()=>{
 it('keeps each retained source ROI and gives new videos empty ROI',()=>{const c=newGroup();selectSources(c,['one','two']);c.sources![0]!.regions=[{id:'roi',name:'区域',points:[[0,0],[1,0],[0,1]]}];selectSources(c,['two','one','three']);expect(bindings(c)[1]!.regions).toHaveLength(1);expect(bindings(c)[2]!.regions).toEqual([]);expect(c.source_id).toBeNull()})
 it('copies new identities and independent configuration objects',()=>{const original={schema_version:'1.0' as const,channels:[newGroup()]};selectSources(original.channels[0]!,['one']);const copy=copyForNewTask(original);copy.channels![0]!.sources![0]!.regions=[{id:'x',name:'区域',points:[[0,0],[1,0],[0,1]]}];expect(copy.channels![0]!.channel_id).not.toBe(original.channels[0]!.channel_id);expect(original.channels[0]!.sources![0]!.regions).toEqual([]);expect(draftIssue('test',copy,true)).not.toBe('')})
 it('retries identical requests with a stable key after response loss',()=>{const first=retryKey('start',{revision:'one'});expect(retryKey('start',{revision:'one'})).toBe(first);expect(retryKey('start',{revision:'two'})).not.toBe(first)})
})


describe('single-input task creation',()=>{
 it('offers each business template once while preserving raw model references',async()=>{
  const second={...preset,id:'other-model-template',capability_ref:{...reference,model_id:'other-model',model_version:'2'}}
  m.templates.mockResolvedValue({items:[preset,second],fingerprint:'fp',data_origin:'mock'})
  const w=await wizard();await button(w,'下一步')
  const picker=w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='固定任务模板')!
  expect(picker.props('options')).toHaveLength(1)
  picker.vm.$emit('update:value',preset.id);await nextTick()
  await button(w,'上一步');await w.get('input[aria-label="任务名称"]').setValue('区域停留检测');await button(w,'保存草稿')
  expect(m.create.mock.calls[0]![0].config.channels[0].capability_ref).toEqual(reference)
 })
 it('uses one source selector and replaces the current video instead of adding another',async()=>{
  const w=await wizard();const picker=w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='检测视频')!
  expect(picker.props('multiple')).toBeFalsy();expect(w.text()).not.toContain('＋ 添加组')
  picker.vm.$emit('update:value','s');await nextTick();picker.vm.$emit('update:value','camera-next');await nextTick()
  await w.get('input[aria-label="任务名称"]').setValue('单视频任务');await button(w,'保存草稿')
  const config=m.create.mock.calls[0]![0].config
  expect(config.channels).toHaveLength(1);expect(bindings(config.channels[0]).map(b=>b.source_id)).toEqual(['camera-next'])
 })
 it('requires an explicit video when copying a multi-input task and removes generated copy suffixes',async()=>{
  const one=newGroup(),two=newGroup();one.name='门口';two.name='仓库';selectSources(one,['s']);selectSources(two,['camera-next'])
  const original={id:'old',name:'区域停留检测（副本）',description:'original',latest_revision:{id:'old-r',state:'draft',config:{schema_version:'1.0',channels:[one,two]}}}
  m.detail.mockResolvedValue(original)
  const w=await wizard();w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='从已有智能体复制')!.vm.$emit('update:value','old');await flushPromises()
  expect(w.findAll('button').find(b=>b.text()==='使用配置')!.attributes('disabled')).toBeDefined()
  w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='复制哪一路视频')!.vm.$emit('update:value','1:0');await nextTick();await button(w,'使用配置')
  expect(w.get('input[aria-label="任务名称"]').element).toHaveProperty('value','区域停留检测');expect(w.text()).not.toContain('（副本）')
  m.detail.mockImplementation(async()=>stored);await button(w,'保存草稿')
  const config=m.create.mock.calls[0]![0].config
  expect(config.channels).toHaveLength(1);expect(bindings(config.channels[0]).map(b=>b.source_id)).toEqual(['camera-next'])
  expect(original.latest_revision.config.channels).toHaveLength(2);expect(bindings(one)).toHaveLength(1)
 })
 it('keeps historical multi-input drafts intact and blocks starting them through the single-video wizard',async()=>{
  const one=newGroup(),two=newGroup();selectSources(one,['s']);selectSources(two,['two'])
  m.route.query={draft:'old'}
  const original={id:'old',name:'历史多视频任务',description:'',latest_revision:{id:'r-old',state:'draft',config:{schema_version:'1.0',channels:[one,two]}}}
  m.detail.mockResolvedValue(original);const w=await wizard()
  expect(w.text()).toContain('此历史配置包含多路视频');expect(w.find('select[aria-label="检测视频"]').exists()).toBe(false)
  expect(w.findAll('button').find(b=>b.text()==='保存草稿')!.attributes('disabled')).toBeDefined()
  expect(m.create).not.toHaveBeenCalled();expect(m.submit).not.toHaveBeenCalled();expect(original.latest_revision.config.channels).toHaveLength(2)
 })
 it('rejects multi-channel and multi-source payloads and never silently chooses a copy input',()=>{
  const one=newGroup(),two=newGroup();selectSources(one,['one']);selectSources(two,['two'])
  const config={schema_version:'1.0' as const,channels:[one,two]}
  expect(draftIssue('name',config,false)).toContain('仅检测一路视频');expect(()=>copyForNewTask(config)).toThrow('请选择本次要检测的一路视频')
  const copy=copyForNewTask(config,'1:0');expect(copy.channels).toHaveLength(1);expect(bindings(copy.channels![0]!)[0]!.source_id).toBe('two')
  selectSources(one,['one','two']);expect(draftIssue('name',{schema_version:'1.0',channels:[one]},false)).toContain('仅检测一路视频')
  expect(cleanTaskName('任务（副本）（副本）')).toBe('任务');expect(cleanTaskName('用户自定任务名称')).toBe('用户自定任务名称')
 })
})

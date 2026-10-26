import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { newGroup, selectSources, bindings, copyForNewTask, draftIssue, retryKey } from '../src/modules/task-create/state'
const m=vi.hoisted(()=>({route:{query:{}},router:{replace:vi.fn(),push:vi.fn()},detail:vi.fn(),create:vi.fn(),validate:vi.fn(),confirm:vi.fn(),submit:vi.fn(),operation:vi.fn(),parse:vi.fn(),get:vi.fn(),catalog:vi.fn(),sources:vi.fn()}))
vi.mock('vue-router',()=>({useRoute:()=>m.route,useRouter:()=>m.router,onBeforeRouteLeave:vi.fn()}))
vi.mock('../src/shared/environment',()=>({environment:ref({data_origin:'mock'}),loadEnvironment:vi.fn()}))
vi.mock('../src/shared/api/client',()=>({client:{get:m.get},humanError:()=> '服务不可用'}))
vi.mock('../src/modules/model-management/api',()=>({modelApi:{parse:m.parse},memberError:()=> '服务不可用'}))
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
const cap={items:[{name:'mock',reference,targets:['person'],rules:['dwell'],requires_region:['dwell'],requires_duration:['dwell'],limitations:['mock only']}],fingerprint:'fp',data_origin:'mock'}
let stored:Record<string,unknown>,revision:Record<string,unknown>
const wrappers:ReturnType<typeof mount>[]=[]
beforeEach(()=>{
 vi.clearAllMocks();sessionStorage.clear()
 m.sources.mockResolvedValue([{id:'s',name:'模拟录像',kind:'file',width:1920,height:1080,duration_ms:100000,status:'ready'}]);m.catalog.mockResolvedValue(cap)
 m.create.mockImplementation(async body=>{revision={id:'r',agent_id:'a',row_version:1,state:'draft',config:body.config};stored={id:'a',name:body.name,description:body.description,row_version:1,latest_revision:revision};return stored});m.detail.mockImplementation(async()=>stored);m.get.mockImplementation(async()=>({data:revision}))
 m.validate.mockResolvedValue({id:'v',revision_id:'r',verdict:'executable',config_hash:'hash',capability_fingerprint:'fp',missing_conditions:[],unsupported_conditions:[],evidence_limitations:['mock'],expires_at:'2099-01-01T00:00:00Z',data_origin:'mock'})
 m.confirm.mockImplementation(async()=>({...revision,state:'published',row_version:2}));m.submit.mockResolvedValue({id:'op',state:'pending',channels:[],message:'accepted'});m.operation.mockResolvedValue({id:'op',state:'pending',channels:[],message:'pending'})
 m.parse.mockResolvedValue({target:'person',rule:'dwell',duration_seconds:null,missing_conditions:['请明确持续时长'],limitations:['mock'],deployment_id:'mock-parser',deployment_version:'1'})
})
afterEach(()=>{for(const w of wrappers.splice(0))w.unmount();vi.restoreAllMocks()})
async function wizard(){const w=mount(TaskCreatePage,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'},RegionEditor:{template:'<div>ROI editor</div>'},MediaPlayer:true}}});wrappers.push(w);await flushPromises();return w}
async function button(w:ReturnType<typeof mount>,text:string){const b=w.findAll('button').find(b=>b.text()===text);expect(b,`button ${text}`).toBeTruthy();await b!.trigger('click');await flushPromises()}
async function ready(w:ReturnType<typeof mount>){
 await w.get('input[aria-label="任务名称"]').setValue('门口任务')
 w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='组内视频源')!.vm.$emit('update:value',['s']);await nextTick()
 await button(w,'下一步');await w.get('input[aria-label="监测需求"]').setValue('有人停留30秒');await w.get('input[aria-label="监测目标"]').setValue('person');await w.get('input[aria-label="触发规则"]').setValue('dwell');await w.get('input[aria-label="持续时长"]').setValue('30');await button(w,'下一步')
 w.findAllComponents({name:'NSelect'}).find(s=>s.attributes('aria-label')==='模型与模板')!.vm.$emit('update:value',JSON.stringify(reference));await nextTick();await w.get('input[type="checkbox"]').setValue(true);await button(w,'保存并验证可执行性')
}
describe('wizard execution guards',()=>{
 it('recovers an interrupted create with the original idempotency key after refresh',async()=>{const body={name:'恢复任务',description:'',config:{schema_version:'1.0',channels:[newGroup()]}};sessionStorage.setItem('vision.create.new',JSON.stringify({signature:JSON.stringify(body),key:'original-key'}));const w=await wizard();expect(m.create).toHaveBeenCalledWith(body,'original-key');expect(w.get('input[aria-label="任务名称"]').element).toHaveProperty('value','恢复任务');expect(sessionStorage.getItem('vision.create.new')).toBeNull()})

 it('invalidates executable evaluation when a business field changes',async()=>{const w=await wizard();await ready(w);expect(w.text()).toContain('可执行');await button(w,'上一步');await button(w,'上一步');await w.get('input[aria-label="持续时长"]').setValue('60');await button(w,'下一步');await button(w,'下一步');expect(w.findAll('button').find(b=>b.text()==='确认并启动')!.attributes('disabled')).toBeDefined();expect(w.text()).toContain('需要重新验证');expect(m.submit).not.toHaveBeenCalled()})
 it('does not call a pending operation successful or submit it twice',async()=>{const w=await wizard();await ready(w);await w.findAll('input[type="checkbox"]').at(-1)!.setValue(true);await button(w,'确认并启动');expect(m.submit).toHaveBeenCalledTimes(1);expect(w.text()).toContain('已受理');expect(m.router.push).not.toHaveBeenCalled();expect(w.text()).not.toContain('启动完成')})
 it('does not invent a duration for vague natural language',async()=>{const w=await wizard();await button(w,'下一步');await w.get('input[aria-label="监测需求"]').setValue('有人停留太久报警');await button(w,'解析当前组需求');expect(w.get('input[aria-label="持续时长"]').element).toHaveProperty('value','');expect(w.text()).toContain('请明确持续时长')})
 it('blocks an unsupported verdict',async()=>{m.validate.mockResolvedValue({id:'v',verdict:'unsupported',missing_conditions:[],unsupported_conditions:['未支持'],evidence_limitations:[],expires_at:'2099-01-01T00:00:00Z'});const w=await wizard();await ready(w);expect(w.text()).toContain('暂不支持');expect(w.findAll('button').find(b=>b.text()==='确认并启动')!.attributes('disabled')).toBeDefined()})
})
describe('grouped draft and idempotency',()=>{
 it('keeps each retained source ROI and gives new videos empty ROI',()=>{const c=newGroup();selectSources(c,['one','two']);c.sources![0]!.regions=[{id:'roi',name:'区域',points:[[0,0],[1,0],[0,1]]}];selectSources(c,['two','one','three']);expect(bindings(c)[1]!.regions).toHaveLength(1);expect(bindings(c)[2]!.regions).toEqual([]);expect(c.source_id).toBeNull()})
 it('copies new identities and independent configuration objects',()=>{const original={schema_version:'1.0' as const,channels:[newGroup()]};selectSources(original.channels[0]!,['one']);const copy=copyForNewTask(original);copy.channels![0]!.sources![0]!.regions=[{id:'x',name:'区域',points:[[0,0],[1,0],[0,1]]}];expect(copy.channels![0]!.channel_id).not.toBe(original.channels[0]!.channel_id);expect(original.channels[0]!.sources![0]!.regions).toEqual([]);expect(draftIssue('test',copy,true)).not.toBe('')})
 it('retries identical requests with a stable key after response loss',()=>{const first=retryKey('start',{revision:'one'});expect(retryKey('start',{revision:'one'})).toBe(first);expect(retryKey('start',{revision:'two'})).not.toBe(first)})
})

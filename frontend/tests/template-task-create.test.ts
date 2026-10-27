import { flushPromises,mount } from '@vue/test-utils'
import { afterEach,beforeEach,expect,it,vi } from 'vitest'
import { nextTick } from 'vue'
import TemplateTaskCreatePage from '../src/modules/task-create/TemplateTaskCreatePage.vue'
import { templatesApi,allPublishedTemplates } from '../src/modules/agents/templatesApi'
import { agentApi,listAgentSources,type AgentDetail,type Revision,type Validation } from '../src/modules/agents/api'
import { pool,catalog,source,template,task } from './fixtures/agentTemplates'
const navigation=vi.hoisted(()=>({query:{} as Record<string,string>,replace:vi.fn(),push:vi.fn()}))
vi.mock('vue-router',()=>({useRoute:()=>({query:navigation.query}),useRouter:()=>navigation,onBeforeRouteLeave:vi.fn()}))
vi.mock('../src/modules/agents/templatesApi',async()=>{const actual=await vi.importActual('../src/modules/agents/templatesApi');return{...actual,allPublishedTemplates:vi.fn()}})
vi.mock('../src/modules/agents/api',async()=>{const actual=await vi.importActual('../src/modules/agents/api');return{...actual,listAgentSources:vi.fn()}})
vi.mock('naive-ui',async()=>{
  const {defineComponent}=await import('vue')
  return {NButton:defineComponent({props:['disabled','loading'],template:'<button :disabled="disabled||loading"><slot/></button>'}),NInput:defineComponent({props:['value'],emits:['update:value'],template:'<input :value="value" @input="$emit(\'update:value\',$event.target.value)"/>'}),NSelect:defineComponent({name:'TaskSelect',props:['value','options','multiple','disabled'],emits:['update:value'],template:'<div/>'}),NInputNumber:defineComponent({name:'TaskNumber',props:['value','disabled'],emits:['update:value'],template:'<input type="number" :value="value"/>'}),NCheckbox:defineComponent({props:['checked','disabled'],emits:['update:checked'],template:'<input type="checkbox" :checked="checked" :disabled="disabled" @change="$emit(\'update:checked\',$event.target.checked)"/>'})}
})
const wrappers:ReturnType<typeof mount>[]=[]
let stored:AgentDetail
beforeEach(()=>{
  sessionStorage.clear();navigation.query={};navigation.push.mockClear();navigation.replace.mockClear();stored=task()
  vi.mocked(allPublishedTemplates).mockResolvedValue([template()]);vi.mocked(listAgentSources).mockResolvedValue([source])
  vi.spyOn(templatesApi,'parameters').mockResolvedValue({version:'1',items:pool,editable_by_user:false})
  vi.spyOn(templatesApi,'detail').mockResolvedValue(template())
  vi.spyOn(agentApi,'catalog').mockResolvedValue(catalog)
  vi.spyOn(templatesApi,'instantiate').mockImplementation(async(_id,body)=>{stored.name=body.name;stored.latest_revision.config.channels![0]!.sources=[body.source];stored.latest_revision.config.channels![0]!.parameters=body.parameters;return stored})
  vi.spyOn(agentApi,'detail').mockImplementation(async()=>stored)
  vi.spyOn(agentApi,'save').mockImplementation(async(_revision,config)=>{stored.latest_revision.config=config;stored.latest_revision.row_version++;return stored.latest_revision})
  vi.spyOn(agentApi,'validate').mockImplementation(async()=>{stored.latest_revision.row_version++;return{id:'validation',revision_id:stored.latest_revision.id,capability_fingerprint:'fp',data_origin:'mock',created_at:'2026-10-27T00:00:00Z',verdict:'executable',config_hash:'hash',expires_at:'2099-01-01T00:00:00Z',missing_conditions:[],unsupported_conditions:[],evidence_limitations:[]} satisfies Validation})
  vi.spyOn(agentApi,'confirm').mockImplementation(async()=>({...stored.latest_revision,state:'published'} as Revision))
  vi.spyOn(agentApi,'submit').mockResolvedValue({id:'operation',agent_id:'task-1',kind:'start',state:'pending',channels:[],message:'已受理',data_origin:'mock'})
  vi.spyOn(agentApi,'operation').mockResolvedValue({id:'operation',agent_id:'task-1',kind:'start',state:'failed',channels:[],message:'测试不启动真实服务',data_origin:'mock'})
})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.restoreAllMocks()})
async function page(){const w=mount(TemplateTaskCreatePage,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'},RegionEditor:true,MediaPlayer:true}}});wrappers.push(w);await flushPromises();return w}
function picker(w:ReturnType<typeof mount>,name:string){return w.findAllComponents({name:'TaskSelect'}).find(s=>s.attributes('aria-label')===name)!}
async function press(w:ReturnType<typeof mount>,name:string){await w.findAll('button').find(b=>b.text()===name)!.trigger('click');await flushPromises()}
async function configure(w:ReturnType<typeof mount>){picker(w,'选择智能体模板').vm.$emit('update:value','template-1');picker(w,'检测视频源').vm.$emit('update:value','source-1');await nextTick()}

it('creates tasks through the selected template version without an independent model picker',async()=>{
  const w=await page();await configure(w);await press(w,'保存任务草稿')
  expect(templatesApi.instantiate).toHaveBeenCalledWith('template-1',expect.objectContaining({template_revision_id:'template-revision-1',source:expect.objectContaining({source_id:'source-1'}),parameters:[{key:'confidence_threshold',value:.8,required:true}]}),expect.any(String))
  expect(w.text()).toContain('任务草稿已保存')
  expect(w.findAllComponents({name:'TaskSelect'}).some(s=>s.attributes('aria-label')==='选择模型')).toBe(false)
  expect(w.text()).not.toContain('选择配置项')
})
it('blocks tasks without a template or video instead of creating an unassociated agent',async()=>{
  const w=await page();await press(w,'保存任务草稿')
  expect(templatesApi.instantiate).not.toHaveBeenCalled()
  expect(w.findAll('button').find(b=>b.text()==='保存任务草稿')!.attributes('disabled')).toBeDefined()
  picker(w,'选择智能体模板').vm.$emit('update:value','template-1');await nextTick()
  await press(w,'保存任务草稿');expect(w.text()).toContain('请选择一个检测视频源')
})
it('keeps an existing task on its original version when the template now has a newer version',async()=>{
  navigation.query={draft:'task-1'}
  const newer=template(2),older=template(1);newer.revisions.push(older.latest_revision)
  vi.mocked(allPublishedTemplates).mockResolvedValue([newer]);vi.mocked(templatesApi.detail).mockResolvedValue(newer)
  const w=await page()
  expect(w.text()).toContain('模板版本 v1')
  expect(w.findAllComponents({name:'TaskNumber'}).find(n=>n.attributes('aria-label')==='置信度阈值')!.props('value')).toBe(.8)
  expect(picker(w,'选择智能体模板').props('disabled')).toBe(true)
  expect(templatesApi.instantiate).not.toHaveBeenCalled()
})
it('invalidates execution approval when a selected parameter changes after validation',async()=>{
  const w=await page();await configure(w);await press(w,'验证任务')
  await w.get('input[type="checkbox"]').setValue(true)
  expect(w.findAll('button').find(b=>b.text()==='确认启动')!.attributes('disabled')).toBeUndefined()
  w.findAllComponents({name:'TaskNumber'}).find(n=>n.attributes('aria-label')==='置信度阈值')!.vm.$emit('update:value',.9);await nextTick()
  expect(w.findAll('button').find(b=>b.text()==='确认启动')!.attributes('disabled')).toBeDefined()
  expect(agentApi.submit).not.toHaveBeenCalled()
})
it('retains failed startup as an operation result rather than displaying success',async()=>{
  const w=await page();await configure(w);await press(w,'验证任务');await w.get('input[type="checkbox"]').setValue(true);await press(w,'确认启动')
  expect(agentApi.submit).toHaveBeenCalledOnce();expect(w.text()).toContain('测试不启动真实服务');expect(navigation.push).not.toHaveBeenCalled()
})

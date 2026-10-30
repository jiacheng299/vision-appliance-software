import { flushPromises,mount } from '@vue/test-utils'
import { afterEach,beforeEach,expect,it,vi } from 'vitest'
import { nextTick } from 'vue'
import TemplateTaskCreatePage from '../src/modules/task-create/TemplateTaskCreatePage.vue'
import { templatesApi,allPublishedTemplates } from '../src/modules/agents/templatesApi'
import { agentApi,listAgentSources,type AgentDetail,type Revision,type Validation } from '../src/modules/agents/api'
import { pool,catalog,source,template,task } from './fixtures/agentTemplates'
const navigation=vi.hoisted(()=>({query:{} as Record<string,string>,replace:vi.fn(),push:vi.fn(),leave:vi.fn()}))
vi.mock('vue-router',()=>({useRoute:()=>({query:navigation.query}),useRouter:()=>navigation,onBeforeRouteLeave:(guard:()=>boolean)=>navigation.leave.mockImplementation(guard)}))
vi.mock('../src/modules/agents/templatesApi',async()=>{const actual=await vi.importActual<typeof import('../src/modules/agents/templatesApi')>('../src/modules/agents/templatesApi');return{...actual,templatesApi:{...actual.templatesApi,matcherStatus:vi.fn(),match:vi.fn()},allPublishedTemplates:vi.fn()}})
vi.mock('../src/modules/agents/api',async()=>{const actual=await vi.importActual('../src/modules/agents/api');return{...actual,listAgentSources:vi.fn()}})
vi.mock('naive-ui',async()=>{
  const {defineComponent}=await import('vue')
  return {NButton:defineComponent({props:['disabled','loading'],template:'<button :disabled="disabled||loading"><slot/></button>'}),NInput:defineComponent({props:['value'],emits:['update:value'],template:'<input :value="value" @input="$emit(\'update:value\',$event.target.value)"/>'}),NSelect:defineComponent({name:'TaskSelect',props:['value','options','multiple','disabled'],emits:['update:value'],template:'<div/>'}),NInputNumber:defineComponent({name:'TaskNumber',props:['value','disabled'],emits:['update:value'],template:'<input type="number" :value="value"/>'}),NCheckbox:defineComponent({props:['checked','disabled'],emits:['update:checked'],template:'<input type="checkbox" :checked="checked" :disabled="disabled" @change="$emit(\'update:checked\',$event.target.checked)"/>'})}
})
const wrappers:ReturnType<typeof mount>[]=[]
let stored:AgentDetail
beforeEach(()=>{
  sessionStorage.clear();navigation.query={};navigation.push.mockClear();navigation.replace.mockClear();stored=task()
  vi.mocked(templatesApi.matcherStatus).mockReset();vi.mocked(templatesApi.match).mockReset()
  vi.mocked(allPublishedTemplates).mockResolvedValue([template()]);vi.mocked(listAgentSources).mockResolvedValue([source])
  vi.spyOn(templatesApi,'parameters').mockResolvedValue({version:'1',items:pool,editable_by_user:false})
  vi.spyOn(templatesApi,'detail').mockResolvedValue(template())
  vi.spyOn(agentApi,'catalog').mockResolvedValue(catalog)
  vi.spyOn(templatesApi,'instantiate').mockImplementation(async(_id,body)=>{stored.name=body.name;stored.latest_revision.config.channels![0]!.sources=body.sources??[body.source!];stored.latest_revision.config.channels![0]!.parameters=body.parameters;return stored})
  vi.spyOn(agentApi,'detail').mockImplementation(async()=>stored)
  vi.spyOn(agentApi,'save').mockImplementation(async(_revision,config)=>{stored.latest_revision.config=config;stored.latest_revision.row_version++;return stored.latest_revision})
  vi.spyOn(agentApi,'validate').mockImplementation(async()=>{stored.latest_revision.row_version++;return{id:'validation',revision_id:stored.latest_revision.id,capability_fingerprint:'fp',data_origin:'mock',created_at:'2026-10-27T00:00:00Z',verdict:'executable',config_hash:'hash',expires_at:'2099-01-01T00:00:00Z',missing_conditions:[],unsupported_conditions:[],evidence_limitations:[]} satisfies Validation})
  vi.spyOn(agentApi,'confirm').mockImplementation(async()=>({...stored.latest_revision,state:'published'} as Revision))
  vi.spyOn(agentApi,'submit').mockResolvedValue({id:'operation',agent_id:'task-1',kind:'start',state:'pending',channels:[],message:'已受理',data_origin:'mock'})
  vi.spyOn(agentApi,'operation').mockResolvedValue({id:'operation',agent_id:'task-1',kind:'start',state:'failed',channels:[],message:'测试不启动真实服务',data_origin:'mock'})
})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.restoreAllMocks()})
async function page(){const w=mount(TemplateTaskCreatePage,{attachTo:document.body,global:{stubs:{RouterLink:{template:'<a><slot/></a>'},RegionEditor:true,MediaPlayer:true}}});wrappers.push(w);await flushPromises();return w}
function picker(w:ReturnType<typeof mount>,name:string){const selected=w.findAllComponents({name:'TaskSelect'}).find(s=>s.attributes('aria-label')===name);expect(selected,`${name} control`).toBeDefined();return selected!}
async function press(w:ReturnType<typeof mount>,name:string){const b=w.findAll('button').find(b=>b.text()===name);expect(b,`${name} button`).toBeDefined();await b!.trigger('click');await flushPromises()}
async function choose(w:ReturnType<typeof mount>){await w.get('[aria-label="选择模板：火灾检测"]').trigger('click');await press(w,'确认模板，下一步')}
async function configure(w:ReturnType<typeof mount>){await choose(w);picker(w,'检测视频源').vm.$emit('update:value','source-1');await nextTick()}
async function returnConfig(w:ReturnType<typeof mount>){await press(w,'返回修改配置')}

it('requires selecting and confirming a template before video configuration and never calls matching APIs',async()=>{
  const w=await page()
  expect(w.get('[aria-label="确认模板，下一步"]').attributes('disabled')).toBeDefined()
  expect(w.get('button[aria-label="自然语言匹配"]').attributes('disabled')).toBeDefined()
  expect(w.find('[aria-label="任务名称"]').isVisible()).toBe(false)
  await w.get('[aria-label="选择模板：火灾检测"]').trigger('click')
  expect(w.find('[aria-label="任务名称"]').isVisible()).toBe(false)
  expect(templatesApi.instantiate).not.toHaveBeenCalled()
  await press(w,'确认模板，下一步')
  expect(w.get('[aria-label="任务名称"]').isVisible()).toBe(true)
  expect(templatesApi.matcherStatus).not.toHaveBeenCalled();expect(templatesApi.match).not.toHaveBeenCalled()
})
it('keeps the chosen template and source configuration when returning to the first step',async()=>{
  const w=await page();await configure(w);await press(w,'上一步')
  await press(w,'确认模板，下一步')
  expect(picker(w,'检测视频源').props('value')).toBe('source-1')
})
it('creates tasks on the selected version and validation never starts execution',async()=>{
  const w=await page();await configure(w);await press(w,'验证任务')
  expect(templatesApi.instantiate).toHaveBeenCalledWith('template-1',expect.objectContaining({template_revision_id:'template-revision-1',source:expect.objectContaining({source_id:'source-1'})}),expect.any(String))
  expect(agentApi.submit).not.toHaveBeenCalled()
  expect(w.get('[aria-label="确认启动"]').attributes('disabled')).toBeDefined()
  await w.get('input[type="checkbox"]').setValue(true);await press(w,'确认启动')
  expect(agentApi.submit).toHaveBeenCalledOnce();expect(w.text()).toContain('测试不启动真实服务')
  expect(navigation.push).not.toHaveBeenCalled()
})
it('preserves every source and their regions in a new multi-video draft',async()=>{
  vi.mocked(listAgentSources).mockResolvedValue([source,{...source,id:'source-2',name:'第二路'}])
  const w=await page();await configure(w)
  w.getComponent({name:'RegionEditor'}).vm.$emit('change',[{id:'roi',points:[[0,0],[1,0],[1,1]]}]);await nextTick()
  await press(w,'添加视频源');picker(w,'检测视频源2').vm.$emit('update:value','source-2');await nextTick()
  await press(w,'保存草稿')
  const body=vi.mocked(templatesApi.instantiate).mock.calls[0]![1]
  expect(body.sources?.map(b=>b.source_id)).toEqual(['source-1','source-2'])
  expect(body.sources?.[0]?.regions).toHaveLength(1);expect(body.sources?.[1]?.regions).toEqual([])
})
it('continues a draft on its original template version and preserves every input',async()=>{
  navigation.query={draft:'task-1'}
  const newer=template(2);newer.revisions.push(template().latest_revision)
  vi.mocked(allPublishedTemplates).mockResolvedValue([newer]);vi.mocked(templatesApi.detail).mockResolvedValue(newer)
  vi.mocked(listAgentSources).mockResolvedValue([source,{...source,id:'source-2',name:'第二路'}])
  stored.latest_revision.config.channels![0]!.sources!.push({...stored.latest_revision.config.channels![0]!.sources![0]!,source_id:'source-2',regions:[]})
  const w=await page();expect(w.text()).toContain('模板版本 v1')
  await press(w,'保存草稿')
  expect(vi.mocked(agentApi.save).mock.calls[0]![1].channels![0]!.sources!.map(b=>b.source_id)).toEqual(['source-1','source-2'])
  expect(templatesApi.instantiate).not.toHaveBeenCalled()
})
it('invalidates approval after editing shared conditions',async()=>{
  const w=await page();await configure(w);await press(w,'验证任务');await w.get('input[type="checkbox"]').setValue(true)
  await returnConfig(w)
  w.findAllComponents({name:'TaskNumber'}).find(n=>n.attributes('aria-label')==='置信度阈值')!.vm.$emit('update:value',.9);await nextTick()
  expect(agentApi.submit).not.toHaveBeenCalled()
  await press(w,'验证任务')
  expect(w.get('[aria-label="确认启动"]').attributes('disabled')).toBeDefined()
})
it('protects navigation and rejects expired validations',async()=>{
  const w=await page();await configure(w)
  vi.spyOn(window,'confirm').mockReturnValue(false);expect(navigation.leave()).toBe(false)
  vi.mocked(agentApi.validate).mockResolvedValue({id:'expired',revision_id:stored.latest_revision.id,capability_fingerprint:'fp',data_origin:'mock',created_at:'2020-01-01T00:00:00Z',verdict:'executable',config_hash:'hash',expires_at:'2020-01-02T00:00:00Z',missing_conditions:[],unsupported_conditions:[],evidence_limitations:[]})
  await press(w,'验证任务')
  expect(w.get('[aria-label="确认启动"]').attributes('disabled')).toBeDefined();expect(agentApi.confirm).not.toHaveBeenCalled()
})
it('blocks incomplete region drawings before saving',async()=>{
  const w=await page();await configure(w)
  w.getComponent({name:'RegionEditor'}).vm.$emit('pending',true);await nextTick();await press(w,'保存草稿')
  expect(templatesApi.instantiate).not.toHaveBeenCalled();expect(w.text()).toContain('请先闭合并保存')
})
it('reuses the instantiate key after an interrupted save',async()=>{
  const implementation=vi.mocked(templatesApi.instantiate).getMockImplementation()!
  vi.mocked(templatesApi.instantiate).mockRejectedValueOnce(new Error('保存请求超时')).mockImplementationOnce(implementation)
  const w=await page();await configure(w);await press(w,'保存草稿');await press(w,'保存草稿')
  expect(vi.mocked(templatesApi.instantiate).mock.calls[0]![2]).toBe(vi.mocked(templatesApi.instantiate).mock.calls[1]![2])
})
it('blocks unavailable sources without losing their reference',async()=>{
  navigation.query={draft:'task-1'};vi.mocked(listAgentSources).mockResolvedValue([])
  const w=await page();await press(w,'保存草稿')
  expect(agentApi.save).not.toHaveBeenCalled();expect(w.text()).toContain('视频源当前不可访问')
})

it('switches video workspace without losing regions and protects unfinished drawing',async()=>{
  vi.mocked(listAgentSources).mockResolvedValue([source,{...source,id:'source-2',name:'第二路'}])
  const w=await page();await configure(w)
  const first=[{id:'first',points:[[0,0],[1,0],[1,1]]}],second=[{id:'second',points:[[.5,.5],[1,.5],[1,1]]}]
  w.getComponent({name:'RegionEditor'}).vm.$emit('change',first);await nextTick()
  await press(w,'添加视频源');picker(w,'检测视频源2').vm.$emit('update:value','source-2');await nextTick()
  expect(w.findAllComponents({name:'RegionEditor'})).toHaveLength(1)
  w.getComponent({name:'RegionEditor'}).vm.$emit('change',second);await nextTick()
  w.getComponent({name:'RegionEditor'}).vm.$emit('pending',true);await nextTick()
  await w.get('[aria-label="配置视频1"]').trigger('click')
  expect(w.get('[aria-label="配置视频2"]').attributes('aria-current')).toBe('true')
  expect(w.text()).toContain('请先闭合并保存')
  w.getComponent({name:'RegionEditor'}).vm.$emit('pending',false);await nextTick()
  await w.get('[aria-label="配置视频1"]').trigger('click');await press(w,'保存草稿')
  const body=vi.mocked(templatesApi.instantiate).mock.calls[0]![1]
  expect(body.sources?.map(b=>b.regions)).toEqual([first,second])
})

it('only navigates to the monitoring page after the start operation succeeds',async()=>{
  vi.mocked(agentApi.operation).mockResolvedValue({id:'op',agent_id:'task-1',kind:'start',state:'succeeded',channels:[],message:'全部运行已启动',data_origin:'mock'})
  const w=await page();await configure(w);await press(w,'验证任务')
  expect(navigation.push).not.toHaveBeenCalled()
  await w.get('input[type="checkbox"]').setValue(true);await press(w,'确认启动')
  expect(navigation.push).toHaveBeenCalledWith('/agents/task-1/live')
})
it('ignores a successful operation response after leaving this page',async()=>{
  let resolve!:(v:Awaited<ReturnType<typeof agentApi.operation>>)=>void
  vi.mocked(agentApi.operation).mockImplementation(()=>new Promise(r=>{resolve=r}))
  const w=await page();await configure(w);await press(w,'验证任务');await w.get('input[type="checkbox"]').setValue(true);await press(w,'确认启动')
  wrappers.splice(wrappers.indexOf(w),1);w.unmount()
  resolve({id:'op',agent_id:'task-1',kind:'start',state:'succeeded',channels:[],message:'完成',data_origin:'mock'});await flushPromises()
  expect(navigation.push).not.toHaveBeenCalled()
})

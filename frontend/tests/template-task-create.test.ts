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
  vi.mocked(templatesApi.matcherStatus).mockReset().mockResolvedValue({configured:true,provider:'deepseek',model:'deepseek-flash',threshold:.8})
  vi.mocked(templatesApi.match).mockReset().mockResolvedValue({status:'matched',template_id:'template-1',template_revision_id:'template-revision-1',confidence:.95,reason:'符合检测要求',uncovered_requirements:[],provider:'deepseek',model:'deepseek-flash'})
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
async function page(){const w=mount(TemplateTaskCreatePage,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'},RegionEditor:true,MediaPlayer:true}}});wrappers.push(w);await flushPromises();return w}
function picker(w:ReturnType<typeof mount>,name:string){const selected=w.findAllComponents({name:'TaskSelect'}).find(s=>s.attributes('aria-label')===name);expect(selected,`${name} control`).toBeDefined();return selected!}
async function press(w:ReturnType<typeof mount>,name:string){await w.findAll('button').find(b=>b.text()===name)!.trigger('click');await flushPromises()}
async function configure(w:ReturnType<typeof mount>){picker(w,'选择智能体模板').vm.$emit('update:value','template-1');picker(w,'检测视频源').vm.$emit('update:value','source-1');await nextTick()}

it('creates one task with two independent video regions and shared parameters',async()=>{
  vi.mocked(listAgentSources).mockResolvedValue([source,{...source,id:'source-2',name:'第二路'}])
  const w=await page();await configure(w)
  w.getComponent({name:'RegionEditor'}).vm.$emit('change',[{id:'roi',points:[[0,0],[1,0],[1,1]]}]);await nextTick()
  await press(w,'添加视频源')
  picker(w,'检测视频源2').vm.$emit('update:value','source-2');await nextTick()
  expect(w.findAllComponents({name:'RegionEditor'})).toHaveLength(2)
  await press(w,'保存任务草稿')
  const body=vi.mocked(templatesApi.instantiate).mock.calls[0]![1]
  expect(body.sources?.map(b=>b.source_id)).toEqual(['source-1','source-2'])
  expect(body.sources?.[0]?.regions).toHaveLength(1)
  expect(body.sources?.[1]?.regions).toEqual([])
  expect(body.parameters).toEqual([{key:'confidence_threshold',value:.8,required:true}])
})

it('loads every source from an existing multi-video draft and keeps them on save',async()=>{
  navigation.query={draft:'task-1'}
  vi.mocked(listAgentSources).mockResolvedValue([source,{...source,id:'source-2',name:'第二路'}])
  stored.latest_revision.config.channels![0]!.sources!.push({...stored.latest_revision.config.channels![0]!.sources![0]!,source_id:'source-2',regions:[]})
  const w=await page()
  expect(picker(w,'检测视频源2').props('value')).toBe('source-2')
  await press(w,'保存任务草稿')
  expect(vi.mocked(agentApi.save).mock.calls[0]![1].channels![0]!.sources!.map(b=>b.source_id)).toEqual(['source-1','source-2'])
})

it('removing one video preserves the other video region and invalidates startup approval',async()=>{
  vi.mocked(listAgentSources).mockResolvedValue([source,{...source,id:'source-2',name:'第二路'}])
  const w=await page();await configure(w);await press(w,'添加视频源')
  picker(w,'检测视频源2').vm.$emit('update:value','source-2');await nextTick()
  const roi=[{id:'second-region',points:[[.5,.5],[1,.5],[1,1]]}]
  w.findAllComponents({name:'RegionEditor'})[1]!.vm.$emit('change',roi);await nextTick()
  await press(w,'验证任务');await w.get('input[type="checkbox"]').setValue(true)
  await w.get('button[aria-label="移除视频1"]').trigger('click');await nextTick()
  expect(picker(w,'检测视频源').props('value')).toBe('source-2')
  expect(w.findAll('button').find(b=>b.text()==='确认启动')!.attributes('disabled')).toBeDefined()
  await press(w,'保存任务草稿')
  expect(vi.mocked(agentApi.save).mock.calls[0]![1].channels![0]!.sources).toEqual([expect.objectContaining({source_id:'source-2',regions:roi})])
})

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
async function natural(w:ReturnType<typeof mount>,text='检测仓库火源'){
  picker(w,'模板选择方式').vm.$emit('update:value','natural');await nextTick()
  await w.get('[aria-label="自然语言任务需求"]').setValue(text)
}
it('matches natural language to the existing published version and its editable defaults',async()=>{
  const w=await page();expect(picker(w,'模板选择方式').props('value')).toBe('manual')
  await natural(w);await press(w,'匹配已有模板')
  expect(templatesApi.match).toHaveBeenCalledWith({requirement_text:'检测仓库火源'})
  expect(w.text()).toContain('符合检测要求');expect(w.text()).toContain('模板版本 v1')
  expect(w.findAllComponents({name:'TaskNumber'}).find(n=>n.attributes('aria-label')==='置信度阈值')!.props('value')).toBe(.8)
  picker(w,'检测视频源').vm.$emit('update:value','source-1');await nextTick();await press(w,'保存任务草稿')
  expect(templatesApi.instantiate).toHaveBeenCalledWith('template-1',expect.objectContaining({template_revision_id:'template-revision-1'}),expect.any(String))
})
it('shows no_match and a management link without allowing a task to be created',async()=>{
  vi.mocked(templatesApi.match).mockResolvedValue({status:'no_match',template_id:null,template_revision_id:null,confidence:.4,reason:'没有覆盖全部需求',uncovered_requirements:['识别烟雾'],provider:'deepseek',model:'deepseek-flash'})
  const w=await page();await natural(w);await press(w,'匹配已有模板')
  expect(w.text()).toContain('无足够匹配的模板，需要自定义创建');expect(w.text()).toContain('识别烟雾')
  expect(w.findAll('a').some(a=>a.text().includes('前往智能体管理'))).toBe(true)
  expect(w.findAll('button').find(b=>b.text()==='保存任务草稿')!.attributes('disabled')).toBeDefined()
  expect(templatesApi.instantiate).not.toHaveBeenCalled()
})
it('explains missing local DeepSeek configuration and still permits manual selection',async()=>{
  vi.mocked(templatesApi.matcherStatus).mockResolvedValue({configured:false,provider:'deepseek',model:'deepseek-flash',threshold:.8})
  const w=await page();await natural(w)
  expect(w.text()).toContain('本机尚未配置 DeepSeek API Key')
  await press(w,'匹配已有模板');expect(templatesApi.match).not.toHaveBeenCalled()
  picker(w,'模板选择方式').vm.$emit('update:value','manual');await nextTick();await configure(w);await press(w,'保存任务草稿')
  expect(templatesApi.instantiate).toHaveBeenCalledOnce()
})
it('reports matching API failures without inventing a template',async()=>{
  vi.mocked(templatesApi.match).mockRejectedValue(new Error('DeepSeek 请求超时'))
  const w=await page();await natural(w);await press(w,'匹配已有模板')
  expect(w.text()).toContain('DeepSeek 请求超时');expect(w.text()).not.toContain('模板版本 v1')
  expect(templatesApi.instantiate).not.toHaveBeenCalled()
})
it.each(['text','mode'] as const)('ignores a late match after changing the %s',async(change)=>{
  let resolve!:(result:Awaited<ReturnType<typeof templatesApi.match>>)=>void
  const match=vi.mocked(templatesApi.match).getMockImplementation()!
  vi.mocked(templatesApi.match).mockImplementation(()=>new Promise(r=>{resolve=r}))
  const w=await page();await natural(w);await press(w,'匹配已有模板')
  await press(w,'匹配已有模板');expect(templatesApi.match).toHaveBeenCalledOnce()
  if(change==='text')await w.get('[aria-label="自然语言任务需求"]').setValue('检测人员在岗')
  else{picker(w,'模板选择方式').vm.$emit('update:value','manual');await nextTick();await configure(w)}
  resolve(await match({requirement_text:'检测仓库火源'}));await flushPromises()
  expect(w.text()).not.toContain('符合检测要求')
  if(change==='text')expect(w.text()).not.toContain('模板版本 v1')
  else expect(picker(w,'选择智能体模板').props('value')).toBe('template-1')
})
it('rejects a match whose published revision changed before it can be selected',async()=>{
  vi.mocked(templatesApi.detail).mockResolvedValue(template(2))
  const w=await page();await natural(w);await press(w,'匹配已有模板')
  expect(w.text()).toContain('匹配的模板版本已不可用，请重新匹配')
  expect(w.text()).not.toContain('模板版本 v2');expect(templatesApi.instantiate).not.toHaveBeenCalled()
})
it('inherits template video, regions and range while a source change clears the old binding',async()=>{
  const t=template();Object.assign(t.published_revision!.config,{default_source:{source_id:'source-1',regions:[{id:'roi',name:'入口',points:[[0,0],[1,0],[1,1]]}],start_media_ms:1000,end_media_ms:5000}})
  vi.mocked(allPublishedTemplates).mockResolvedValue([t]);vi.mocked(listAgentSources).mockResolvedValue([source,{...source,id:'source-2'}])
  const w=await page();picker(w,'选择智能体模板').vm.$emit('update:value','template-1');await nextTick()
  expect(picker(w,'检测视频源').props('value')).toBe('source-1')
  picker(w,'检测视频源').vm.$emit('update:value','source-2');await nextTick();await press(w,'保存任务草稿')
  expect(templatesApi.instantiate).toHaveBeenCalledWith('template-1',expect.objectContaining({source:{source_id:'source-2',regions:[],start_media_ms:null,end_media_ms:null}}),expect.any(String))
})
it.each(['missing','failed'] as const)('blocks an inaccessible %s default source',async(kind)=>{
  const t=template();Object.assign(t.published_revision!.config,{default_source:{source_id:kind==='missing'?'missing':'source-1',regions:[]}})
  vi.mocked(allPublishedTemplates).mockResolvedValue([t]);if(kind==='failed')vi.mocked(listAgentSources).mockResolvedValue([{...source,status:'failed'}])
  const w=await page();picker(w,'选择智能体模板').vm.$emit('update:value','template-1');await nextTick();await press(w,'保存任务草稿')
  expect(w.text()).toContain('视频源当前不可访问，请重新选择可用视频源');expect(templatesApi.instantiate).not.toHaveBeenCalled()
})
it('retains unsaved-navigation protection and rejects expired validations',async()=>{
  const w=await page();await configure(w)
  vi.spyOn(window,'confirm').mockReturnValue(false);expect(navigation.leave()).toBe(false)
  vi.mocked(agentApi.validate).mockResolvedValue({id:'expired',revision_id:stored.latest_revision.id,capability_fingerprint:'fp',data_origin:'mock',created_at:'2020-01-01T00:00:00Z',verdict:'executable',config_hash:'hash',expires_at:'2020-01-02T00:00:00Z',missing_conditions:[],unsupported_conditions:[],evidence_limitations:[]})
  await press(w,'验证任务');expect(w.findAll('button').find(b=>b.text()==='确认启动')!.attributes('disabled')).toBeDefined()
  expect(agentApi.confirm).not.toHaveBeenCalled()
})
it('rejects starting when the validation expires after it was displayed',async()=>{
  const w=await page();await configure(w);await press(w,'验证任务');await w.get('input[type="checkbox"]').setValue(true)
  vi.spyOn(Date,'now').mockReturnValue(Date.parse('2099-01-02T00:00:00Z'))
  await press(w,'确认启动');expect(agentApi.confirm).not.toHaveBeenCalled();expect(agentApi.submit).not.toHaveBeenCalled()
})
it('keeps the local matcher status error visible after switching selection modes',async()=>{
  vi.mocked(templatesApi.matcherStatus).mockRejectedValue(new Error('匹配服务状态暂不可用'))
  const w=await page();await natural(w)
  expect(w.text()).toContain('匹配服务状态暂不可用');expect(templatesApi.match).not.toHaveBeenCalled()
})
it('clears a selected match when its requirement text changes',async()=>{
  const w=await page();await natural(w);await press(w,'匹配已有模板')
  expect(w.text()).toContain('模板版本 v1')
  await w.get('[aria-label="自然语言任务需求"]').setValue('人员是否在岗')
  expect(w.text()).not.toContain('模板版本 v1');expect(w.text()).not.toContain('符合检测要求')
})
it('reuses the instantiate idempotency key after an interrupted save',async()=>{
  const implementation=vi.mocked(templatesApi.instantiate).getMockImplementation()!
  vi.mocked(templatesApi.instantiate).mockRejectedValueOnce(new Error('保存请求超时')).mockImplementationOnce(implementation)
  const w=await page();await configure(w);await press(w,'保存任务草稿');await press(w,'保存任务草稿')
  expect(templatesApi.instantiate).toHaveBeenCalledTimes(2)
  expect(vi.mocked(templatesApi.instantiate).mock.calls[0]![2]).toBe(vi.mocked(templatesApi.instantiate).mock.calls[1]![2])
})
it('blocks startup and protects navigation while an unfinished region is being drawn',async()=>{
  const w=await page();await configure(w);await press(w,'验证任务');await w.get('input[type="checkbox"]').setValue(true)
  w.getComponent({name:'RegionEditor'}).vm.$emit('pending',true);await nextTick()
  expect(w.findAll('button').find(b=>b.text()==='确认启动')!.attributes('disabled')).toBeDefined()
  vi.spyOn(window,'confirm').mockReturnValue(false);expect(navigation.leave()).toBe(false)
})
it('resets the region editor when switching templates that share a video source',async()=>{
  const first=template(),second=template();second.id='template-2';second.published_revision!.id='template-2-revision';second.published_revision!.template_id=second.id
  for(const t of [first,second])Object.assign(t.published_revision!.config,{default_source:{source_id:'source-1',regions:[]}})
  vi.mocked(allPublishedTemplates).mockResolvedValue([first,second])
  const w=await page();picker(w,'选择智能体模板').vm.$emit('update:value','template-1');await nextTick()
  const original=w.getComponent({name:'RegionEditor'}).element
  picker(w,'选择智能体模板').vm.$emit('update:value','template-2');await nextTick()
  expect(w.getComponent({name:'RegionEditor'}).element===original).toBe(false)
})

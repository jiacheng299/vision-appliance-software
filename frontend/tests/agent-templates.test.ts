import { mount,flushPromises } from '@vue/test-utils'
import { afterEach,beforeEach,expect,it,vi } from 'vitest'
import { defineComponent,nextTick } from 'vue'
import { templatesApi } from '../src/modules/agents/templatesApi'
import { agentApi } from '../src/modules/agents/api'
import { pool,catalog,template } from './fixtures/agentTemplates'
import ParameterFields from '../src/modules/agents/ParameterFields.vue'
import TemplateEditor from '../src/modules/agents/TemplateEditor.vue'
import AgentTemplatesPage from '../src/modules/agents/AgentTemplatesPage.vue'
vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()}),onBeforeRouteLeave:vi.fn()}))
vi.mock('naive-ui',async()=>{
  const {defineComponent}=await import('vue')
  const Box=defineComponent({props:['title'],template:'<div>{{title}}<slot/><slot name="footer"/></div>'})
  return {NDrawer:Box,NDrawerContent:Box,NButton:defineComponent({props:['disabled','loading'],template:'<button :disabled="disabled||loading"><slot/></button>'}),NInput:defineComponent({props:['value'],emits:['update:value'],template:'<input :value="value" @input="$emit(\'update:value\',$event.target.value)"/>'}),NSelect:defineComponent({name:'TestSelect',props:['value','options','multiple','disabled'],emits:['update:value'],template:'<div/>'}),NInputNumber:defineComponent({name:'TestNumber',props:['value','min','max'],emits:['update:value'],template:'<input type="number" :value="value"/>'}),NCheckbox:defineComponent({props:['checked'],template:'<span><slot/></span>'})}
})
const wrappers:ReturnType<typeof mount>[]=[]
beforeEach(()=>{vi.spyOn(templatesApi,'parameters').mockResolvedValue({version:'1',items:pool,editable_by_user:false});vi.spyOn(agentApi,'catalog').mockResolvedValue(catalog)})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.restoreAllMocks()})
it('selects only developer-defined fields and preserves values when the selection changes',async()=>{
  const w=mount(ParameterFields,{props:{settings:[{key:'confidence_threshold',value:.8,required:true}],definitions:pool,selectable:true}});wrappers.push(w)
  const picker=w.getComponent({name:'TestSelect'})
  expect(picker.props('options').map((o:{value:string})=>o.value)).toEqual(pool.map(p=>p.key))
  picker.vm.$emit('update:value',['confidence_threshold','color']);await nextTick()
  expect(w.emitted('update:settings')![0]![0]).toEqual([{key:'confidence_threshold',value:.8,required:true},{key:'color',value:null,required:false}])
  expect(w.text()).not.toContain('自定义')
})
it('renders typed fields without exposing a field selection control in task mode',async()=>{
  const w=mount(ParameterFields,{props:{settings:[{key:'min_count',value:2,required:true}],definitions:pool}});wrappers.push(w)
  expect(w.findComponent({name:'TestSelect'}).exists()).toBe(false)
  expect(w.getComponent({name:'TestNumber'}).props('min')).toBe(0)
  w.getComponent({name:'TestNumber'}).vm.$emit('update:value',3);await nextTick()
  expect(w.emitted('update:settings')![0]![0]).toEqual([{key:'min_count',value:3,required:true}])
})
it('creates a source-independent business template with one model selector and selected parameters',async()=>{
  const create=vi.spyOn(templatesApi,'create').mockResolvedValue(template())
  const w=mount(TemplateEditor);wrappers.push(w);await flushPromises()
  await w.findAll('input')[0]!.setValue('火灾检测')
  const selectors=w.findAllComponents({name:'TestSelect'})
  const model=selectors.find(s=>s.attributes('aria-label')==='选择模型')!
  model.vm.$emit('update:value',JSON.stringify(catalog.items[0]!.reference));await nextTick()
  selectors.find(s=>s.attributes('aria-label')==='选择模板配置项')!.vm.$emit('update:value',['color']);await nextTick()
  await w.findAll('button').find(b=>b.text()==='保存草稿')!.trigger('click');await flushPromises()
  expect(create.mock.calls[0]![0].config!.model_ref).toEqual(catalog.items[0]!.reference)
  expect(create.mock.calls[0]![0].config!.parameters?.map(p=>p.key)).toEqual(['color'])
  expect(w.text()).not.toContain('分析模型与规则模板');expect(w.text()).not.toContain('通道内视频源')
})
it('shows template cards with task and unique source totals rather than individual task cards',async()=>{
  vi.spyOn(templatesApi,'list').mockResolvedValue({items:[{...template(),task_count:3,source_count:2}],next_cursor:null})
  const w=mount(AgentTemplatesPage,{global:{stubs:{RouterLink:defineComponent({template:'<a><slot/></a>'}),TemplateEditor:true}}});wrappers.push(w);await flushPromises()
  expect(w.findAll('.template-card')).toHaveLength(1)
  expect(w.findAll('.template-counts strong').map(e=>e.text())).toEqual(['3','2'])
  expect(w.text()).toContain('每张卡片代表一个业务模板')
})

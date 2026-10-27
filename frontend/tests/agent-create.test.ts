import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import CreateAgentDrawer from '../src/modules/agents/CreateAgentDrawer.vue'
import AgentsPage from '../src/modules/agents/AgentsPage.vue'
import { agentApi, listAgentSources } from '../src/modules/agents/api'
import type { Source } from '../src/shared/api/types'

vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()}),onBeforeRouteLeave:vi.fn()}))
vi.mock('../src/modules/agents/api',async()=>{const actual=await vi.importActual('../src/modules/agents/api');return{...actual,listAgentSources:vi.fn()}})
vi.mock('naive-ui',async()=>{
  const {defineComponent}=await import('vue')
  return {
    NDrawer:defineComponent({name:'TestDrawer',props:['show','width','placement','maskClosable','closeOnEsc'],emits:['update:show'],template:'<div><slot/></div>'}),
    NDrawerContent:defineComponent({props:['title','closable'],emits:['close'],template:'<section><h2>{{title}}</h2><slot/><slot name="footer"/></section>'}),
    NButton:defineComponent({props:['disabled','loading','attrType','type'],template:'<button :type="attrType||\'button\'" :disabled="disabled||loading"><slot/></button>'}),
    NInput:defineComponent({props:['value','inputProps'],emits:['update:value'],template:'<input v-bind="inputProps" :value="value" @input="$emit(\'update:value\',$event.target.value)"/>'}),
    NSelect:defineComponent({name:'TestSelect',props:['value','options','multiple','disabled'],emits:['update:value'],template:'<div/>'}),
  }
})
const wrappers:ReturnType<typeof mount>[]=[]
const sources=[{id:'s1',name:'入口',kind:'camera'},{id:'s2',name:'录像',kind:'file'}] as Source[]
function drawer(){const wrapper=mount(CreateAgentDrawer,{props:{sources,sourcesError:''}});wrappers.push(wrapper);return wrapper}
beforeEach(()=>{vi.mocked(listAgentSources).mockResolvedValue(sources)})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.restoreAllMocks()})

it('uses a right drawer and protects uncreated input when closing by mask',async()=>{
  const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
  const w=drawer(),surface=w.getComponent({name:'TestDrawer'})
  expect(surface.props('placement')).toBe('right')
  expect(surface.props('width')).toBe('min(100vw, max(640px, 50vw))')
  expect(w.text()).not.toContain('监测组')
  await w.get('#agent-name').setValue('仓库火灾探测')
  surface.vm.$emit('update:show',false);await flushPromises()
  expect(confirm).toHaveBeenCalledOnce();expect(w.emitted('close')).toBeUndefined()
  confirm.mockReturnValue(true);surface.vm.$emit('update:show',false);await flushPromises()
  expect(w.emitted('close')).toHaveLength(1)
})
it('keeps fields and the same idempotency key after a timeout, then creates one multi-source channel',async()=>{
  const create=vi.spyOn(agentApi,'create').mockRejectedValueOnce(new Error('timeout')).mockResolvedValue({id:'created'} as any)
  const w=drawer()
  await w.get('#agent-name').setValue('火灾探测')
  w.getComponent({name:'TestSelect'}).vm.$emit('update:value',['s1','s2'])
  await w.get('form').trigger('submit');await flushPromises()
  expect(w.emitted('created')).toBeUndefined()
  expect((w.get('#agent-name').element as HTMLInputElement).value).toBe('火灾探测')
  await w.get('form').trigger('submit');await flushPromises()
  expect(create.mock.calls[1]![1]).toBe(create.mock.calls[0]![1])
  expect(create.mock.calls[1]![0]).toEqual(create.mock.calls[0]![0])
  expect(create.mock.calls[1]![0].config?.channels?.[0]?.sources?.map(s=>s.source_id)).toEqual(['s1','s2'])
  expect(create.mock.calls[1]![0].config?.channels?.[0]?.name).toBe('通道 1')
  expect(create.mock.calls[1]![0].config?.channels?.[0]?.task_mode).toBe('template')
  expect(w.emitted('created')).toHaveLength(1)
})
it('prevents duplicate submission or dismissal while creation is in flight',async()=>{
  let finish!:(value:any)=>void
  const create=vi.spyOn(agentApi,'create').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const w=drawer();await w.get('#agent-name').setValue('草稿')
  await w.get('form').trigger('submit');await w.get('form').trigger('submit')
  w.getComponent({name:'TestDrawer'}).vm.$emit('update:show',false)
  await flushPromises()
  expect(create).toHaveBeenCalledOnce();expect(w.emitted('close')).toBeUndefined()
  expect(w.getComponent({name:'TestDrawer'}).props('maskClosable')).toBe(false)
  finish({id:'created'});await flushPromises()
})
it('keeps agent cards and the create button usable even when source loading fails',async()=>{
  vi.mocked(listAgentSources).mockRejectedValue(new Error('source service unavailable'))
  vi.spyOn(agentApi,'list').mockResolvedValue({items:[{id:'a',name:'仓库监测',status:'draft',latest_revision:{revision_no:1,config:{channels:[]}}}]} as any)
  const w=mount(AgentsPage,{global:{stubs:{RouterLink:{template:'<a><slot/></a>'}}}});wrappers.push(w)
  await flushPromises()
  expect(w.findAll('.agent-card')).toHaveLength(1)
  const open=w.findAll('button').find(b=>b.text()==='新建草稿')!
  expect(open.attributes('disabled')).toBeUndefined()
  await open.trigger('click');await flushPromises()
  expect(w.findComponent(CreateAgentDrawer).exists()).toBe(true)
  expect(w.text()).toContain('视频源列表加载失败')
})

import { afterEach,it,expect,vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TemplateSelection from '../src/modules/task-create/TemplateSelection.vue'
import { templatesApi } from '../src/modules/agents/templatesApi'
import { template } from './fixtures/agentTemplates'

afterEach(() => vi.restoreAllMocks())

it('filters published templates and emits the selected existing template',async()=>{
  const first=template(),second={...template(),id:'second',name:'人员在岗监测'},archived={...template(),id:'archived',archived_at:'2026-01-01'}
  const w=mount(TemplateSelection,{props:{templates:[first,second,archived],selectedId:null}})
  expect(w.findAll('[role="option"]')).toHaveLength(2)
  await w.get('input[type="search"]').setValue('人员')
  expect(w.findAll('[role="option"]')).toHaveLength(1)
  await w.get('[role="option"]').trigger('click')
  expect(w.emitted('select')).toEqual([['second']])
  w.unmount()
})

it('shows natural-language matching as a second selectable mode',async()=>{
  vi.spyOn(templatesApi,'matcherStatus').mockResolvedValue({configured:false,provider:'kimi',model:'kimi-latest',threshold:.8})
  const w=mount(TemplateSelection,{props:{templates:[template()],selectedId:null}})
  const natural=w.get('button[aria-label="自然语言匹配"]')
  expect(natural.attributes('disabled')).toBeUndefined()
  await natural.trigger('click')
  expect(w.find('[aria-label="自然语言匹配面板"]').exists()).toBe(true)
  expect(w.text()).toContain('大模型接口')
  expect(w.get('[aria-label="开始匹配模板"]').attributes('disabled')).toBeDefined()
  w.unmount()
})

it('matches a requirement and emits the matched template with a pinned-version card',async()=>{
  vi.spyOn(templatesApi,'matcherStatus').mockResolvedValue({configured:true,provider:'kimi',model:'kimi-latest',threshold:.8})
  vi.spyOn(templatesApi,'match').mockResolvedValue({status:'matched',template_id:'template-1',template_revision_id:'rev-1',confidence:.87,reason:'已完整覆盖需求',uncovered_requirements:[],provider:'kimi',model:'kimi-latest'})
  const w=mount(TemplateSelection,{props:{templates:[template()],selectedId:null}})
  await flushPromises()
  await w.get('button[aria-label="自然语言匹配"]').trigger('click')
  await w.get('input[aria-label="监测需求"]').setValue('监测人员在岗')
  await w.get('[aria-label="开始匹配模板"]').trigger('click')
  await flushPromises()
  expect(w.emitted('matched')).toEqual([['template-1']])
  const outcome=w.get('[aria-label="匹配结果"]')
  expect(outcome.text()).toContain('置信度 87%（模型自评）')
  expect(outcome.text()).toContain('已固定到该发布版本')
  w.unmount()
})

it('reports no_match with uncovered requirements and no analysis claim',async()=>{
  vi.spyOn(templatesApi,'matcherStatus').mockResolvedValue({configured:true,provider:'kimi',model:'kimi-latest',threshold:.8})
  vi.spyOn(templatesApi,'match').mockResolvedValue({status:'no_match',template_id:null,template_revision_id:null,confidence:.4,reason:'没有模板能覆盖夜间低照度要求',uncovered_requirements:['夜间低照度增强'],provider:'kimi',model:'kimi-latest'})
  const w=mount(TemplateSelection,{props:{templates:[template()],selectedId:null}})
  await flushPromises()
  await w.get('button[aria-label="自然语言匹配"]').trigger('click')
  await w.get('input[aria-label="监测需求"]').setValue('夜间入侵')
  await w.get('[aria-label="开始匹配模板"]').trigger('click')
  await flushPromises()
  const outcome=w.get('[aria-label="匹配结果"]')
  expect(outcome.text()).toContain('夜间低照度增强')
  expect(outcome.text()).toContain('未执行任何分析')
  expect(w.emitted('matched')).toBeUndefined()
  w.unmount()
})

it('marks the outcome stale once the requirement text changes',async()=>{
  vi.spyOn(templatesApi,'matcherStatus').mockResolvedValue({configured:true,provider:'kimi',model:'kimi-latest',threshold:.8})
  vi.spyOn(templatesApi,'match').mockResolvedValue({status:'matched',template_id:'template-1',template_revision_id:'rev-1',confidence:.9,reason:'ok',uncovered_requirements:[],provider:'kimi',model:'kimi-latest'})
  const w=mount(TemplateSelection,{props:{templates:[template()],selectedId:null}})
  await flushPromises()
  await w.get('button[aria-label="自然语言匹配"]').trigger('click')
  await w.get('input[aria-label="监测需求"]').setValue('监测人员在岗')
  await w.get('[aria-label="开始匹配模板"]').trigger('click')
  await flushPromises()
  await w.get('input[aria-label="监测需求"]').setValue('监测人员在岗，加夜间')
  expect(w.text()).toContain('需求已修改，当前匹配结果对应旧文本')
  w.unmount()
})

it('asks before replacing an already selected template',async()=>{
  vi.spyOn(templatesApi,'matcherStatus').mockResolvedValue({configured:true,provider:'kimi',model:'kimi-latest',threshold:.8})
  vi.spyOn(templatesApi,'match').mockResolvedValue({status:'matched',template_id:'second',template_revision_id:'rev-2',confidence:.9,reason:'ok',uncovered_requirements:[],provider:'kimi',model:'kimi-latest'})
  const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
  const w=mount(TemplateSelection,{props:{templates:[template(),{...template(),id:'second',name:'区域入侵'}],selectedId:'template-1'}})
  await flushPromises()
  await w.get('button[aria-label="自然语言匹配"]').trigger('click')
  await w.get('input[aria-label="监测需求"]').setValue('禁区入侵')
  await w.get('[aria-label="开始匹配模板"]').trigger('click')
  await flushPromises()
  expect(confirm).toHaveBeenCalled()
  expect(w.emitted('matched')).toBeUndefined()
  confirm.mockReturnValue(true)
  await w.get('[aria-label="开始匹配模板"]').trigger('click')
  await flushPromises()
  expect(w.emitted('matched')).toEqual([['second']])
  w.unmount()
})

it('shows the task pinned version when a newer template version exists',()=>{
  const w=mount(TemplateSelection,{props:{templates:[template(2)],selectedId:'template-1',version:template(1).published_revision,disabled:true}})
  expect(w.get('[aria-label="模板详情"]').text()).toContain('v1')
  expect(w.get('[role="option"]').attributes('disabled')).toBeDefined()
  w.unmount()
})

it('uses business names instead of raw model target and rule identifiers',()=>{
  const t=template();t.published_revision!.config.default_target='person';t.published_revision!.config.default_rule='absence'
  const w=mount(TemplateSelection,{props:{templates:[t],selectedId:t.id}})
  const text=w.get('[aria-label="模板详情"]').text()
  expect(text).toContain('人员在岗');expect(text).not.toContain('absence');expect(text).not.toContain('person')
  w.unmount()
})

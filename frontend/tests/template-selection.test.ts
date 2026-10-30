import { describe,it,expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TemplateSelection from '../src/modules/task-create/TemplateSelection.vue'
import { template } from './fixtures/agentTemplates'

describe('template selection first step',()=>{
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
  it('shows natural-language matching as disabled and never emits a selection for it',async()=>{
    const w=mount(TemplateSelection,{props:{templates:[template()],selectedId:null}})
    const natural=w.get('button[aria-label="自然语言匹配"]')
    expect(natural.attributes('disabled')).toBeDefined()
    expect(natural.text()).toContain('暂未开放')
    await natural.trigger('click')
    expect(w.emitted('select')).toBeUndefined()
    w.unmount()
  })
  it('shows the task pinned version when a newer template version exists',()=>{
    const w=mount(TemplateSelection,{props:{templates:[template(2)],selectedId:'template-1',version:template(1).published_revision,disabled:true}})
    expect(w.get('[aria-label="模板详情"]').text()).toContain('v1')
    expect(w.get('[role="option"]').attributes('disabled')).toBeDefined()
    w.unmount()
  })
})

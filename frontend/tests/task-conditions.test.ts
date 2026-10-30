import { describe,it,expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskConditions from '../src/modules/task-create/TaskConditions.vue'
import ParameterFields from '../src/modules/agents/ParameterFields.vue'
import { pool } from './fixtures/agentTemplates'

describe('shared task conditions',()=>{
  it('merges basic and advanced edits without losing order, values or required flags',async()=>{
    const settings=[{key:'confidence_threshold',value:.5,required:true},{key:'color',value:'red',required:false}]
    const w=mount(TaskConditions,{props:{settings,definitions:pool,sourceCount:2,rule:'absence'},global:{stubs:{ParameterFields:true}}})
    const fields=w.findAllComponents(ParameterFields)
    fields[0]!.vm.$emit('update:settings',[{key:'confidence_threshold',value:.8,required:false}])
    const first=(w.emitted('update:settings')![0]![0]) as typeof settings
    expect(first).toEqual([{key:'confidence_threshold',value:.8,required:true},{key:'color',value:'red',required:false}])
    await w.setProps({settings:first})
    fields[1]!.vm.$emit('update:settings',[{key:'color',value:'blue',required:true}])
    expect(w.emitted('update:settings')![1]![0]).toEqual([{key:'confidence_threshold',value:.8,required:true},{key:'color',value:'blue',required:false}])
    expect(w.text()).toContain('应用于全部 2 路视频')
    expect(w.text()).toContain('恢复确认时长')
    w.unmount()
  })
  it('keeps required advanced fields visible and only shows restoration for absence rules',()=>{
    const w=mount(TaskConditions,{props:{settings:[{key:'color',value:'red',required:true}],definitions:pool,sourceCount:1,rule:'intrusion'},global:{stubs:{ParameterFields:true}}})
    expect(w.getComponent(ParameterFields).props('settings')).toEqual([{key:'color',value:'red',required:true}])
    expect(w.find('details').exists()).toBe(false)
    expect(w.text()).not.toContain('恢复确认时长')
    w.unmount()
  })
})

import { shallowMount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import WorkflowPanel from '../src/modules/agents/WorkflowPanel.vue'
import { agentApi, type AgentDetail, type Revision } from '../src/modules/agents/api'
import { newChannel } from '../src/modules/agents/draft'

afterEach(()=>vi.restoreAllMocks())
it('keeps an existing validation when only the revision object is refreshed',async()=>{
  const revision={id:'r',revision_no:1,state:'draft',latest_validation_id:'v',config:{schema_version:'1.0',channels:[newChannel()]}} as Revision
  const validation=vi.spyOn(agentApi,'validation').mockResolvedValue({id:'v',verdict:'executable',expires_at:'2099-01-01T00:00:00Z'} as any)
  const wrapper=shallowMount(WorkflowPanel,{props:{agent:{id:'a',revisions:[revision]} as AgentDetail,revision,runs:[],sources:[],canWrite:true,runtimeAvailable:true}})
  try{
    await flushPromises()
    await wrapper.setProps({revision:JSON.parse(JSON.stringify(revision))})
    await flushPromises()
    expect(validation).toHaveBeenCalledTimes(1)
    await wrapper.setProps({revision:{...revision,latest_validation_id:'v2'}})
    await flushPromises()
    expect(validation).toHaveBeenLastCalledWith('v2')
  }finally{wrapper.unmount()}
})

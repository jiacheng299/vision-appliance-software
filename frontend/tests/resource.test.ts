import {mount,flushPromises} from '@vue/test-utils'
import {defineComponent,h} from 'vue'
import {describe,it,expect,vi} from 'vitest'
import {useResource} from '../src/shared/ui/resource'
describe('snapshot refresh ordering',()=>{
  it('coalesces dashboard refreshes while a snapshot is in flight',async()=>{
    let resolve!:(value:string)=>void
    const fetch=vi.fn(()=>new Promise<string>(done=>{resolve=done}))
    let resource!:ReturnType<typeof useResource<string>>
    const wrapper=mount(defineComponent({setup(){resource=useResource(fetch,{coalesce:true});return()=>h('div',resource.data.value??'')}}))
    try{
      for(let i=0;i<100;i++)void resource.refresh()
      expect(fetch).toHaveBeenCalledTimes(1)
      resolve('ready');await flushPromises()
      expect(wrapper.text()).toBe('ready')
      const next=resource.refresh();expect(fetch).toHaveBeenCalledTimes(2)
      resolve('updated');await next
      expect(wrapper.text()).toBe('updated')
    }finally{wrapper.unmount()}
  })
  it('keeps the newest query when an older request finishes late',async()=>{
    const pending:Array<(value:string)=>void>=[]
    let refresh:(()=>Promise<void>)|undefined
    const component=defineComponent({setup(){const state=useResource(()=>new Promise<string>(resolve=>pending.push(resolve)));refresh=state.refresh;return ()=>h('div',state.data.value??'')}})
    const wrapper=mount(component)
    const second=refresh!()
    pending[1]!('newest');await second
    pending[0]!('outdated');await flushPromises()
    expect(wrapper.text()).toBe('newest')
    wrapper.unmount()
  })
})

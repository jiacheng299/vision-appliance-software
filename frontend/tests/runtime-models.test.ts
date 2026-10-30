import {flushPromises,mount} from '@vue/test-utils'
import {afterEach,describe,expect,it,vi} from 'vitest'
import RuntimePage from '../src/modules/runtime/RuntimePage.vue'
import {api} from '../src/shared/api'

vi.mock('../src/shared/realtime/useRealtime',()=>({useRealtime:()=>({connected:true})}))

const snapshot=(models:unknown[])=>({
  observed_at:'2026-10-30T08:00:00Z',cpu_percent:10,memory_percent:20,gpu_percent:null,
  disk:{used_bytes:1,total_bytes:10,free_bytes:9},sources:{total:0,online:0},
  runs:{running:0,completed:0,failed:0},services:[],models,workers:[],history:[],
})

afterEach(()=>vi.restoreAllMocks())

describe('runtime model availability',()=>{
  it('shows registered model versions and their actual readiness',async()=>{
    vi.spyOn(api,'runtime').mockResolvedValue(snapshot([{
      id:'model',name:'YOLO11n 人员检测',version:'1.0.0',runtime_type:'yolo11n-onnx-person',
      template_name:'人员在岗监测',status:'ready',message:'模型校验通过，当前本地执行器可用。',data_origin:'real',
    }]) as any)
    vi.spyOn(api,'logs').mockResolvedValue({items:[],next_cursor:null})
    const wrapper=mount(RuntimePage)
    try{
      await flushPromises()
      expect(wrapper.text()).toContain('YOLO11n 人员检测 · 1.0.0')
      expect(wrapper.text()).toContain('人员在岗监测')
      expect(wrapper.text()).toContain('模型校验通过，当前本地执行器可用。')
      expect(wrapper.text()).not.toContain('尚未登记本地模型')
    }finally{wrapper.unmount()}
  })

  it('shows the empty state only when no model version is registered',async()=>{
    vi.spyOn(api,'runtime').mockResolvedValue(snapshot([]) as any)
    vi.spyOn(api,'logs').mockResolvedValue({items:[],next_cursor:null})
    const wrapper=mount(RuntimePage)
    try{await flushPromises();expect(wrapper.text()).toContain('尚未登记本地模型')}
    finally{wrapper.unmount()}
  })
})

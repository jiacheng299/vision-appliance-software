import { describe, it, expect, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import RegionEditor from '../src/modules/agents/RegionEditor.vue'
import { nearPoint, regionError } from '../src/modules/agents/regionGeometry'
import type { Source } from '../src/shared/api/types'
vi.mock('naive-ui',async()=>{
  const {defineComponent}=await import('vue')
  return {NButton:defineComponent({props:['disabled'],template:'<button :disabled="disabled"><slot/></button>'})}
})
afterEach(()=>vi.restoreAllMocks())
function editor(){
  const wrapper=mount(RegionEditor,{props:{regions:[],demo:true}})
  vi.spyOn(wrapper.get('svg').element,'getBoundingClientRect').mockReturnValue({left:0,top:0,width:1000,height:500} as DOMRect)
  const click=(x:number,y:number)=>wrapper.get('svg').trigger('click',{clientX:x,clientY:y})
  const save=()=>wrapper.findAll('button').find(b=>b.text()==='保存区域')!.trigger('click')
  return {wrapper,click,save}
}
describe('region drawing',()=>{
  it('captures the first live frame and lets the user replace it',async()=>{
    let capture=0
    const Player=defineComponent({
      name:'MediaPlayer',
      emits:['frame-ready'],
      setup(_props,{expose}){expose({captureFrame:()=>`data:image/jpeg;base64,frame-${++capture}`})},
      template:'<button data-frame-ready @click="$emit(\'frame-ready\')">frame ready</button>',
    })
    const camera={id:'camera-1',name:'直播',kind:'camera',status:'online',width:960,height:540,thumbnail_url:null} as Source
    const wrapper=mount(RegionEditor,{props:{regions:[],source:camera},global:{stubs:{MediaPlayer:Player}}})

    await wrapper.get('[data-frame-ready]').trigger('click');await flushPromises()
    expect(wrapper.get('img[alt="直播当前帧，用于绘制监测区域"]').attributes('src')).toBe('data:image/jpeg;base64,frame-1')
    await wrapper.findAll('button').find(button=>button.text()==='重新选取当前帧')!.trigger('click')
    expect(wrapper.get('img[alt="直播当前帧，用于绘制监测区域"]').attributes('src')).toBe('data:image/jpeg;base64,frame-2')
    wrapper.unmount()
  })

  it('rejects save until the user returns to the start, then stores no duplicate closing point',async()=>{
    const {wrapper,click,save}=editor()
    await click(100,100);await click(800,100);await click(800,400)
    await save();expect(wrapper.text()).toContain('区域尚未闭合');expect(wrapper.emitted('change')).toBeUndefined()
    await click(105,102);expect(wrapper.text()).toContain('已吸附起点并闭合')
    await save()
    const regions=wrapper.emitted('change')![0]![0] as {points:number[][]}[]
    expect(regions[0]!.points).toEqual([[.1,.2],[.8,.2],[.8,.8]])
    expect(wrapper.text()).toContain('未闭合');wrapper.unmount()
  })
  it('merges only adjacent near clicks in display pixels and allows undoing closure',async()=>{
    const {wrapper,click}=editor()
    await click(100,100);await click(104,102)
    expect(wrapper.text()).toContain('已选 1 个点');expect(wrapper.text()).toContain('自动合并')
    await click(800,100);await click(800,400);await click(100,100)
    await wrapper.findAll('button').find(b=>b.text()==='撤销闭合')!.trigger('click')
    expect(wrapper.text()).toContain('已选 3 个点 · 未闭合')
    expect(nearPoint([0,0],[.005,.005],1000,500)).toBe(true)
    expect(nearPoint([0,0],[.005,.005],4000,2000)).toBe(false)
    wrapper.unmount()
  })
  it('rejects crossing, collinear and overlapping boundaries before emitting a region',async()=>{
    const {wrapper,click,save}=editor()
    for(const [x,y] of [[100,100],[800,400],[100,400],[800,100]])await click(x!,y!)
    await click(100,100);expect(wrapper.text()).toContain('边界不能交叉')
    await save();expect(wrapper.emitted('change')).toBeUndefined();wrapper.unmount()
    expect(regionError([[0,0],[.3,.3],[1,1]])).toContain('面积')
    expect(regionError([[0,0],[1,0],[.5,0],[.5,1]])).not.toBe('')
    expect(regionError([[0,0],[1,0],[0,1]])).toBe('')
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DetectionPreview from '../src/modules/agents/DetectionPreview.vue'
import { agentApi } from '../src/modules/agents/api'

describe('same-frame detection preview', () => {
  let images: Array<{onload: (()=>void)|null; onerror: (()=>void)|null; src:string}>
  beforeEach(() => {
    vi.useFakeTimers()
    images=[]
    vi.stubGlobal('Image', class {
      onload=null; onerror=null; src=''; naturalWidth=640; naturalHeight=480
      constructor(){images.push(this)}
    })
    vi.stubGlobal('URL', {createObjectURL:vi.fn().mockReturnValueOnce('blob:one').mockReturnValue('blob:two'),revokeObjectURL:vi.fn()})
  })
  afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals()})

  it('swaps complete annotated images only after decode and clears stale results', async()=>{
    vi.spyOn(agentApi,'detectionFrame').mockResolvedValueOnce({image:new Blob(['jpeg']),observedAt:'one'}).mockResolvedValue({image:new Blob(['jpeg']),observedAt:'two'})
    const w=mount(DetectionPreview,{props:{agentId:'a',runId:'r'}})
    try {
      await flushPromises()
      expect(w.find('img').exists()).toBe(false)
      images[0]!.onload!();await flushPromises()
      expect(w.get('img').attributes('src')).toBe('blob:one')
      await vi.advanceTimersByTimeAsync(334);await flushPromises()
      expect(w.get('img').attributes('src')).toBe('blob:one')
      images[1]!.onload!();await flushPromises()
      expect(w.get('img').attributes('src')).toBe('blob:two')
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:one')
      vi.mocked(agentApi.detectionFrame).mockResolvedValue(null)
      await vi.advanceTimersByTimeAsync(334);await flushPromises()
      expect(w.find('img').exists()).toBe(false)
      expect(w.text()).toContain('等待新的检测画面')
    } finally {w.unmount()}
  })

  it('ignores a late frame from a previous task and cancels requests on unmount', async()=>{
    let resolve!: (value:any)=>void
    const request=vi.spyOn(agentApi,'detectionFrame').mockImplementationOnce(()=>new Promise(r=>{resolve=r})).mockResolvedValue(null)
    const w=mount(DetectionPreview,{props:{agentId:'a',runId:'old'}})
    await flushPromises()
    const signal=request.mock.calls[0]![2]!
    await w.setProps({runId:'new'});await flushPromises()
    expect(signal.aborted).toBe(true)
    resolve({image:new Blob(['old']),observedAt:'old'});await flushPromises()
    expect(images).toHaveLength(0)
    expect(w.find('img').exists()).toBe(false)
    w.unmount()
    expect(request.mock.calls[1]![2]!.aborted).toBe(true)
  })

  it('clears an old picture even while the next network request is stuck',async()=>{
    vi.spyOn(agentApi,'detectionFrame').mockResolvedValueOnce({image:new Blob(['jpeg']),observedAt:new Date().toISOString()})
      .mockImplementation(()=>new Promise(()=>{}))
    const w=mount(DetectionPreview,{props:{agentId:'a',runId:'r'}})
    try {
      await flushPromises();images[0]!.onload!();await flushPromises()
      expect(w.find('img').exists()).toBe(true)
      await vi.advanceTimersByTimeAsync(3100);await flushPromises()
      expect(w.find('img').exists()).toBe(false)
    } finally {w.unmount()}
  })
})

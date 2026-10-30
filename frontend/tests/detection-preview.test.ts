import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest'
import { flushPromises,mount } from '@vue/test-utils'
import DetectionPreview from '../src/modules/agents/DetectionPreview.vue'

describe('continuous same-frame detection preview',()=>{
  let images:Array<{onload:(()=>void)|null;onerror:(()=>void)|null;src:string}>,streams:ReadableStreamDefaultController<Uint8Array>[]
  beforeEach(()=>{
    vi.useFakeTimers();images=[];streams=[]
    vi.stubGlobal('Image',class {onload=null;onerror=null;src='';naturalWidth=640;naturalHeight=480;constructor(){images.push(this)}})
    let sequence=0
    vi.stubGlobal('URL',{createObjectURL:vi.fn(()=>`blob:frame-${++sequence}`),revokeObjectURL:vi.fn()})
    vi.stubGlobal('fetch',vi.fn(async()=>new Response(new ReadableStream<Uint8Array>({start(c){streams.push(c)}}),{headers:{'content-type':'multipart/x-mixed-replace; boundary=vision-frame'}})))
  })
  afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals()})
  function send(index=0){streams[index]!.enqueue(new TextEncoder().encode(`--vision-frame\r\nContent-Type: image/jpeg\r\nContent-Length: 3\r\nX-Detection-Observed-At: ${new Date().toISOString()}\r\n\r\njpg\r\n`))}

  it('uses one connection and decodes complete frames atomically without replacing the surface',async()=>{
    const w=mount(DetectionPreview,{props:{agentId:'a',runId:'r'}})
    try {
      await flushPromises();send();await flushPromises()
      expect(w.find('img').exists()).toBe(false)
      images[0]!.onload!();await flushPromises()
      const old=w.get('img').element
      expect(w.get('img').attributes('src')).toBe('blob:frame-1')
      send();await flushPromises()
      expect(w.get('img').attributes('src')).toBe('blob:frame-1')
      images[1]!.onload!();await flushPromises()
      expect(w.get('img').element).toBe(old)
      expect(w.get('img').attributes('src')).toBe('blob:frame-2')
      expect(fetch).toHaveBeenCalledTimes(1)
    } finally {w.unmount()}
  })

  it('drops intermediate frames while decoding is slow',async()=>{
    const w=mount(DetectionPreview,{props:{agentId:'a',runId:'r'}})
    try {
      await flushPromises();send();await flushPromises()
      for(let i=0;i<10;i++)send()
      await flushPromises()
      expect(images).toHaveLength(1)
      images[0]!.onload!();await flushPromises()
      expect(images).toHaveLength(2)
      images[1]!.onload!();await flushPromises()
      expect(images).toHaveLength(2)
    } finally {w.unmount()}
  })

  it('clears and reconnects when the image stream stops delivering frames',async()=>{
    const w=mount(DetectionPreview,{props:{agentId:'a',runId:'r'}})
    try {
      await flushPromises();send();await flushPromises();images[0]!.onload!();await flushPromises()
      expect(w.find('img').exists()).toBe(true)
      await vi.advanceTimersByTimeAsync(3100);await flushPromises()
      expect(w.find('img').exists()).toBe(false)
      await vi.advanceTimersByTimeAsync(1000);await flushPromises()
      expect(fetch).toHaveBeenCalledTimes(2)
    } finally {w.unmount()}
  })

  it('cancels the old scope and never displays a late decoded picture from another task',async()=>{
    const w=mount(DetectionPreview,{props:{agentId:'a',runId:'old'}})
    await flushPromises();send();await flushPromises()
    const signal=vi.mocked(fetch).mock.calls[0]![1]!.signal!
    await w.setProps({runId:'new'});await flushPromises()
    expect(signal.aborted).toBe(true)
    images[0]!.onload!();await flushPromises()
    expect(w.find('img').exists()).toBe(false)
    expect(vi.mocked(fetch).mock.calls[1]![0]).toBe('/api/v1/agents/a/runs/new/detection-stream')
    w.unmount()
    expect(vi.mocked(fetch).mock.calls[1]![1]!.signal!.aborted).toBe(true)
  })
})

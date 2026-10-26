import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { useRealtime } from '../src/shared/realtime/useRealtime'

class Socket {
  static instances:Socket[]=[]
  onopen:(()=>void)|null=null
  onmessage:((event:{data:string})=>void)|null=null
  onclose:(()=>void)|null=null
  onerror:(()=>void)|null=null
  send=vi.fn()
  close=vi.fn()
  constructor(){Socket.instances.push(this)}
}
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();Socket.instances=[]})
it('batches notification bursts and cancels scheduled refresh after navigation',async()=>{
  vi.useFakeTimers();vi.stubGlobal('WebSocket',Socket)
  const refresh=vi.fn()
  const wrapper=mount(defineComponent({setup(){useRealtime(refresh);return{}},template:'<div/>'}))
  const socket=Socket.instances[0]!
  try{
    socket.onopen?.();refresh.mockClear()
    const send=(sequence:number)=>socket.onmessage?.({data:JSON.stringify({sequence,event_id:`e-${sequence}`,type:'source'})})
    for(let i=1;i<=100;i++)send(i)
    await vi.advanceTimersByTimeAsync(250)
    expect(refresh).toHaveBeenCalledTimes(1)
    send(100);await vi.advanceTimersByTimeAsync(250)
    expect(refresh).toHaveBeenCalledTimes(1)
    send(101);wrapper.unmount()
    await vi.advanceTimersByTimeAsync(1000)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(socket.close).toHaveBeenCalledOnce()
  }finally{if(wrapper.exists())wrapper.unmount()}
})

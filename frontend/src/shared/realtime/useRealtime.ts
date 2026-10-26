import { onMounted, onUnmounted, ref } from 'vue'
import type { RealtimeEnvelope } from '../api/types'
export function useRealtime(refresh:()=>void) {
  const connected=ref(false)
  let socket:WebSocket|null=null, timer:ReturnType<typeof setTimeout>|undefined, stopped=false, sequence=0
  const eventIds=new Set<string>()
  let refreshTimer:ReturnType<typeof setTimeout>|undefined
  function scheduleRefresh(){
    if(stopped||refreshTimer!==undefined)return
    refreshTimer=setTimeout(()=>{refreshTimer=undefined;if(!stopped)refresh()},250)
  }
  function connect(){
    if(stopped)return
    socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/v1/ws`)
    socket.onopen=()=>{connected.value=true;socket?.send(JSON.stringify({type:'subscribe',topics:['runtime','sources'],...(sequence?{last_sequence:sequence}:{})}));refresh()}
    socket.onmessage=message=>{
      try {
        const event=JSON.parse(String(message.data)) as RealtimeEnvelope
        if(stopped)return
        if(event.type==='resync_required'){sequence=0;eventIds.clear();scheduleRefresh();return}
        if(typeof event.sequence!=='number'||event.sequence<=sequence||eventIds.has(event.event_id))return
        sequence=event.sequence;eventIds.add(event.event_id);if(eventIds.size>500)eventIds.clear()
        scheduleRefresh()
      }catch{/* Non-envelope messages do not change the snapshot. */}
    }
    socket.onclose=()=>{connected.value=false;if(!stopped)timer=setTimeout(connect,5000)}
    socket.onerror=()=>socket?.close()
  }
  onMounted(connect)
  onUnmounted(()=>{stopped=true;clearTimeout(timer);clearTimeout(refreshTimer);socket?.close()})
  return {connected}
}

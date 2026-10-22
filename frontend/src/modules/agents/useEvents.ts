import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { agentApi, type MonitorEvent, type MonitorEventPage, type EventFilters } from './api'
import { mergedEvents, agentError } from './state'
export function useEvents(id:Ref<string>, filters:Ref<EventFilters>) {
  const items=ref<MonitorEvent[]>([]), error=ref(''), connected=ref(false), lastUpdated=ref<string|null>(null), nextCursor=ref<string|null>(null), loading=ref(false)
  let stream:EventSource|null=null,timer:ReturnType<typeof setTimeout>|undefined,generation=0,stopped=false
  const versions=new Map<string,number>()
  function stopStream(){stream?.close();stream=null;connected.value=false;clearTimeout(timer)}
  function matches(e:MonitorEvent){
    const f=filters.value
    return (!f.run_id||e.run_id===f.run_id)&&(!f.review_status||e.review_status===f.review_status)&&(!f.event_type||e.event_type===f.event_type)&&(!f.from_time||Date.parse(e.occurred_at)>=Date.parse(f.from_time))&&(!f.to_time||Date.parse(e.occurred_at)<=Date.parse(f.to_time))
  }
  function connect(cursor:string,request:number){
    if(stopped||request!==generation)return
    stream=new EventSource(`/api/v1/agents/${encodeURIComponent(id.value)}/event-stream?after=${encodeURIComponent(cursor)}`,{withCredentials:true})
    stream.addEventListener('events',message=>{
      if(request!==generation)return
      try{
        const page=JSON.parse((message as MessageEvent).data) as MonitorEventPage
        const valid=page.items.filter(e=>e.agent_id===id.value&&(versions.get(e.id)??0)<=e.row_version)
        for(const event of valid)versions.set(event.id,event.row_version)
        if(versions.size>1500){for(const key of versions.keys()){if(!items.value.some(e=>e.id===key))versions.delete(key);if(versions.size<=1000)break}}
        const removed=new Set(valid.filter(e=>!matches(e)).map(e=>e.id))
        items.value=mergedEvents(items.value.filter(e=>!removed.has(e.id)),valid.filter(matches))
        connected.value=true;error.value='';lastUpdated.value=page.updated_at
      }catch{disconnect('报警数据格式异常，正在重新同步。')}
    })
    stream.addEventListener('resync_required',()=>{if(request===generation)void refresh()})
    stream.addEventListener('unavailable',()=>{if(request===generation)disconnect('报警订阅已断开，历史记录已保留，正在重连。')})
    stream.onerror=()=>{if(request===generation&&!stopped)disconnect('报警订阅已断开，历史记录已保留，正在重连。')}
  }
  function disconnect(message:string){stopStream();error.value=message;if(!stopped)timer=setTimeout(()=>void refresh(),5000)}
  async function refresh(){
    stopStream();const request=++generation;loading.value=true
    try{
      const page=await agentApi.events(id.value,filters.value)
      if(stopped||request!==generation)return
      items.value=mergedEvents([],page.items.filter(e=>e.agent_id===id.value));nextCursor.value=page.next_cursor??null;lastUpdated.value=page.updated_at;error.value=''
      for(const event of items.value)versions.set(event.id,event.row_version)
      connect(page.stream_cursor,request)
    }catch(e){if(!stopped&&request===generation){error.value=agentError(e);timer=setTimeout(()=>void refresh(),5000)}}
    finally{if(request===generation)loading.value=false}
  }
  async function more(){
    if(!nextCursor.value||loading.value)return
    const request=generation;loading.value=true
    try{const page=await agentApi.events(id.value,filters.value,nextCursor.value);if(request===generation){items.value=mergedEvents(items.value,page.items);nextCursor.value=page.next_cursor??null}}
    catch(e){if(request===generation)error.value=agentError(e)}finally{if(request===generation)loading.value=false}
  }
  watch([id,filters],()=>{items.value=[];versions.clear();lastUpdated.value=null;nextCursor.value=null;void refresh()},{deep:true,immediate:true})
  onScopeDispose(()=>{stopped=true;generation++;stopStream()})
  return {items,error,connected,lastUpdated,nextCursor,loading,refresh,more}
}

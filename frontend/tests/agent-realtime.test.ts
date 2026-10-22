import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { agentApi, type EventFilters, type MonitorEvent, type MonitorEventPage, type Operation, type Workspace } from '../src/modules/agents/api'
import { mergedEvents, configChanges } from '../src/modules/agents/state'
import { useEvents } from '../src/modules/agents/useEvents'
import { useWorkspace } from '../src/modules/agents/useWorkspace'
import { emptyConfig, newChannel } from '../src/modules/agents/draft'

class EventStream extends EventTarget {
  static instances:EventStream[]=[]
  onerror:(()=>void)|null=null
  closed=false
  constructor(public url:string){super();EventStream.instances.push(this)}
  close(){this.closed=true}
  send(type:string,payload:unknown){this.dispatchEvent(new MessageEvent(type,{data:JSON.stringify(payload)}))}
}
function event(id='event-1',version=1):MonitorEvent {
  return {id,agent_id:'agent-1',run_id:'run-old',revision_id:'revision-old',source_id:'source-1',channel_id:'channel-1',occurred_at:'2026-10-20T01:00:00Z',updated_at:'2026-10-20T01:00:00Z',row_version:version,event_type:'区域滞留',severity:'warning',reason:'由服务提供的依据',evidence_status:'ready',review_status:'unreviewed',feedback_reason:'',data_origin:'mock'}
}
function page(items:MonitorEvent[],cursor='1'):MonitorEventPage{return {items,next_cursor:null,stream_cursor:cursor,updated_at:'2026-10-20T01:00:00Z',data_origin:'mock',resync_required:false,today_count:items.length}}
function mountEvents(){
  const id=ref('agent-1'),filters=ref<EventFilters>({})
  let feed!:ReturnType<typeof useEvents>
  const wrapper=mount(defineComponent({setup(){feed=useEvents(id,filters);return{}},template:'<div/>'}))
  return {wrapper,id,filters,get feed(){return feed}}
}
beforeEach(()=>{vi.useFakeTimers();sessionStorage.clear();EventStream.instances=[];vi.stubGlobal('EventSource',EventStream)})
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals()})

describe('event stream correctness',()=>{
  it('deduplicates event ids and does not roll back a newer review',async()=>{
    vi.spyOn(agentApi,'events').mockResolvedValue(page([event()]))
    const subject=mountEvents();await flushPromises()
    const stream=EventStream.instances[0]!
    stream.send('events',page([{...event('event-1',2),review_status:'false_positive'},event('event-1',2)],'2'))
    // Same-version duplicate delivery must not add another row.
    expect(subject.feed.items.value).toHaveLength(1)
    stream.send('events',page([{...event('event-1',3),review_status:'correct'}],'3'))
    stream.send('events',page([event('event-1',1)],'4'))
    expect(subject.feed.items.value[0]!.row_version).toBe(3)
    expect(subject.feed.items.value[0]!.review_status).toBe('correct')
    subject.wrapper.unmount();expect(stream.closed).toBe(true)
  })
  it('retains history on disconnect, then compensates with a fresh snapshot',async()=>{
    const fetch=vi.spyOn(agentApi,'events').mockResolvedValueOnce(page([event()])).mockResolvedValue(page([event(),event('event-2')],'2'))
    const subject=mountEvents();await flushPromises()
    EventStream.instances[0]!.send('events',page([]))
    expect(subject.feed.connected.value).toBe(true)
    EventStream.instances[0]!.onerror?.()
    expect(subject.feed.connected.value).toBe(false)
    expect(subject.feed.items.value).toHaveLength(1)
    expect(subject.feed.error.value).toContain('历史记录已保留')
    await vi.advanceTimersByTimeAsync(5000);await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(subject.feed.items.value).toHaveLength(2)
    expect(EventStream.instances[1]!.url).toContain('after=2')
    subject.wrapper.unmount()
  })
  it('a stale stream cannot disconnect another agent after navigation',async()=>{
    vi.spyOn(agentApi,'events').mockImplementation(async id=>page([{...event(),agent_id:id}]))
    const subject=mountEvents();await flushPromises();const old=EventStream.instances[0]!
    subject.id.value='agent-2';await flushPromises();const current=EventStream.instances[1]!
    current.send('events',page([{...event(),agent_id:'agent-2'}]))
    old.onerror?.();old.send('events',page([event('foreign')]))
    expect(subject.feed.connected.value).toBe(true)
    expect(current.closed).toBe(false)
    expect(subject.feed.items.value.every(e=>e.agent_id==='agent-2')).toBe(true)
    subject.wrapper.unmount()
  })
})

describe('operation tracking',()=>{
  it('keeps a submitted command pending until the server confirms completion',async()=>{
    const snapshot:Workspace={agent_id:'agent-1',runs:[],runtime_available:true,runtime_error:'',observed_at:'2026-10-20T01:00:00Z',data_origin:'mock'}
    vi.spyOn(agentApi,'workspace').mockResolvedValue(snapshot)
    const pending:Operation={id:'op-1',agent_id:'agent-1',kind:'start',state:'pending',channels:[],message:'受理',data_origin:'mock'}
    vi.spyOn(agentApi,'operation').mockResolvedValue({...pending,state:'succeeded'})
    let tracker!:ReturnType<typeof useWorkspace>;const settled=vi.fn()
    const wrapper=mount(defineComponent({setup(){tracker=useWorkspace(ref('agent-1'),settled);return{}},template:'<div/>'}))
    await flushPromises();tracker.track(pending);await flushPromises()
    expect(tracker.operations.value[0]!.state).toBe('pending')
    expect(settled).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000);await flushPromises()
    expect(tracker.operations.value[0]!.state).toBe('succeeded')
    expect(settled).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
})

describe('snapshot diff and duplicate delivery',()=>{
  it('shows changed rules without modifying either snapshot',()=>{
    const before=emptyConfig(),channel=newChannel();channel.duration_seconds=30;before.channels=[channel]
    const after=JSON.parse(JSON.stringify(before));after.channels[0].duration_seconds=60
    expect(configChanges(before,after)).toContainEqual({channel:channel.name,field:'持续时长（秒）',before:'30',after:'60'})
    expect(before.channels[0]!.duration_seconds).toBe(30)
    expect(mergedEvents([event()],[event(),event()])).toHaveLength(1)
  })
})

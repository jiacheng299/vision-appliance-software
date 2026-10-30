import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { readFileSync } from 'node:fs'
import RunPlayer from '../src/modules/agents/RunPlayer.vue'
import MonitorPanel from '../src/modules/agents/MonitorPanel.vue'
import { agentApi, type Revision, type Run, type Workspace } from '../src/modules/agents/api'
import { label } from '../src/modules/agents/state'

vi.mock('naive-ui', async () => {
  const { defineComponent } = await import('vue')
  return {
    NButton: defineComponent({ template: '<button><slot/></button>' }),
    NSelect: defineComponent({ template: '<div/>' }),
  }
})

function playback() {
  return {
    id: 'session-1', agent_id: 'agent-1', run_id: 'run-1', protocol: 'mock' as const,
    expires_at: new Date(Date.now() + 60_000).toISOString(), message: '',
    media_origin_ms: 0, data_origin: 'mock' as const, detection_available:false,
  }
}

const run = (alert_state: Run['alert_state']): Run => ({
  id: 'run-1', agent_id: 'agent-1', revision_id: 'revision-1', revision_no: 1,
  channel_id: 'channel-1', channel_name: '主通道', source_id: 'source-1', source_kind: 'camera',
  state: 'running', recording_available: false, config_snapshot: { schema_version: '1.0', channels: [] },
  message: '', alert_state, data_origin: 'real',
} as Run)

describe('persisted absence alert presentation', () => {
  it('defaults to same-frame detection and never overlays old person boxes on original video',async()=>{
    vi.spyOn(HTMLMediaElement.prototype,'canPlayType').mockReturnValue('probably')
    vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{})
    vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{})
    vi.spyOn(agentApi,'releasePlayback').mockResolvedValue({} as never)
    vi.spyOn(agentApi,'detectionFrame').mockResolvedValue(null)
    const load=async()=>({...playback(),protocol:'hls' as const,data_origin:'real' as const,detection_available:true,
      playback_url:'/api/v1/sources/camera/live/index.m3u8',regions:[],targets:[{id:'old',label:'person',x:.1,y:.1,width:.2,height:.4}]})
    const w=mount(RunPlayer,{props:{identity:'run',agentId:'agent-1',load,isLive:true}})
    try {
      await flushPromises()
      expect(w.find('.detection-preview').exists()).toBe(true)
      expect(w.find('video').exists()).toBe(false)
      expect(w.find('rect').exists()).toBe(false)
      await w.findAll('button').find(b=>b.text()==='切换原始视频')!.trigger('click');await flushPromises()
      expect(w.find('video').exists()).toBe(true)
      expect(w.find('rect').exists()).toBe(false)
      await w.findAll('button').find(b=>b.text()==='切换检测画面')!.trigger('click');await flushPromises()
      expect(w.find('.detection-preview').exists()).toBe(true)
      expect(w.find('video').exists()).toBe(false)
    } finally {w.unmount();vi.restoreAllMocks()}
  })
  it('automatically opens a new live player after a real media failure',async()=>{
    vi.useFakeTimers()
    vi.spyOn(HTMLMediaElement.prototype,'canPlayType').mockReturnValue('probably')
    vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{})
    vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{})
    vi.spyOn(agentApi,'releasePlayback').mockResolvedValue({} as never)
    const load=vi.fn(async()=>({...playback(),protocol:'hls' as const,playback_url:'/api/v1/sources/camera/live/index.m3u8',regions:[],targets:[]}))
    const wrapper=mount(RunPlayer,{props:{identity:'live',agentId:'agent-1',load,isLive:true}})
    try{
      await flushPromises()
      const old=wrapper.get('video').element
      Object.defineProperty(old,'error',{configurable:true,value:{code:2}})
      await wrapper.get('video').trigger('error')
      expect(wrapper.text()).toContain('正在自动重连')
      await vi.advanceTimersByTimeAsync(1000);await flushPromises()
      expect(wrapper.get('video').element).not.toBe(old)
      await wrapper.get('video').trigger('playing')
      expect(wrapper.find('.error-banner').exists()).toBe(false)
    }finally{wrapper.unmount();vi.useRealTimers();vi.restoreAllMocks()}
  })
  it('ignores an old media error and clears a real error after playback recovers', async () => {
    vi.spyOn(HTMLMediaElement.prototype,'canPlayType').mockReturnValue('probably')
    vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{})
    vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{})
    vi.spyOn(agentApi,'releasePlayback').mockResolvedValue({} as never)
    const load=vi.fn(async()=>({...playback(),protocol:'hls' as const,playback_url:'/api/v1/sources/camera/live/index.m3u8',regions:[],targets:[]}))
    const wrapper=mount(RunPlayer,{props:{identity:'old',agentId:'agent-1',load}})
    try{
      await flushPromises()
      await wrapper.get('video').trigger('error')
      expect(wrapper.text()).not.toContain('视频无法播放或已断流')
      const old=wrapper.get('video').element
      await wrapper.setProps({identity:'new'})
      await flushPromises()
      expect(wrapper.get('video').element).not.toBe(old)
      Object.defineProperty(wrapper.get('video').element,'error',{configurable:true,value:{code:4}})
      await wrapper.get('video').trigger('error')
      expect(wrapper.text()).toContain('视频无法播放或已断流')
      await wrapper.get('video').trigger('playing')
      expect(wrapper.text()).not.toContain('视频无法播放或已断流')
    }finally{wrapper.unmount();vi.restoreAllMocks()}
  })
  it('updates live targets without replacing the playing surface', async () => {
    vi.useFakeTimers()
    vi.spyOn(agentApi,'releasePlayback').mockResolvedValue({} as never)
    let x=.1
    const load=vi.fn(async()=>({...playback(),observed_at:new Date().toISOString(),regions:[],
      targets:[{id:'person',label:'person',x,y:.2,width:.1,height:.2}]}))
    const wrapper=mount(RunPlayer,{props:{identity:'run-live',agentId:'agent-1',load,isLive:true}})
    try{
      await flushPromises()
      const surface=wrapper.get('.run-frame').element
      expect(wrapper.get('rect').attributes('x')).toBe('100')
      x=.6
      await vi.advanceTimersByTimeAsync(1000)
      await flushPromises()
      expect(wrapper.get('rect').attributes('x')).toBe('600')
      expect(wrapper.get('.run-frame').element).toBe(surface)
      expect(load).toHaveBeenCalledTimes(2)
    }finally{wrapper.unmount();vi.useRealTimers()}
  })
  it('offers a failed run retry with its original revision and error reason', async () => {
    const failed = {...run('normal'),state:'failed',message:'视频解码工具不可用',error_code:'dependency_unavailable'} as Run
    const wrapper = mount(MonitorPanel, {props:{
      agentId:'agent-1',revision:{id:'revision-1',config:{schema_version:'1.0',channels:[]}} as unknown as Revision,
      workspace:{runs:[failed],runtime_available:true} as Workspace,sources:[],canWrite:true,
    },global:{stubs:{RunPlayer:true,EventsPanel:true,VideoWall:true,AgentStatus:true}}})
    expect(wrapper.text()).toContain('视频解码工具不可用')
    await wrapper.findAll('button').find(b=>b.text()==='重新监测')!.trigger('click')
    expect(wrapper.emitted('retry')?.[0]?.[0]).toEqual(failed)
    wrapper.unmount()
  })
  it('translates absence event machine values for the event feed', () => {
    expect(label('person_absence')).toBe('人员缺岗')
    expect(label('person_presence_restored')).toBe('恢复在岗')
  })

  it('keeps the picture red until persisted run state returns to normal without reloading media', async () => {
    vi.spyOn(agentApi, 'releasePlayback').mockResolvedValue({} as never)
    const load = vi.fn(async () => playback())
    const wrapper = mount(RunPlayer, { props: {
      identity: 'run-1', agentId: 'agent-1', load, alertActive: true, alertLabel: '人员缺岗',
    } })
    await flushPromises()

    expect(wrapper.get('.run-player-surface').classes()).toContain('alert-active')
    expect(wrapper.get('.run-frame').classes()).toContain('alert-active')
    expect(wrapper.get('[role="alert"]').text()).toBe('人员缺岗')
    expect(load).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ alertActive: false })
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('.run-player-surface').classes()).not.toContain('alert-active')
    expect(wrapper.get('.run-frame').classes()).not.toContain('alert-active')
    expect(load).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ alertActive: true })
    expect(wrapper.get('.run-frame').classes()).toContain('alert-active')
    expect(wrapper.get('[role="alert"]').text()).toBe('人员缺岗')
    expect(load).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('draws the red frame above frame contents and keeps the banner on top', () => {
    const styles = readFileSync('src/modules/agents/agents.css', 'utf8')
    expect(styles).toMatch(/\.run-frame\.alert-active::after\{[^}]*z-index:\s*\d+/)
    expect(styles).toMatch(/\.run-alert-banner\{[^}]*z-index:\s*\d+/)
    expect(styles).not.toContain('.run-player-surface.alert-active{box-shadow:')
  })

  it('passes selected single-run alert state to its player', () => {
    const playerStub = defineComponent({
      props: ['alertActive', 'alertLabel'],
      template: '<div class="player-stub" :data-alert-active="alertActive" :data-alert-label="alertLabel"/>',
    })
    const wrapper = mount(MonitorPanel, { props: {
      agentId: 'agent-1', revision: { id: 'revision-1', agent_id: 'agent-1', revision_no: 1, base_revision_id: null, state: 'published', config: { schema_version: '1.0', channels: [] }, row_version: 1, created_at: '', updated_at: '' } as Revision,
      workspace: { agent_id: 'agent-1', runs: [run('absence')], runtime_available: true, runtime_error: '', observed_at: '', data_origin: 'real' } as Workspace,
      sources: [], canWrite: false,
    }, global: { stubs: { RunPlayer: playerStub, EventsPanel: true, VideoWall: true, AgentStatus: true } } })

    expect(wrapper.get('.player-stub').attributes('data-alert-active')).toBe('true')
    expect(wrapper.get('.player-stub').attributes('data-alert-label')).toBe('人员缺岗')
    wrapper.unmount()
  })
})

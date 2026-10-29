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
    media_origin_ms: 0, data_origin: 'mock' as const,
  }
}

const run = (alert_state: Run['alert_state']): Run => ({
  id: 'run-1', agent_id: 'agent-1', revision_id: 'revision-1', revision_no: 1,
  channel_id: 'channel-1', channel_name: '主通道', source_id: 'source-1', source_kind: 'camera',
  state: 'running', recording_available: false, config_snapshot: { schema_version: '1.0', channels: [] },
  message: '', alert_state, data_origin: 'real',
} as Run)

describe('persisted absence alert presentation', () => {
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

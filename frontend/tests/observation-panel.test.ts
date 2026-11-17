import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NSelect } from 'naive-ui'
import { agentApi, type Observation, type ObservationPage, type Revision, type Workspace } from '../src/modules/agents/api'
import ObservationPanel from '../src/modules/agents/ObservationPanel.vue'
import MonitorPanel from '../src/modules/agents/MonitorPanel.vue'

const sources = [{ id: 'one', name: '一号录像' }, { id: 'two', name: '二号录像' }]
const blocked: Observation = {
  id: 'obs-blocked', agent_id: 'task', run_id: 'run-two', source_id: 'two', task_key: 'person/absence',
  roi: [], window_start: 60, window_end: 90, route_version: 'local-r1', profile_version: 2,
  model_version: '1', path_id: 'channel', verdict: 'insufficient', detection_count: 0,
  metrics: { frame_count: 30, actual_fps: null, overexposure_ratio: null },
  thresholds: {}, gates: [], reasons: ['监测区域过曝比例超过门槛。'], created_at: '2026-11-17T03:00:00Z',
}
const empty: Observation = {
  ...blocked, id: 'obs-empty', source_id: 'one', run_id: 'run-one', verdict: 'not_detected',
  reasons: [], metrics: { frame_count: 30, actual_fps: 1.02, overexposure_ratio: 0.05 },
}
const page = (items: Observation[]): ObservationPage => ({
  items, next_cursor: null, summary: { detected: 0, not_detected: 1, insufficient: 2 },
})
afterEach(() => vi.restoreAllMocks())

it('shows the three-state verdict with its evidence and filters by verdict', async () => {
  const request = vi.spyOn(agentApi, 'observations').mockImplementation(
    async (_id, filters) => page(filters?.verdict ? [blocked] : [empty, blocked]))
  const wrapper = mount(ObservationPanel, {
    props: { agentId: 'task', sources, runs: sources.map(source => ({ source_id: source.id })) },
  })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('限定窗口未检出')
    expect(wrapper.text()).toContain('观察不足')
    expect(wrapper.text()).toContain('60.0–90.0 秒')
    expect(wrapper.text()).toContain('未测定')
    expect(wrapper.text()).toContain('监测区域过曝比例超过门槛。')
    expect(wrapper.text()).toContain('观察条件全部满足')
    expect(wrapper.get('[aria-label="观察结论统计"]').text()).toContain('观察不足 2')
    const verdictSelect = wrapper.findAllComponents(NSelect)[1]
    verdictSelect.vm.$emit('update:value', 'insufficient')
    await flushPromises()
    expect(request.mock.calls.at(-1)?.[1]).toMatchObject({ verdict: 'insufficient' })
    expect(wrapper.text()).not.toContain('观察条件全部满足')
  } finally { wrapper.unmount() }
})

it('states the limits of an absence verdict in the panel itself', async () => {
  vi.spyOn(agentApi, 'observations').mockResolvedValue(page([empty]))
  const wrapper = mount(ObservationPanel, {
    props: { agentId: 'task', sources, runs: sources.map(source => ({ source_id: source.id })) },
  })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('观察不足不等于事件未发生')
    expect(wrapper.text()).toContain('未检出也不外推到其他时段或区域')
  } finally { wrapper.unmount() }
})

it('reads real observation records only while the panel is open', async () => {
  const request = vi.spyOn(agentApi, 'observations').mockResolvedValue(page([]))
  const workspace: Workspace = { agent_id: 'task', runs: [], data_origin: 'real', runtime_available: true,
    runtime_error: '', observed_at: empty.created_at }
  const revision: Revision = { id: 'revision', agent_id: 'task', revision_no: 1, base_revision_id: null,
    state: 'published', row_version: 1, created_at: empty.created_at, updated_at: empty.created_at,
    config: { schema_version: '1.0', channels: [] } }
  const wrapper = mount(MonitorPanel, {
    props: { agentId: 'task', sources: [], canWrite: false, workspace, revision },
    global: { stubs: { EventsPanel: true, MediaPlayer: true, VideoWall: true } },
  })
  try {
    await flushPromises()
    expect(request).not.toHaveBeenCalled()
    const toggle = wrapper.get('button[aria-label="有效观察"]')
    await toggle.trigger('click')
    await flushPromises()
    expect(request).toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无有效观察记录')
    await toggle.trigger('click')
    expect(wrapper.find('[aria-label="有效观察记录"]').exists()).toBe(false)
    await wrapper.setProps({ workspace: { ...workspace, data_origin: 'mock' } })
    expect(wrapper.find('button[aria-label="有效观察"]').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

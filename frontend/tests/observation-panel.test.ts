import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NSelect } from 'naive-ui'
import { agentApi, type Observation, type ObservationPage, type Revision, type Workspace } from '../src/modules/agents/api'
import { profileApi } from '../src/modules/sources/profileApi'
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
    expect(wrapper.text()).toContain('需要调整的部分')
    expect(wrapper.text()).not.toMatch(/门禁|路由|画像|ΔJ|\b[SMF]\d+\b/)
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
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([])
  vi.spyOn(profileApi, 'read').mockResolvedValue({ source_id: 'one', view_version: '1', version: 1,
    intrinsic: {}, runtime: {}, attributes: [], evaluated_at: 0, updated_at: empty.created_at })
  const wrapper = mount(MonitorPanel, {
    props: { agentId: 'task', sources: [], canWrite: false, workspace, revision },
    global: { stubs: { EventsPanel: true, MediaPlayer: true, VideoWall: true } },
  })
  try {
    await flushPromises()
    // 顶部摘要条确实会取一次结论分布，但观察列表本身在打开页签前不渲染
    expect(wrapper.find('section[aria-label="观察记录"]').exists()).toBe(false)
    const before = request.mock.calls.length
    const observationTab = wrapper.get('button[aria-label="观察记录"]')
    expect(wrapper.get('[role="tablist"]').text()).toContain('画面')
    expect(wrapper.get('[role="tablist"]').text()).toContain('事件')
    await observationTab.trigger('click')
    await flushPromises()
    expect(request.mock.calls.length).toBeGreaterThan(before)
    expect(wrapper.text()).toContain('暂无观察记录')
    // 切回画面页签后，观察面板应被卸载，不再持有数据
    await wrapper.get('button[aria-label="画面"]').trigger('click')
    expect(wrapper.find('section[aria-label="观察记录"]').exists()).toBe(false)
    // 模拟数据源不显示交底书相关的两个页签
    await wrapper.setProps({ workspace: { ...workspace, data_origin: 'mock' } })
    expect(wrapper.find('button[aria-label="观察记录"]').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="模型组合"]').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

it('shows the model combination version of each window and keeps the existing jump action', async () => {
  vi.spyOn(agentApi, 'observations').mockResolvedValue(page([empty]))
  const wrapper = mount(ObservationPanel, {
    props: { agentId: 'task', sources, runs: sources.map(source => ({ source_id: source.id })) },
  })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('local-r1')
    await wrapper.get('[aria-label="查看该视频源的模型组合"]').trigger('click')
    expect(wrapper.emitted('openRoute')?.[0]).toEqual(['one'])
  } finally { wrapper.unmount() }
})
it('translates stored version-mismatch reasons into the same business language', async () => {
  vi.spyOn(agentApi, 'observations').mockResolvedValue(page([{ ...empty, verdict: 'insufficient',
    reasons: ['路由、画像或模型版本与当前不一致。'] }]))
  const wrapper = mount(ObservationPanel, {
    props: { agentId: 'task', sources, runs: sources.map(source => ({ source_id: source.id })) },
  })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('模型组合、场景记录或模型版本与当前不一致。')
    expect(wrapper.text()).not.toMatch(/路由|画像/)
  } finally { wrapper.unmount() }
})

const withGates: Observation = {
  ...blocked,
  gates: [
    { name: 'actual_fps', status: 'pass', value: 1.0, threshold: 0.9, reason: null },
    { name: 'overexposure_ratio', status: 'pass', value: 0.03, threshold: 0.2, reason: null },
    { name: 'blur_score', status: 'unverified', value: null, threshold: 50, reason: 'unverified_quality' },
    { name: 'path_complete', status: 'pass', value: 1, threshold: 1, reason: null },
    { name: 'version_consistency', status: 'pass', value: null, threshold: null, reason: null },
  ],
  metrics: { frame_count: 30, actual_fps: 1.02, max_gap_seconds: 1.1, roi_visible_ratio: 1,
    overexposure_ratio: 0.05, blur_score: null, occlusion_ratio: null, target_scale_px: 48 },
}

it('opens the observation conditions of one window and admits what was never measured', async () => {
  vi.spyOn(agentApi, 'observations').mockResolvedValue(page([withGates]))
  const wrapper = mount(ObservationPanel, {
    props: { agentId: 'task', sources, runs: sources.map(source => ({ source_id: source.id })) },
  })
  try {
    await flushPromises()
    expect(wrapper.find('[aria-label="观察条件明细"]').exists()).toBe(false)
    await wrapper.get('[aria-label="查看该条观察的观察条件"]').trigger('click')
    const detail = wrapper.get('[aria-label="观察条件明细"]')
    expect(detail.text()).toContain('观察不足')
    expect(detail.text()).toContain('实际帧率')
    expect(detail.text()).toContain('通过')
    expect(detail.text()).toContain('画面清晰度')
    expect(detail.text()).toContain('未测定')
    expect(detail.text()).toContain('画面质量指标未测定')
    expect(detail.text()).not.toMatch(/门禁|路由|画像/)
    const metrics = wrapper.get('[aria-label="实测指标"]')
    expect(metrics.text()).toContain('画面清晰度：未测定')
    expect(metrics.text()).toContain('遮挡比例：未测定')
    expect(metrics.text()).toContain('可辨目标尺度：48 像素')
    expect(detail.text()).toContain('模型组合版本 local-r1')
    await wrapper.findAll('button').find(button => button.text() === '关闭')!.trigger('click')
    expect(wrapper.find('[aria-label="观察条件明细"]').exists()).toBe(false)
  } finally { wrapper.unmount() }
})
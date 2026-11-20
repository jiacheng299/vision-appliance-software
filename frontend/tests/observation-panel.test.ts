import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NSelect } from 'naive-ui'
import { agentApi, type Observation, type ObservationPage, type Revision, type Workspace } from '../src/modules/agents/api'
import { profileApi } from '../src/modules/sources/profileApi'
import type { Source } from '../src/shared/api/types'
import ObservationPanel from '../src/modules/agents/ObservationPanel.vue'
import MonitorPanel from '../src/modules/agents/MonitorPanel.vue'

const sources = [{ id: 'one', name: '一号录像' }, { id: 'two', name: '二号录像' }]
const blocked: Observation = {
  id: 'obs-blocked', agent_id: 'task', run_id: 'run-two', source_id: 'two', task_key: 'person/absence',
  roi: [], window_start: 60, window_end: 90, route_version: 'local-r1', profile_version: 2,
  model_version: '1', path_id: 'channel-two', verdict: 'insufficient', detection_count: 0,
  metrics: { frame_count: 30, actual_fps: null, overexposure_ratio: null },
  thresholds: {}, gates: [], reasons: ['监测区域过曝比例超过门槛。'], created_at: '2026-11-17T03:00:00Z',
}
const empty: Observation = {
  ...blocked, id: 'obs-empty', source_id: 'one', run_id: 'run-one', path_id: 'channel', verdict: 'not_detected',
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
    expect(wrapper.emitted('openRoute')?.[0]).toEqual([{ sourceId: 'one', channelId: 'channel' }])
  } finally { wrapper.unmount() }
})
function mountMultiSourcePanel() {
  const observedAt = '2026-11-17T03:00:00Z'
  const revision: Revision = { id: 'revision', agent_id: 'task', revision_no: 1, base_revision_id: null,
    state: 'published', row_version: 1, created_at: observedAt, updated_at: observedAt,
    config: { schema_version: '1.0', channels: [
      { channel_id: 'channel-one', name: '一号岗位', target: 'person', rule: 'absence', duration_seconds: 30,
        requirement_text: '一号岗位人员监测', sources: [{ source_id: 'one', regions: [] }], parameters: [] },
      { channel_id: 'channel-two', name: '二号岗位', target: 'person', rule: 'presence', duration_seconds: 45,
        requirement_text: '二号岗位人员监测', sources: [{ source_id: 'two', regions: [] }], parameters: [] },
    ] } }
  const workspace: Workspace = { agent_id: 'task', runs: [], data_origin: 'real', runtime_available: true,
    runtime_error: '', observed_at: observedAt }
  const observationRequest = vi.spyOn(agentApi, 'observations').mockResolvedValue(page([blocked]))
  const routeRequest = vi.spyOn(agentApi, 'routes').mockImplementation(async sourceId => ({
    source_id: sourceId, rule: sourceId === 'two' ? 'presence' : 'absence', profile_version: 0,
    scenario: { bucket: 'default', reasons: [] }, graph: { requirements: [], edges: [] },
    capabilities: [], chosen: null, ranked: [], blocked: [], weights: {}, budgets: {},
    min_quality: 0.6, notices: [],
  }))
  const timelineRequest = vi.spyOn(agentApi, 'routeTimeline').mockResolvedValue([])
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([{
    agent_id: 'task', channel_id: 'channel-two', source_id: 'two', rule: 'presence',
    active_members: ['model-two'], active_version: 'route-two', active_since: 1,
    mode: 'stable', candidate_members: null, candidate_score: null, valid_windows: 1,
    hard_failure: false, delta_j: null, drift: [], affected: [], fixed: [], escalated: false,
    chosen: null, notices: [], updated_at: observedAt,
  }])
  vi.spyOn(agentApi, 'routeDecisions').mockResolvedValue([])
  const profileRequest = vi.spyOn(profileApi, 'read').mockImplementation(async sourceId => ({
    source_id: sourceId, view_version: '1', version: sourceId === 'two' ? 9 : 3,
    intrinsic: {}, runtime: {}, attributes: [], evaluated_at: 0, updated_at: observedAt,
  }))
  vi.spyOn(agentApi, 'trackerPolicies').mockResolvedValue({ items: [], active: 'heuristic-iou',
    resolved: { spec: 'heuristic-iou', available: true, name: 'heuristic-iou',
      label: '固定机位 IoU/中心距关联', kind: 'heuristic', external: false, detail: {} }, notice: '' })
  const wrapper = mount(MonitorPanel, {
    props: { agentId: 'task', sources: sources as unknown as Source[], canWrite: false, workspace, revision },
    global: { stubs: { EventsPanel: true, MediaPlayer: true, VideoWall: true } },
  })
  return { wrapper, revision, observationRequest, routeRequest, timelineRequest, profileRequest }
}

async function openSecondRoute(wrapper: ReturnType<typeof mountMultiSourcePanel>['wrapper']) {
  await flushPromises()
  await wrapper.get('button[aria-label="观察记录"]').trigger('click')
  await flushPromises()
  await wrapper.get('[aria-label="查看该视频源的模型组合"]').trigger('click')
  await flushPromises()
}

it('keeps the second video context across observation, model combination and summary', async () => {
  const { wrapper, observationRequest, routeRequest, timelineRequest, profileRequest } = mountMultiSourcePanel()
  try {
    await openSecondRoute(wrapper)
    expect(routeRequest).toHaveBeenLastCalledWith('two', { rule: 'presence', duration_seconds: 45 })
    expect(timelineRequest).toHaveBeenLastCalledWith('task', {
      channel_id: 'channel-two', source_id: 'two', limit: 12 })
    expect(profileRequest).toHaveBeenLastCalledWith('two')
    expect(observationRequest).toHaveBeenLastCalledWith('task', { source_id: 'two' }, undefined)
    expect(wrapper.get('section[aria-label="模型组合"] .panel-title').text()).toContain('二号录像')
    const summary = wrapper.get('[aria-label="任务可观察性摘要"]')
    expect(summary.text()).toContain('当前视频')
    expect(summary.text()).toContain('v9')
    expect(summary.text()).toContain('route-two')
    expect(summary.text()).toContain('model-two')
  } finally { wrapper.unmount() }
})

it('keeps the selected channel when two channels with different rules share one video', async () => {
  const { wrapper, revision, routeRequest, timelineRequest } = mountMultiSourcePanel()
  try {
    const channels = revision.config.channels!
    await wrapper.setProps({ revision: { ...revision, config: { ...revision.config, channels: [
      { ...channels[0], sources: [{ source_id: 'two', regions: [] }] }, channels[1],
    ] } } })
    await openSecondRoute(wrapper)
    expect(routeRequest).toHaveBeenLastCalledWith('two', { rule: 'presence', duration_seconds: 45 })
    expect(timelineRequest).toHaveBeenLastCalledWith('task', {
      channel_id: 'channel-two', source_id: 'two', limit: 12 })
    expect(wrapper.get('[aria-label="任务可观察性摘要"]').text()).toContain('route-two')
  } finally { wrapper.unmount() }
})

it('re-resolves the selected video rule and duration when the revision changes', async () => {
  const { wrapper, revision, routeRequest } = mountMultiSourcePanel()
  try {
    await openSecondRoute(wrapper)
    const channels = revision.config.channels!
    const changedRule: Revision = { ...revision, revision_no: 2, config: { ...revision.config,
      channels: [channels[0], { ...channels[1], rule: 'absence' }] } }
    await wrapper.setProps({ revision: changedRule })
    await flushPromises()
    expect(routeRequest).toHaveBeenLastCalledWith('two', { rule: 'absence', duration_seconds: 45 })
    const changedDuration: Revision = { ...changedRule, config: { ...changedRule.config,
      channels: [channels[0], { ...channels[1], rule: 'absence', duration_seconds: 60 }] } }
    await wrapper.setProps({ revision: changedDuration })
    await flushPromises()
    expect(routeRequest).toHaveBeenLastCalledWith('two', { rule: 'absence', duration_seconds: 60 })
    const requestCount = routeRequest.mock.calls.length
    await wrapper.setProps({ revision: { ...changedDuration } })
    await flushPromises()
    expect(wrapper.get('section[aria-label="模型组合"] .panel-title').text()).toContain('二号录像')
    expect(routeRequest).toHaveBeenCalledTimes(requestCount)
  } finally { wrapper.unmount() }
})

it('falls back to the first video when the selected source is removed from the revision', async () => {
  const { wrapper, revision, observationRequest, routeRequest, profileRequest } = mountMultiSourcePanel()
  try {
    await openSecondRoute(wrapper)
    const firstChannel = revision.config.channels![0]
    await wrapper.setProps({ revision: { ...revision, revision_no: 2,
      config: { ...revision.config, channels: [firstChannel] } } })
    await flushPromises()
    expect(routeRequest).toHaveBeenLastCalledWith('one', { rule: 'absence', duration_seconds: 30 })
    expect(profileRequest).toHaveBeenLastCalledWith('one')
    expect(observationRequest).toHaveBeenLastCalledWith('task', { source_id: 'one' }, undefined)
    expect(wrapper.get('section[aria-label="模型组合"] .panel-title').text()).toContain('一号录像')
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

it('paginates observation records ten per page with cursor and resets on filter change', async () => {
  const request = vi.spyOn(agentApi, 'observations').mockImplementation(
    async (_id, filters, cursor) => cursor === 'c2'
      ? { items: [blocked], next_cursor: null, summary: {} }
      : { items: [empty], next_cursor: filters?.verdict ? null : 'c2', summary: {} })
  const wrapper = mount(ObservationPanel, {
    props: { agentId: 'task', sources, runs: sources.map(source => ({ source_id: source.id })) },
  })
  try {
    await flushPromises()
    expect(request).toHaveBeenLastCalledWith('task', {}, undefined, 10)
    expect(wrapper.text()).toContain('第 1 页')
    const prev = () => wrapper.findAll('button').find(b => b.text() === '上一页')!
    const next = () => wrapper.findAll('button').find(b => b.text() === '下一页')!
    expect(prev().attributes('disabled')).toBeDefined()
    await next().trigger('click')
    await flushPromises()
    expect(request).toHaveBeenLastCalledWith('task', {}, 'c2', 10)
    expect(wrapper.text()).toContain('第 2 页')
    expect(next().attributes('disabled')).toBeDefined()
    await prev().trigger('click')
    await flushPromises()
    expect(request).toHaveBeenLastCalledWith('task', {}, undefined, 10)
    expect(wrapper.text()).toContain('第 1 页')
    await next().trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('第 2 页')
    wrapper.findAllComponents(NSelect)[1].vm.$emit('update:value', 'insufficient')
    await flushPromises()
    expect(request).toHaveBeenLastCalledWith('task', { verdict: 'insufficient' }, undefined, 10)
    expect(wrapper.text()).toContain('第 1 页')
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
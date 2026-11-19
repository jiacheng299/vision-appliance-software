import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NTag } from 'naive-ui'
import { agentApi, type Observation } from '../src/modules/agents/api'
import { profileApi } from '../src/modules/sources/profileApi'
import TaskSummaryStrip from '../src/modules/agents/TaskSummaryStrip.vue'
import { activeGroupLabel } from '../src/app/navigation'

const sources = [{ id: 'one', name: '一号录像' }]
const routeState = {
  agent_id: 'task', channel_id: 'channel', source_id: 'one', rule: 'absence',
  active_members: ['yolo11n-person'], active_version: 'route-v2', active_since: 1,
  mode: 'candidate' as const, candidate_members: ['yolo11s-person'], candidate_score: 1.7,
  valid_windows: 1, hard_failure: false, delta_j: 0.09, drift: [], affected: [], fixed: [],
  escalated: false, chosen: null, notices: [], updated_at: '2026-11-17T00:00:00Z',
}
const profile = {
  source_id: 'one', view_version: 'v1', version: 7, intrinsic: {}, runtime: {},
  attributes: [], evaluated_at: 1, updated_at: '2026-11-17T00:00:00Z',
}
const observation: Observation = {
  id: 'observation', agent_id: 'task', run_id: 'run', source_id: 'one', task_key: 'person/absence',
  roi: [], window_start: 0, window_end: 30, route_version: 'route-v2', profile_version: 7,
  model_version: '1', path_id: 'channel', verdict: 'detected', detection_count: 1,
  metrics: { frame_count: 30, actual_fps: null, overexposure_ratio: null }, thresholds: {},
  gates: [], reasons: [], created_at: '2026-11-17T00:00:00Z',
}
afterEach(() => vi.restoreAllMocks())

function mountStrip(props: Partial<{ real: boolean; sourceId: string | null; channelId: string | null }> = {}) {
  return mount(TaskSummaryStrip, {
    props: { agentId: 'task', sourceId: 'one', channelId: 'channel',
      real: props.real ?? true, ...props },
  })
}

it('summarises the current video with its profile version, verdict counts and active route', async () => {
  const observations = vi.spyOn(agentApi, 'observations').mockResolvedValue({
    items: [observation, { ...observation, id: 'not-detected', verdict: 'not_detected' },
      { ...observation, id: 'insufficient', verdict: 'insufficient' }],
    next_cursor: null, summary: { detected: 8, not_detected: 4, insufficient: 9 } })
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([routeState])
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const wrapper = mountStrip()
  try {
    await flushPromises()
    const strip = wrapper.get('[aria-label="任务可观察性摘要"]')
    expect(observations).toHaveBeenCalledWith('task', { source_id: 'one' }, undefined)
    expect(strip.text()).toContain('当前视频')
    expect(strip.text()).toContain('v7')
    expect(strip.text()).toContain('检测到 1')
    expect(strip.text()).toContain('未检出 1')
    expect(strip.text()).toContain('观察不足 1')
    expect(strip.text()).toContain('route-v2')
    expect(strip.text()).toContain('候选验证中')
    expect(strip.text()).toContain('yolo11n-person')
    expect(strip.text()).toContain('观察不足')
    expect(strip.text()).toContain('不等于事件未发生')
  } finally { wrapper.unmount() }
})

it('uses task totals only when no current video is selected', async () => {
  const observations = vi.spyOn(agentApi, 'observations').mockResolvedValue({
    items: [], next_cursor: null, summary: { detected: 2, not_detected: 1, insufficient: 0 } })
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([])
  const wrapper = mountStrip({ sourceId: null, channelId: null })
  try {
    await flushPromises()
    expect(observations).toHaveBeenCalledWith('task', {}, undefined)
    expect(wrapper.get('[aria-label="任务可观察性摘要"]').text()).toContain('任务累计')
  } finally { wrapper.unmount() }
})

it('announces request failures instead of disguising them as zero or missing records', async () => {
  vi.spyOn(agentApi, 'observations').mockRejectedValue(new Error('offline'))
  vi.spyOn(agentApi, 'routeStates').mockRejectedValue(new Error('offline'))
  vi.spyOn(profileApi, 'read').mockRejectedValue(new Error('offline'))
  const wrapper = mountStrip()
  try {
    await flushPromises()
    const strip = wrapper.get('[aria-label="任务可观察性摘要"]')
    expect(strip.text()).toContain('加载失败')
    expect(strip.text()).toContain('无法连接本机服务')
    expect(strip.text()).not.toContain('未知')
    expect(strip.text()).not.toContain('尚未建立')
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(3)
    expect(wrapper.findAllComponents(NTag)).toHaveLength(0)
  } finally { wrapper.unmount() }
})

it('distinguishes no observation records from a route that has not been established', async () => {
  vi.spyOn(agentApi, 'observations').mockResolvedValue({
    items: [], next_cursor: null, summary: { detected: 0, not_detected: 0, insufficient: 0 } })
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([])
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const wrapper = mountStrip()
  try {
    await flushPromises()
    const strip = wrapper.get('[aria-label="任务可观察性摘要"]')
    expect(strip.text()).toContain('无记录')
    expect(strip.text()).toContain('尚未建立')
    expect(strip.text()).not.toContain('加载失败')
  } finally { wrapper.unmount() }
})

it('does not fetch anything for a mock workspace', async () => {
  const observations = vi.spyOn(agentApi, 'observations')
  const routes = vi.spyOn(agentApi, 'routeStates')
  const profileRead = vi.spyOn(profileApi, 'read')
  const wrapper = mountStrip({ real: false })
  try {
    await flushPromises()
    expect(observations).not.toHaveBeenCalled()
    expect(routes).not.toHaveBeenCalled()
    expect(profileRead).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-label="任务可观察性摘要"]').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

it('matches the sidebar group by the longest path prefix', () => {
  expect(activeGroupLabel('/dashboard')).toBe('运行与观察')
  expect(activeGroupLabel('/dashboard/events')).toBe('结果')
  expect(activeGroupLabel('/sources/abc')).toBe('采集')
  expect(activeGroupLabel('/create')).toBe('采集')
  expect(activeGroupLabel('/agents/task/live')).toBe('运行与观察')
  expect(activeGroupLabel('/settings/security')).toBe('管理与诊断')
  expect(activeGroupLabel('/unknown')).toBeNull()
})

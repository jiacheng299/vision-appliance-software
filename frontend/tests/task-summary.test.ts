import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NTag } from 'naive-ui'
import { agentApi } from '../src/modules/agents/api'
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
afterEach(() => vi.restoreAllMocks())

function mountStrip(props: Partial<{ real: boolean; sourceId: string | null; channelId: string | null }> = {}) {
  return mount(TaskSummaryStrip, {
    props: { agentId: 'task', sourceId: 'one', channelId: 'channel',
      real: props.real ?? true, ...props },
  })
}

it('summarises the profile version, the three verdict counts and the active route', async () => {
  vi.spyOn(agentApi, 'observations').mockResolvedValue({
    items: [], next_cursor: null, summary: { detected: 8, not_detected: 4, insufficient: 9 } })
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([routeState])
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const wrapper = mountStrip()
  try {
    await flushPromises()
    const strip = wrapper.get('[aria-label="任务可观察性摘要"]')
    expect(strip.text()).toContain('v7')
    expect(strip.text()).toContain('检测到 8')
    expect(strip.text()).toContain('未检出 4')
    expect(strip.text()).toContain('观察不足 9')
    expect(strip.text()).toContain('route-v2')
    expect(strip.text()).toContain('候选验证中')
    expect(strip.text()).toContain('yolo11n-person')
    expect(strip.text()).toContain('观察不足')
    expect(strip.text()).toContain('不等于事件未发生')
  } finally { wrapper.unmount() }
})

it('says 未知 or 尚未建立 instead of inventing numbers', async () => {
  vi.spyOn(agentApi, 'observations').mockRejectedValue(new Error('offline'))
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([])
  vi.spyOn(profileApi, 'read').mockRejectedValue(new Error('offline'))
  const wrapper = mountStrip()
  try {
    await flushPromises()
    const strip = wrapper.get('[aria-label="任务可观察性摘要"]')
    expect(strip.text()).toContain('未知')
    expect(strip.text()).toContain('尚未建立')
    expect(wrapper.findAllComponents(NTag)).toHaveLength(0)
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

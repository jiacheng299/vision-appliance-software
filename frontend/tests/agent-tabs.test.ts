import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { agentApi, type Revision, type Workspace } from '../src/modules/agents/api'
import { profileApi } from '../src/modules/sources/profileApi'
import type { Source } from '../src/shared/api/types'
import MonitorPanel from '../src/modules/agents/MonitorPanel.vue'
import EventsPanel from '../src/modules/agents/EventsPanel.vue'

const observedAt = '2026-11-17T00:00:00Z'
const workspace: Workspace = { agent_id: 'task', runs: [], data_origin: 'real',
  runtime_available: true, runtime_error: '', observed_at: observedAt }

const revision = {
  id: 'revision', agent_id: 'task', revision_no: 1, base_revision_id: null, state: 'published',
  row_version: 1, created_at: observedAt, updated_at: observedAt,
  config: { schema_version: '1.0', channels: [{ channel_id: 'channel', name: '岗位',
    target: 'person', rule: 'absence', duration_seconds: 30,
    sources: [{ source_id: 'one', regions: [{ id: 'roi', points: [[0, 0], [1, 0], [1, 1], [0, 1]] }] }],
    parameters: [] }] },
} as unknown as Revision

const sources = [{ id: 'one', name: '一号录像' }] as unknown as Source[]

function mountPanel(props: Partial<{ workspace: Workspace }> = {}) {
  vi.spyOn(agentApi, 'observations').mockResolvedValue({ items: [], next_cursor: null,
    summary: { detected: 0, not_detected: 0, insufficient: 0 } })
  vi.spyOn(agentApi, 'routes').mockResolvedValue({ source_id: 'one', rule: 'absence',
    profile_version: 0, scenario: { bucket: 'default', reasons: [] },
    graph: { requirements: [], edges: [] }, capabilities: [], chosen: null, ranked: [],
    blocked: [], weights: {}, budgets: {}, min_quality: 0.6, notices: [] })
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([])
  vi.spyOn(agentApi, 'routeDecisions').mockResolvedValue([])
  vi.spyOn(agentApi, 'routeTimeline').mockResolvedValue([])
  vi.spyOn(profileApi, 'read').mockResolvedValue({ source_id: 'one', view_version: '1', version: 1,
    intrinsic: {}, runtime: {}, attributes: [], evaluated_at: 0, updated_at: observedAt })
  vi.spyOn(agentApi, 'trackerPolicies').mockResolvedValue({ items: [], active: 'heuristic-iou',
    resolved: { spec: 'heuristic-iou', available: true, name: 'heuristic-iou',
      label: '固定机位 IoU/中心距关联', kind: 'heuristic', external: false, detail: {} },
    notice: '' })
  return mount(MonitorPanel, {
    props: { agentId: 'task', sources, canWrite: false, revision,
      workspace: props.workspace ?? workspace },
    global: { stubs: { EventsPanel: true, MediaPlayer: true, VideoWall: true } },
  })
}

afterEach(() => vi.restoreAllMocks())

it('orders the task view in business language without internal identifiers', async () => {
  const wrapper = mountPanel()
  try {
    await flushPromises()
    const tablist = wrapper.get('[role="tablist"]')
    const labels = tablist.findAll('button').map(button => button.text())
    expect(labels).toEqual(['画面', '观察记录', '模型组合', '事件'])
    expect(tablist.text()).not.toMatch(/\b[SMF]\d+\b|ΔJ/)
    expect(wrapper.text()).not.toMatch(/画像版本|当前路由/)
    expect(wrapper.text()).toContain('场景记录')
    expect(wrapper.text()).toContain('当前组合')
    expect(wrapper.get('button[aria-label="画面"]').attributes('aria-selected')).toBe('true')
  } finally { wrapper.unmount() }
})

it('defaults observation, model combination and summary to the first video', async () => {
  const wrapper = mountPanel()
  try {
    await flushPromises()
    await wrapper.get('button[aria-label="模型组合"]').trigger('click')
    await flushPromises()
    expect(agentApi.routes).toHaveBeenLastCalledWith('one', { rule: 'absence', duration_seconds: 30 })
    expect(agentApi.routeTimeline).toHaveBeenLastCalledWith('task', {
      channel_id: 'channel', source_id: 'one', limit: 12 })
    expect(profileApi.read).toHaveBeenLastCalledWith('one')
    expect(agentApi.observations).toHaveBeenCalledWith('task', { source_id: 'one' }, undefined)
  } finally { wrapper.unmount() }
})

it('the 事件 tab shows the full event list while 画面 keeps the compact one', async () => {
  const wrapper = mountPanel()
  try {
    await flushPromises()
    const compact = wrapper.findAllComponents(EventsPanel).map(item => item.props('compact'))
    expect(compact.every(value => value === true)).toBe(true)
    await wrapper.get('button[aria-label="事件"]').trigger('click')
    await flushPromises()
    const after = wrapper.findAllComponents(EventsPanel).map(item => item.props('compact'))
    expect(after).toEqual([false])
  } finally { wrapper.unmount() }
})

it('switching tabs unmounts the panels of the previous tab', async () => {
  const wrapper = mountPanel()
  try {
    await flushPromises()
    await wrapper.get('button[aria-label="模型组合"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[aria-label="模型组合"]').exists()).toBe(true)
    await wrapper.get('button[aria-label="观察记录"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[aria-label="观察记录"]').exists()).toBe(true)
  } finally { wrapper.unmount() }
})

it('a mock workspace shows only the two neutral tabs', async () => {
  const wrapper = mountPanel({ workspace: { ...workspace, data_origin: 'mock' } })
  try {
    await flushPromises()
    const labels = wrapper.get('[role="tablist"]').findAll('button').map(button => button.text())
    expect(labels).toEqual(['画面', '事件'])
  } finally { wrapper.unmount() }
})

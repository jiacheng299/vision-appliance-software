import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import RouteTimeline from '../src/modules/agents/RouteTimeline.vue'
import type { RouteDecision } from '../src/modules/agents/api'

function decision(overrides: Partial<RouteDecision> & { id: string }): RouteDecision {
  const base: RouteDecision = {
    id: overrides.id, kind: 'refresh', action: 'hold',
    reason: '评分增益未达到进入阈值（ΔJ=0.000）',
    delta_j: 0, route_version: 'route-v1', source_id: 'one', channel_id: 'channel',
    created_at: '2026-11-17T00:00:00Z', payload: {},
  }
  return { ...base, ...overrides }
}

const baseline = decision({ id: 'd1', kind: 'baseline', created_at: '2026-11-17T00:00:00Z' })
const blocked = decision({
  id: 'd2', kind: 'blocked', action: 'hold', delta_j: null, created_at: '2026-11-17T00:01:00Z',
  reason: '没有可行组合：当前组合失效时保持原状，观察记录输出观察不足',
  payload: { drift: [{ attribute: 'lighting', kind: 'confirmed', previous: 'daylight',
    current: 'strong_glare', reason: '新帧或设备证据确认属性发生变化' }],
    affected: ['person_detect'], candidate: null },
})
const switched = decision({
  id: 'd3', kind: 'window', action: 'switch', delta_j: 0.12, route_version: 'route-v2',
  created_at: '2026-11-17T00:02:00Z', reason: '候选已取得 2 个有效观察窗口，满足切换要求',
  payload: { affected: ['person_detect'], candidate: ['yolo11s-person'] },
})

it('reads from old to new and marks the entry that changed the route version', () => {
  const wrapper = mount(RouteTimeline, { props: { decisions: [switched, blocked, baseline] } })
  try {
    const items = wrapper.findAll('.route-timeline > li')
    expect(items).toHaveLength(3)
    expect(items[0].text()).toContain('建立基线')
    expect(items[0].classes()).not.toContain('changed')
    expect(items[1].text()).toContain('无可行组合')
    expect(items[1].classes()).not.toContain('changed')
    expect(items[2].text()).toContain('route-v2')
    expect(items[2].text()).toContain('切换版本')
    expect(items[2].classes()).toContain('changed')
  } finally { wrapper.unmount() }
})

it('shows the drift that triggered a decision and the affected subgraph', () => {
  const wrapper = mount(RouteTimeline, { props: { decisions: [blocked] } })
  try {
    const rows = wrapper.get('[aria-label="本次决策的属性变化"]')
    expect(rows.text()).toContain('lighting：daylight → strong_glare')
    expect(wrapper.text()).toContain('受影响子图：person_detect')
    expect(wrapper.text()).toContain('没有可行组合')
  } finally { wrapper.unmount() }
})

it('shows the candidate and the gain only when they exist', () => {
  const wrapper = mount(RouteTimeline, { props: { decisions: [switched, blocked] } })
  try {
    expect(wrapper.text()).toContain('候选：yolo11s-person')
    expect(wrapper.text()).toContain('ΔJ 0.120')
    const blockedItem = wrapper.findAll('.route-timeline > li')[0]
    expect(blockedItem.text()).not.toContain('ΔJ')
  } finally { wrapper.unmount() }
})

it('states plainly when there is nothing to plot', () => {
  const wrapper = mount(RouteTimeline, { props: { decisions: [] } })
  try {
    expect(wrapper.text()).toContain('还没有路由决策记录')
    expect(wrapper.find('.route-timeline').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

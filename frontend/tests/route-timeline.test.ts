import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import RouteTimeline from '../src/modules/agents/RouteTimeline.vue'
import type { TimelineEntry } from '../src/modules/agents/api'

function entry(overrides: Partial<TimelineEntry> & { id: string }): TimelineEntry {
  const base: TimelineEntry = {
    id: overrides.id, at: '2026-11-17T00:00:00Z', origin: 'route', kind: 'refresh',
    version: 'route-v1', summary: '评分增益未达到进入阈值（当前评分增益 0.000）',
  }
  return { ...base, ...overrides }
}

const profileDaylight = entry({ id: 'p1', origin: 'profile', kind: 'attribute_write',
  version: 'v1', summary: '写入动态属性 lighting', attribute: 'lighting',
  previous: null, current: 'daylight', at: '2026-11-17T00:00:00Z' })
const baseline = entry({ id: 'r1', kind: 'baseline', action: 'hold', delta_j: 0,
  at: '2026-11-17T00:01:00Z' })
const profileGlare = entry({ id: 'p2', origin: 'profile', kind: 'attribute_write',
  version: 'v2', summary: '写入动态属性 lighting', attribute: 'lighting',
  previous: 'daylight', current: 'strong_glare', at: '2026-11-17T00:02:00Z' })
const switched = entry({ id: 'r2', kind: 'window', action: 'switch', delta_j: 0.12,
  version: 'route-v2', summary: '候选已取得 2 个有效观察窗口，满足切换要求',
  at: '2026-11-17T00:03:00Z' })

it('plots observation conditions and model combinations from old to new in business language', () => {
  const wrapper = mount(RouteTimeline, {
    props: { entries: [switched, profileGlare, baseline, profileDaylight] },
  })
  try {
    const items = wrapper.findAll('.route-timeline > li')
    expect(items).toHaveLength(4)
    expect(items[0].text()).toContain('观察条件')
    expect(items[0].text()).toContain('更新观察条件')
    expect(items[1].text()).toContain('建立初始记录')
    expect(items[2].text()).toContain('strong_glare'.slice(0, 4))
    expect(items[3].text()).toContain('切换模型组合')
    expect(wrapper.text()).not.toMatch(/\b[SMF]\d+\b|ΔJ/)
  } finally { wrapper.unmount() }
})

it('marks a node only when the version of the same origin actually changed', () => {
  const wrapper = mount(RouteTimeline, {
    props: { entries: [switched, profileGlare, baseline, profileDaylight] },
  })
  try {
    const classes = wrapper.findAll('.route-timeline > li').map(item => item.classes())
    expect(classes[0]).not.toContain('changed')
    expect(classes[1]).not.toContain('changed')
    expect(classes[2]).toContain('changed')
    expect(classes[3]).toContain('changed')
  } finally { wrapper.unmount() }
})

it('shows the observation change and score gain only when present', () => {
  const wrapper = mount(RouteTimeline, { props: { entries: [switched, profileGlare] } })
  try {
    const drift = wrapper.get('[aria-label="观察条件变化"]')
    expect(drift.text()).toContain('lighting：daylight → strong_glare')
    expect(wrapper.text()).toContain('评分增益 0.120')
    expect(wrapper.text()).not.toContain('ΔJ')
    const profileItem = wrapper.findAll('.route-timeline > li')[0]
    expect(profileItem.text()).not.toContain('评分增益')
  } finally { wrapper.unmount() }
})

it('translates stored formula summaries without changing the timeline API', () => {
  const legacy = entry({ id: 'legacy', summary: '评分增益未达到进入阈值（ΔJ=0.000）' })
  const wrapper = mount(RouteTimeline, { props: { entries: [legacy] } })
  try {
    expect(wrapper.text()).toContain('评分增益未达到进入阈值（当前评分增益 0.000）')
    expect(wrapper.text()).not.toContain('ΔJ')
  } finally { wrapper.unmount() }
})

it('states plainly when there is nothing to plot', () => {
  const wrapper = mount(RouteTimeline, { props: { entries: [] } })
  try {
    expect(wrapper.text()).toContain('还没有观察条件或模型组合记录')
    expect(wrapper.find('.route-timeline').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

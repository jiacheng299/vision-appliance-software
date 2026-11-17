import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import RouteTimeline from '../src/modules/agents/RouteTimeline.vue'
import type { TimelineEntry } from '../src/modules/agents/api'

function entry(overrides: Partial<TimelineEntry> & { id: string }): TimelineEntry {
  const base: TimelineEntry = {
    id: overrides.id, at: '2026-11-17T00:00:00Z', origin: 'route', kind: 'refresh',
    version: 'route-v1', summary: '评分增益未达到进入阈值（ΔJ=0.000）',
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

it('plots profile and routing versions on one axis, from old to new', () => {
  const wrapper = mount(RouteTimeline, {
    props: { entries: [switched, profileGlare, baseline, profileDaylight] },
  })
  try {
    const items = wrapper.findAll('.route-timeline > li')
    expect(items).toHaveLength(4)
    expect(items[0].text()).toContain('画像')
    expect(items[0].text()).toContain('写入属性')
    expect(items[1].text()).toContain('建立基线')
    expect(items[2].text()).toContain('strong_glare'.slice(0, 4))
    expect(items[3].text()).toContain('切换版本')
  } finally { wrapper.unmount() }
})

it('marks a node only when the version of the same origin actually changed', () => {
  const wrapper = mount(RouteTimeline, {
    props: { entries: [switched, profileGlare, baseline, profileDaylight] },
  })
  try {
    const classes = wrapper.findAll('.route-timeline > li').map(item => item.classes())
    expect(classes[0]).not.toContain('changed')     // 画像第一条：无前序
    expect(classes[1]).not.toContain('changed')     // 路由第一条：无前序
    expect(classes[2]).toContain('changed')         // 画像 v1 → v2
    expect(classes[3]).toContain('changed')         // 路由 v1 → v2
  } finally { wrapper.unmount() }
})

it('shows the attribute change of a profile event and ΔJ only when present', () => {
  const wrapper = mount(RouteTimeline, { props: { entries: [switched, profileGlare] } })
  try {
    const drift = wrapper.get('[aria-label="属性变化"]')
    expect(drift.text()).toContain('lighting：daylight → strong_glare')
    expect(wrapper.text()).toContain('ΔJ 0.120')
    const profileItem = wrapper.findAll('.route-timeline > li')[0]
    expect(profileItem.text()).not.toContain('ΔJ')
  } finally { wrapper.unmount() }
})

it('states plainly when there is nothing to plot', () => {
  const wrapper = mount(RouteTimeline, { props: { entries: [] } })
  try {
    expect(wrapper.text()).toContain('还没有画像或路由记录')
    expect(wrapper.find('.route-timeline').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

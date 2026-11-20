import { flushPromises, mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import PatentPointsPanel from '../src/modules/agents/PatentPointsPanel.vue'
import type { RouteState, RouteView } from '../src/modules/agents/api'

const evaluation = (overrides: Partial<RouteView> = {}): RouteView => ({
  source_id: 'one', rule: 'absence', profile_version: 1,
  scenario: { bucket: 'default', reasons: [] },
  graph: { requirements: [], edges: [] },
  capabilities: [], chosen: null, ranked: [], blocked: [],
  weights: {}, budgets: {}, min_quality: 0.6, notices: [], ...overrides,
} as RouteView)

const chosen = { combination_id: 'c1', label: '人员检测 + 跟踪 + 区域规则', score: 0.812,
  coverage: .9, dependency: .8, conflict: 1, cost: .5, switch: .4, members: ['a', 'b'],
  feasible: true, reasons: [], bucket: 'default' }

const state = (overrides: Partial<RouteState> = {}): RouteState => ({
  agent_id: 'task', channel_id: 'channel', source_id: 'one', rule: 'absence',
  active_members: ['a'], active_version: 'local-r1', active_since: 1, mode: 'stable',
  candidate_members: null, candidate_score: null, valid_windows: 0, hard_failure: false,
  delta_j: null, drift: [], affected: [], fixed: [], escalated: false, chosen: null,
  notices: [], updated_at: '', ...overrides,
} as RouteState)

it('renders the requirement chain, valid evidence, chosen combination and stable mode', () => {
  const wrapper = mount(PatentPointsPanel, { props: {
    rule: 'absence',
    evaluation: evaluation({ chosen,
      evidence: { observation_id: 'o1', verdict: 'not_detected', usable: true,
        confidence: 'confirmed', window_start: 12, window_end: 42 },
      blocked: [{ combination_id: 'c2', label: '备用组合', reasons: ['能力未安装'],
        members: [], feasible: false, coverage: 0, dependency: 0, conflict: 0, cost: 0,
        switch: 0, bucket: 'default' }] }),
    state: state() } })
  try {
    const text = wrapper.get('[aria-label="专利技术要点"]').text()
    expect(text).toContain('人员数量检测 1.0')
    expect(text).toContain('有效观察窗口 12.0–42.0 秒，观察条件全部满足。')
    expect(text).toContain('首选 人员检测 + 跟踪 + 区域规则，综合评分 0.812')
    expect(text).toContain('1 组候选被硬约束排除')
    expect(text).toContain('稳定 · 当前组合持续工作')
    expect(text).not.toMatch(/ΔJ|\b[SMF]\d+\b/)
  } finally { wrapper.unmount() }
})

it('shows the three-node chain for intrusion rules', () => {
  const wrapper = mount(PatentPointsPanel, { props: {
    rule: 'intrusion', evaluation: evaluation({ rule: 'intrusion' }), state: null } })
  try {
    const text = wrapper.get('[aria-label="专利技术要点"]').text()
    expect(text).toContain('人员检测 0.5 → 跨帧跟踪 0.3 → 区域相交确认 0.2')
    expect(text).toContain('尚无观察记录，场景条件按未测定处理。')
    expect(text).toContain('绑定任务后可见。')
  } finally { wrapper.unmount() }
})

it('marks unverified evidence as a hint only and shows candidate hysteresis progress', () => {
  const wrapper = mount(PatentPointsPanel, { props: {
    rule: 'intrusion',
    evaluation: evaluation({ rule: 'intrusion',
      evidence: { observation_id: 'o2', verdict: 'insufficient', usable: false,
        confidence: 'unverified', window_start: 60, window_end: 90 } }),
    state: state({ mode: 'candidate', delta_j: 0.12, valid_windows: 3,
      candidate_members: ['x'], candidate_score: .9 }) } })
  try {
    const row = wrapper.get('[aria-label="专利技术要点"]')
    expect(row.text()).toContain('观察不足窗口 60.0–90.0 秒，仅作提示，不参与场景求解。')
    expect(row.find('.patent-warn').exists()).toBe(true)
    expect(row.text()).toContain('候选验证中 · 评分增益 0.120 · 已积累有效窗口 3')
  } finally { wrapper.unmount() }
})

it('admits plainly when nothing is decidable yet', async () => {
  const wrapper = mount(PatentPointsPanel, { props: { rule: 'absence', evaluation: null, state: null } })
  try {
    await flushPromises()
    const text = wrapper.get('[aria-label="专利技术要点"]').text()
    expect(text).toContain('没有可行组合')
    expect(text).toContain('尚无观察记录，场景条件按未测定处理。')
    expect(text).toContain('绑定任务后可见。')
  } finally { wrapper.unmount() }
})

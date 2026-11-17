import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { agentApi, type Revision, type RouteEvaluation, type RouteState, type RouteView, type Workspace } from '../src/modules/agents/api'
import type { Source } from '../src/shared/api/types'
import RoutePanel from '../src/modules/agents/RoutePanel.vue'
import MonitorPanel from '../src/modules/agents/MonitorPanel.vue'

const chosen: RouteEvaluation = {
  combination_id: 'combo:yolo11n-person', label: 'YOLO11n COCO 人员检测（CPU ONNX）',
  members: ['yolo11n-person'], score: 1.6225, coverage: 0.72, dependency: 1, conflict: 0,
  cost: 0.325, switch: 0, feasible: true, reasons: [], bucket: 'default',
}
const blocked: RouteEvaluation = {
  ...chosen, combination_id: 'combo:center-crop+yolo11n-person',
  label: '中心区域裁剪放大（未安装） + YOLO11n COCO 人员检测（CPU ONNX）',
  members: ['center-crop', 'yolo11n-person'], score: null, feasible: false,
  reasons: ['未安装：中心区域裁剪放大（未安装）'],
}
const view: RouteView = {
  source_id: 'one', rule: 'absence', profile_version: 3,
  scenario: { bucket: 'default', saturated_ratio: null, target_px: 48, brightness: 0.5,
    blur: 120, reasons: [] },
  graph: { requirements: [{ key: 'person_detect', kind: 'detect', target: 'person', weight: 1,
    description: '监测区域内人员数量' }], edges: [] },
  capabilities: [], chosen, ranked: [chosen], blocked: [blocked],
  weights: { alpha: 1, beta: 0.2, gamma: 0.3, delta: 0.2 },
  budgets: { cpu_ms: 200, memory_mb: 1024, transition_cpu_ms: 200 },
  min_quality: 0.6,
  notices: ['以下能力的质量数字是保守示例值，未做分桶验证，不能当作准确率：YOLO11n'],
}
afterEach(() => vi.restoreAllMocks())

it('shows the chosen combination with its score breakdown and the blocked ones', async () => {
  const request = vi.spyOn(agentApi, 'routes').mockResolvedValue(view)
  const wrapper = mount(RoutePanel, { props: { sourceId: 'one', rule: 'absence' } })
  try {
    await flushPromises()
    expect(request).toHaveBeenCalledWith('one', { rule: 'absence', duration_seconds: undefined })
    expect(wrapper.text()).toContain('评估首选：YOLO11n COCO 人员检测')
    expect(wrapper.text()).toContain('综合评分 1.623')
    expect(wrapper.text()).toContain('常规场景')
    expect(wrapper.text()).toContain('未做分桶验证')
    expect(wrapper.text()).toContain('未安装：中心区域裁剪放大')
    expect(wrapper.get('[aria-label="路由候选"]').text()).toContain('路由候选')
  } finally { wrapper.unmount() }
})

it('states plainly when no combination survives the hard constraints', async () => {
  vi.spyOn(agentApi, 'routes').mockResolvedValue({ ...view, chosen: null, ranked: [],
    blocked: [blocked] })
  const wrapper = mount(RoutePanel, { props: { sourceId: 'one', rule: 'intrusion', durationSeconds: 8 } })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('没有可行组合')
    expect(wrapper.text()).toContain('所有候选都被硬约束排除')
    expect(wrapper.text()).toContain('暂无可行候选')
  } finally { wrapper.unmount() }
})

it('opens route evaluation from the task monitor only for a real bound channel', async () => {
  const request = vi.spyOn(agentApi, 'routes').mockResolvedValue(view)
  const workspace: Workspace = { agent_id: 'task', runs: [], data_origin: 'real', runtime_available: true,
    runtime_error: '', observed_at: '2026-11-17T00:00:00Z' }
  const revision = {
    id: 'revision', agent_id: 'task', revision_no: 1, base_revision_id: null, state: 'published',
    row_version: 1, created_at: '2026-11-17T00:00:00Z', updated_at: '2026-11-17T00:00:00Z',
    config: { schema_version: '1.0', channels: [{ channel_id: 'channel', name: '岗位', target: 'person',
      rule: 'absence', duration_seconds: 30,
      sources: [{ source_id: 'one', regions: [{ id: 'roi', points: [[0, 0], [1, 0], [1, 1], [0, 1]] }] }],
      parameters: [] }] },
  } as unknown as Revision
  const wrapper = mount(MonitorPanel, {
    props: { agentId: 'task', sources: [{ id: 'one', name: '一号录像' }] as unknown as Source[],
      canWrite: false, workspace, revision },
    global: { stubs: { EventsPanel: true, MediaPlayer: true, VideoWall: true } },
  })
  try {
    await flushPromises()
    expect(request).not.toHaveBeenCalled()
    await wrapper.get('button[aria-label="路由候选"]').trigger('click')
    await flushPromises()
    expect(request).toHaveBeenCalledWith('one', { rule: 'absence', duration_seconds: 30 })
    expect(wrapper.find('[aria-label="路由候选"]').exists()).toBe(true)
  } finally { wrapper.unmount() }
})

const routeState: RouteState = {
  agent_id: 'task', channel_id: 'channel', source_id: 'one', rule: 'absence',
  active_members: ['yolo11n-person'], active_version: 'route-v1', active_since: 1,
  mode: 'candidate', candidate_members: ['yolo11s-person'], candidate_score: 1.71,
  valid_windows: 1, hard_failure: false, delta_j: 0.09,
  drift: [{ attribute: 'lighting', kind: 'confirmed', previous: 'daylight',
    current: 'strong_glare', reason: '新帧或设备证据确认属性发生变化' }],
  affected: ['person_detect'], fixed: [], escalated: true,
  escalation_reason: '漂移覆盖全部需求', chosen: { ...chosen, combination_id: 'combo:yolo11s-person',
    members: ['yolo11s-person'], label: 'YOLO11s 人员检测' },
  notices: ['无法局部修复，已退化为全图重算：漂移覆盖全部需求'], updated_at: '2026-11-17T00:00:00Z',
}

it('shows the active route version, the pending candidate and the drift that caused it', async () => {
  vi.spyOn(agentApi, 'routes').mockResolvedValue(view)
  const states = vi.spyOn(agentApi, 'routeStates').mockResolvedValue([routeState])
  const wrapper = mount(RoutePanel, {
    props: { sourceId: 'one', rule: 'absence', agentId: 'task', channelId: 'channel' },
  })
  try {
    await flushPromises()
    expect(states).toHaveBeenCalledWith('task')
    expect(wrapper.get('[aria-label="路由状态"]').text()).toContain('当前路由 route-v1')
    expect(wrapper.text()).toContain('候选验证中')
    expect(wrapper.text()).toContain('候选：yolo11s-person')
    expect(wrapper.text()).toContain('有效窗口 1')
    expect(wrapper.text()).toContain('lighting：daylight → strong_glare')
    expect(wrapper.text()).toContain('已退化为全图重算')
  } finally { wrapper.unmount() }
})

it('can propose a candidate from the panel', async () => {
  vi.spyOn(agentApi, 'routes').mockResolvedValue(view)
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([])
  const propose = vi.spyOn(agentApi, 'proposeRoute').mockResolvedValue(routeState)
  const wrapper = mount(RoutePanel, {
    props: { sourceId: 'one', rule: 'absence', durationSeconds: 30, agentId: 'task', channelId: 'channel' },
  })
  try {
    await flushPromises()
    const buttons = wrapper.findAll('button')
    const proposeButton = buttons.find(button => button.text().includes('评估并提议'))
    expect(proposeButton).toBeTruthy()
    await proposeButton!.trigger('click')
    await flushPromises()
    expect(propose).toHaveBeenCalledWith('task', { channel_id: 'channel', source_id: 'one',
      rule: 'absence', duration_seconds: 30 })
  } finally { wrapper.unmount() }
})
it('plots the merged profile and routing timeline', async () => {
  vi.spyOn(agentApi, 'routes').mockResolvedValue(view)
  vi.spyOn(agentApi, 'routeStates').mockResolvedValue([routeState])
  vi.spyOn(agentApi, 'routeTimeline').mockResolvedValue([
    { id: 't2', at: '2026-11-17T00:02:00Z', origin: 'route', kind: 'window', version: 'route-v2',
      summary: '候选已取得 2 个有效观察窗口，满足切换要求', action: 'switch', delta_j: 0.12 },
    { id: 't1', at: '2026-11-17T00:00:00Z', origin: 'profile', kind: 'attribute_write',
      version: 'v2', summary: '写入动态属性 lighting', attribute: 'lighting',
      previous: 'daylight', current: 'strong_glare' },
  ])
  const wrapper = mount(RoutePanel, {
    props: { sourceId: 'one', rule: 'absence', agentId: 'task', channelId: 'channel' },
  })
  try {
    await flushPromises()
    const history = wrapper.get('[aria-label="路由版本时间线"]')
    expect(history.text()).toContain('lighting：daylight → strong_glare')
    expect(history.text()).toContain('切换版本')
    expect(history.text()).toContain('ΔJ 0.120')
  } finally { wrapper.unmount() }
})
it('shows the tracker policy registry so the missing MARL slot is visible', async () => {
  vi.spyOn(agentApi, 'routes').mockResolvedValue(view)
  vi.spyOn(agentApi, 'trackerPolicies').mockResolvedValue({
    active: 'heuristic-iou',
    notice: '关联策略可替换；多智能体强化学习策略尚未安装，本机仍使用固定机位 IoU/中心距关联。',
    items: [
      { name: 'heuristic-iou', label: '固定机位 IoU/中心距关联', kind: 'heuristic',
        installed: true, calibrated: true, requires: [], limitations: ['不做身份识别'] },
      { name: 'marl-association', label: '多智能体强化学习关联策略（预留）', kind: 'learned',
        installed: false, calibrated: false,
        requires: ['训练环境与策略权重（不在本仓库）'],
        limitations: ['本仓库没有训练循环与策略权重'] },
    ],
  })
  const wrapper = mount(RoutePanel, { props: { sourceId: 'one', rule: 'absence' } })
  try {
    await flushPromises()
    const panel = wrapper.get('[aria-label="关联策略"]')
    expect(panel.text()).toContain('尚未安装')
    expect(panel.text()).toContain('多智能体强化学习关联策略（预留）')
    expect(panel.text()).toContain('当前使用')
    expect(panel.text()).toContain('本仓库没有训练循环与策略权重')
  } finally { wrapper.unmount() }
})
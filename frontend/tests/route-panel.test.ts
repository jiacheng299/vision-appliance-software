import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { agentApi, type Revision, type RouteEvaluation, type RouteView, type Workspace } from '../src/modules/agents/api'
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
    expect(wrapper.text()).toContain('当前选择：YOLO11n COCO 人员检测')
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

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NSelect } from 'naive-ui'
import { agentApi, type Revision, type TrustCheck, type Workspace } from '../src/modules/agents/api'
import TrustChecksPanel from '../src/modules/agents/TrustChecksPanel.vue'
import EventDrawer from '../src/modules/agents/EventDrawer.vue'
import MonitorPanel from '../src/modules/agents/MonitorPanel.vue'

const sources = [{ id: 'one', name: '一号录像' }, { id: 'two', name: '二号录像' }]
const row: TrustCheck = {
  source_id: 'one', source_kind: 'file', run_id: 'run-one', channel_id: 'channel',
  observed_at: '2026-11-09T03:00:00Z', reason: 'sample_gap', start_seconds: 30, end_seconds: 59,
}
afterEach(() => vi.restoreAllMocks())

it('filters the task by source and opens the associated alarm', async () => {
  const second = { ...row, source_id: 'two', run_id: 'run-two', reason: 'evidence_unavailable' as const, event_id: 'alarm' }
  const request = vi.spyOn(agentApi, 'trustChecks').mockImplementation(async (_, source) => source ? [second] : [row, second])
  const wrapper = mount(TrustChecksPanel, {
    props: { agentId: 'task', sources, runs: sources.map(source => ({ source_id: source.id })) },
    global: { stubs: { EventDrawer: true } },
  })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('采样间断')
    expect(wrapper.text()).toContain('30.0–59.0 秒')
    wrapper.getComponent(NSelect).vm.$emit('update:value', 'two')
    await flushPromises()
    expect(request).toHaveBeenLastCalledWith('task', 'two')
    expect(wrapper.text()).not.toContain('采样间断')
    expect(wrapper.text()).toContain('证据未就绪')
    await wrapper.get('[aria-label="查看关联报警"]').trigger('click')
    expect(wrapper.getComponent(EventDrawer).props('eventId')).toBe('alarm')
  } finally { wrapper.unmount() }
})

it('reads real task diagnostics only while the trust check panel is open', async () => {
  const request = vi.spyOn(agentApi, 'trustChecks').mockResolvedValue([])
  const workspace: Workspace = { agent_id: 'task', runs: [], data_origin: 'real', runtime_available: true,
    runtime_error: '', observed_at: row.observed_at }
  const revision: Revision = { id: 'revision', agent_id: 'task', revision_no: 1, base_revision_id: null,
    state: 'published', row_version: 1, created_at: row.observed_at, updated_at: row.observed_at,
    config: { schema_version: '1.0', channels: [] } }
  const wrapper = mount(MonitorPanel, {
    props: { agentId: 'task', sources: [], canWrite: false, workspace, revision },
    global: { stubs: { EventsPanel: true, MediaPlayer: true, VideoWall: true } },
  })
  try {
    await flushPromises()
    expect(request).not.toHaveBeenCalled()
    const toggle = wrapper.get('button[aria-label="模型防护"]')
    await toggle.trigger('click')
    await flushPromises()
    expect(request).toHaveBeenCalledWith('task', undefined)
    expect(wrapper.text()).toContain('暂无模型防护记录')
    await toggle.trigger('click')
    expect(wrapper.find('[aria-label="模型防护记录"]').exists()).toBe(false)
    await wrapper.setProps({ workspace: { ...workspace, data_origin: 'mock' } })
    expect(wrapper.find('button[aria-label="模型防护"]').exists()).toBe(false)
  } finally { wrapper.unmount() }
})

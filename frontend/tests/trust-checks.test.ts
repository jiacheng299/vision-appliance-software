import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NSelect } from 'naive-ui'
import { agentApi, type TrustCheck } from '../src/modules/agents/api'
import TrustChecksPanel from '../src/modules/agents/TrustChecksPanel.vue'
import EventDrawer from '../src/modules/agents/EventDrawer.vue'

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

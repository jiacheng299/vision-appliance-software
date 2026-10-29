import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { agentApi, type MonitorEvent, type MonitorEventPage } from '../src/modules/agents/api'
import EventsPanel from '../src/modules/agents/EventsPanel.vue'
import EventDrawer from '../src/modules/agents/EventDrawer.vue'

class EventStream extends EventTarget {
  static instances: EventStream[] = []
  onerror: (() => void) | null = null
  closed = false
  constructor(public url: string) { super(); EventStream.instances.push(this) }
  close() { this.closed = true }
  send(payload: MonitorEvent[]) {
    this.dispatchEvent(new MessageEvent('events', { data: JSON.stringify({ items: payload, updated_at: '2026-10-29T00:00:00Z' }) }))
  }
}

function event(type: string): MonitorEvent {
  return {
    id: type, agent_id: 'agent-1', run_id: 'run-1', revision_id: 'revision-1', source_id: 'source-1', channel_id: 'channel-1',
    occurred_at: '2026-10-29T00:00:00Z', updated_at: '2026-10-29T00:00:00Z', row_version: 1, event_type: type,
    severity: 'warning', reason: 'test', evidence_status: 'ready', review_status: 'unreviewed', feedback_reason: '', data_origin: 'real',
  }
}

function page(items: MonitorEvent[] = []): MonitorEventPage {
  return { items, next_cursor: null, stream_cursor: 'cursor-1', updated_at: '2026-10-29T00:00:00Z', data_origin: 'real', resync_required: false, today_count: items.length }
}

vi.mock('naive-ui', async () => {
  const { defineComponent } = await import('vue')
  return {
    NButton: defineComponent({ template: '<button><slot/></button>' }),
    NInput: defineComponent({ props: ['value'], emits: ['update:value'], template: '<input :value="value" aria-label="筛选事件类型" @input="$emit(\'update:value\', $event.target.value)"/>' }),
    NSelect: defineComponent({ props: ['value', 'options'], template: '<select/>' }),
    NDrawer: defineComponent({ template: '<div><slot/></div>' }),
    NDrawerContent: defineComponent({ template: '<div><slot/></div>' }),
  }
})

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); EventStream.instances = [] })

describe('agent event labels and filters', () => {
  it('submits a Chinese event name as its machine value and filters SSE with that same value', async () => {
    vi.stubGlobal('EventSource', EventStream)
    const request = vi.spyOn(agentApi, 'events').mockResolvedValue(page())
    const wrapper = mount(EventsPanel, { props: { agentId: 'agent-1', runs: [], sources: [], canWrite: false } })
    await flushPromises()

    await wrapper.get('input[aria-label="筛选事件类型"]').setValue('人员缺岗')
    await wrapper.findAll('button').find(button => button.text() === '应用筛选')!.trigger('click')
    await flushPromises()

    expect(request.mock.calls.at(-1)?.[1]?.event_type).toBe('person_absence')
    const stream = EventStream.instances.at(-1)!
    stream.send([event('person_absence'), event('person_presence_restored')])
    await flushPromises()
    expect(wrapper.text()).toContain('人员缺岗')
    expect(wrapper.text()).not.toContain('恢复在岗')
    wrapper.unmount()
  })

  it('shows the mapped Chinese event name in the event drawer title', async () => {
    vi.spyOn(agentApi, 'event').mockResolvedValue({ ...event('person_absence'), evidence: [], feedback_history: [] } as any)
    const wrapper = mount(EventDrawer, {
      props: { agentId: 'agent-1', event: event('person_absence'), canWrite: false },
      global: { stubs: { RunPlayer: true, AgentStatus: true, ErrorBanner: true } },
    })
    await flushPromises()
    expect(wrapper.get('h2').text()).toBe('人员缺岗')
    wrapper.unmount()
  })
})

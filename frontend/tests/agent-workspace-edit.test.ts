import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentWorkspacePage from '../src/modules/agents/AgentWorkspacePage.vue'
import RevisionEditor from '../src/modules/agents/RevisionEditor.vue'
import * as agentModule from '../src/modules/agents/api'
import { agentApi, type AgentDetail, type Revision } from '../src/modules/agents/api'
import { task } from './fixtures/agentTemplates'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'task-1', tab: 'config' } }),
  useRouter: () => ({ push: vi.fn() }),
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}))

vi.mock('../src/modules/agents/useWorkspace', async () => {
  const { ref } = await import('vue')
  return {
    useWorkspace: () => ({
      data: ref({ runtime_available: true, runs: [] }),
      operations: ref([]),
      error: ref(''),
      operationError: ref(''),
      refresh: vi.fn(),
      track: vi.fn(),
    }),
  }
})

vi.mock('../src/modules/agents/api', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/modules/agents/api')>()
  return { ...actual, listAgentSources: vi.fn() }
})

vi.mock('naive-ui', () => {
  const Box = defineComponent({ template: '<div><slot/></div>' })
  return {
    NButton: defineComponent({ name: 'NButton', props: ['disabled', 'loading'], template: '<button :disabled="disabled || loading"><slot/></button>' }),
    NInput: Box,
    NModal: Box,
    NSelect: Box,
  }
})

function detail(state: Revision['state']): AgentDetail {
  const value = task()
  const revision: Revision = {
    ...value.latest_revision,
    state,
    published_at: state === 'published' ? value.latest_revision.updated_at : null,
  }
  return { ...value, latest_revision: revision, revisions: [revision] }
}

async function page(value: AgentDetail) {
  vi.spyOn(agentApi, 'detail').mockResolvedValue(value)
  vi.mocked(agentModule.listAgentSources).mockResolvedValue([])
  const wrapper = mount(AgentWorkspacePage, {
    global: {
      stubs: {
        AgentWorkspaceHeader: true,
        WorkflowPanel: true,
        MonitorPanel: true,
        HistoryPanel: true,
        ExportsPanel: true,
        ErrorBanner: true,
        AgentStatus: true,
        RevisionEditor: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

function configButton(wrapper: Awaited<ReturnType<typeof page>>) {
  const section = wrapper.findAll('section').find(node => node.text().includes('配置内容'))
  return section!.get('button')
}

afterEach(() => vi.restoreAllMocks())

describe('task configuration editing', () => {
  it('opens the newly cloned draft when modifying a published task', async () => {
    const value = detail('published')
    const draft: Revision = { ...value.latest_revision, id: 'task-revision-2', revision_no: 2, state: 'draft', published_at: null }
    const clone = vi.spyOn(agentApi, 'clone').mockResolvedValue(draft)
    const wrapper = await page(value)

    await configButton(wrapper).trigger('click')
    await flushPromises()

    expect(clone).toHaveBeenCalledOnce()
    expect(wrapper.findComponent(RevisionEditor).exists()).toBe(true)
    wrapper.unmount()
  })

  it('opens an existing draft directly without cloning it', async () => {
    const clone = vi.spyOn(agentApi, 'clone')
    const wrapper = await page(detail('draft'))

    await configButton(wrapper).trigger('click')
    await flushPromises()

    expect(clone).not.toHaveBeenCalled()
    expect(wrapper.findComponent(RevisionEditor).exists()).toBe(true)
    wrapper.unmount()
  })
})

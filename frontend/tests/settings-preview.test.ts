import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsPage from '../src/modules/settings/SettingsPage.vue'
import { api } from '../src/shared/api'

vi.mock('naive-ui', async importOriginal => ({
  ...await importOriginal<typeof import('naive-ui')>(), useMessage: () => ({ success: vi.fn() }),
}))
afterEach(() => vi.restoreAllMocks())

async function open(section: string) {
  const read = vi.spyOn(api, 'getSettings').mockResolvedValue({ section: 'diagnostics', values: {}, row_version: 1 })
  const write = vi.spyOn(api, 'saveSettings')
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/settings/:section', component: SettingsPage }] })
  await router.push('/settings/' + section)
  await router.isReady()
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, read, write }
}

describe('planned settings', () => {
  it('shows disabled planned capabilities instead of system name and timezone', async () => {
    const { wrapper, read, write } = await open('general')
    expect(wrapper.text()).not.toContain('系统名称')
    expect(wrapper.text()).not.toContain('系统时区')
    expect(wrapper.text()).toContain('智能场景适配')
    expect(wrapper.text()).toContain('多模态联合分析')
    expect(wrapper.text()).toContain('规划中')
    const plannedButtons = wrapper.findAll('button').filter(button => button.text().includes('暂未开放'))
    expect(plannedButtons).toHaveLength(4)
    expect(plannedButtons.every(button => button.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.text()).not.toContain('保存设置')
    expect(read.mock.calls.every(([section]) => section === 'diagnostics')).toBe(true)
    expect(write).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps security empty without reading or writing its configuration', async () => {
    const { wrapper, read, write } = await open('security')
    expect(wrapper.text()).toContain('暂未开放')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('保存设置')
    expect(read.mock.calls.every(([section]) => section === 'diagnostics')).toBe(true)
    expect(write).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

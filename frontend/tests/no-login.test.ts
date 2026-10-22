import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../src/app/App.vue'
import { router as applicationRouter } from '../src/app/router'
import { api } from '../src/shared/api'
import { environment } from '../src/shared/environment'

vi.mock('../src/shared/environment', async () => {
  const { ref } = await import('vue')
  return { environment: ref(null), loadEnvironment: vi.fn() }
})
afterEach(() => { environment.value = null })

describe('account-free workspace', () => {
  it('renders the workspace without a user store or account initialization', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', redirect: '/dashboard' },
      { path: '/dashboard', component: { template: '<h1>快速监控看板</h1>' } },
    ] })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('快速监控看板')
    expect(wrapper.find('[aria-label="退出登录"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('创建管理员')
    wrapper.unmount()
  })

  it('has no login route or account API methods', () => {
    expect(applicationRouter.getRoutes().some(route => route.path === '/login')).toBe(false)
    expect('authenticate' in api).toBe(false)
    expect('setupStatus' in api).toBe(false)
    expect('me' in api).toBe(false)
  })

  it('keeps the mock warning visible without an account', async () => {
    environment.value = { data_origin: 'mock', message: '演示' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/agents', component: { template: '<h1>智能体管理</h1>' } },
    ] })
    await router.push('/agents')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('所有运行、画面、报警和导出均为模拟')
    expect(wrapper.get('h1').text()).toBe('智能体管理')
    expect(wrapper.find('[aria-label="退出登录"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

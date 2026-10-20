import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import App from '../src/app/App.vue'
import { router as applicationRouter } from '../src/app/router'
import { api } from '../src/shared/api'

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
})

import { expect, it } from 'vitest'
import { navigation, navigationGroups, permittedRoutes } from '../src/app/navigation'

it('groups the navigation along the patent chain, in order', () => {
  const labels = navigationGroups.map(group => group.label)
  expect(labels).toEqual(['采集', '运行与观察', '结果', '管理与诊断'])
  expect(navigationGroups[0].items.map(item => item.label)).toEqual(['视频源管理', '任务创建'])
  expect(navigationGroups[1].items.map(item => item.label)).toEqual(['快速监控看板', '智能体管理'])
  expect(navigationGroups[2].items.map(item => item.label)).toEqual(['事件记录'])
  expect(navigationGroups[3].items.map(item => item.label)).toEqual(['运行状态', '模型管理', '系统设置'])
})

it('every group states which part of the flow it covers', () => {
  expect(navigationGroups[0].note).toContain('S1')
  expect(navigationGroups[1].note).toContain('S6')
  expect(navigationGroups[2].note).toContain('S8')
  for (const group of navigationGroups) expect(group.note.length).toBeGreaterThan(4)
})

it('keeps every previously reachable entry and adds the event page', () => {
  const paths = navigation.map(item => item.path)
  for (const path of ['/dashboard', '/runtime', '/sources', '/create', '/agents', '/models', '/settings'])
    expect(paths).toContain(path)
  expect(paths).toContain('/dashboard/events')
  expect(new Set(paths).size).toBe(paths.length)
  // 扁平列表只是分组结果的视图，不另存一份
  expect(navigation).toHaveLength(navigationGroups.flatMap(group => group.items).length)
})

it('still permits exactly the routes the sidebar links to', () => {
  for (const item of navigation) expect(permittedRoutes(item.path)).toBe(true)
  expect(permittedRoutes('/agents/123/config')).toBe(true)
  expect(permittedRoutes('/agents/123/unknown')).toBe(false)
  expect(permittedRoutes('/settings/security')).toBe(true)
})

it('gives every entry an icon and a hint so the sidebar can explain itself', () => {
  for (const item of navigation) {
    expect(item.icon.length).toBeGreaterThan(2)
    expect(item.hint && item.hint.length > 3).toBe(true)
  }
})

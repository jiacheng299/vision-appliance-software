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

it('explains the operating flow without patent-internal identifiers', () => {
  expect(navigationGroups[0].note).toBe('接入视频源并建立监测任务')
  expect(navigationGroups[1].note).toBe('查看实际画面、观察条件与模型组合')
  expect(navigationGroups[2].note).toBe('查看检测到、限定窗口未检出与观察不足')
  for (const group of navigationGroups) {
    expect(group.note.length).toBeGreaterThan(4)
    expect(`${group.label} ${group.note} ${group.items.map(item => `${item.label} ${item.hint}`).join(' ')}`)
      .not.toMatch(/\b[SMF]\d+\b|ΔJ/)
  }
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

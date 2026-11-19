// 导航按使用流程分组：采集 → 运行与观察 → 结果 → 管理与诊断。
// 路径保持不变，既有链接与书签继续可用。
export interface NavEntry { label: string; path: string; icon: string; hint?: string }
export interface NavGroup { label: string; note: string; items: NavEntry[] }

export const navigationGroups: NavGroup[] = [
  {
    label: '采集',
    note: '接入视频源并建立监测任务',
    items: [
      { label: '视频源管理', path: '/sources', icon: 'video', hint: '摄像头与录像、连接诊断' },
      { label: '任务创建', path: '/create', icon: 'file-plus', hint: '选择模板、划区、验证启动' },
    ],
  },
  {
    label: '运行与观察',
    note: '查看实际画面、观察条件与模型组合',
    items: [
      { label: '快速监控看板', path: '/dashboard', icon: 'house', hint: '画面墙与运行概况' },
      { label: '智能体管理', path: '/agents', icon: 'bot',
        hint: '任务详情：画面 / 观察记录 / 模型组合 / 事件' },
    ],
  },
  {
    label: '结果',
    note: '查看检测到、限定窗口未检出与观察不足',
    items: [
      { label: '事件记录', path: '/dashboard/events', icon: 'siren', hint: '报警与证据' },
    ],
  },
  {
    label: '管理与诊断',
    note: '能力、资源与运行环境',
    items: [
      { label: '运行状态', path: '/runtime', icon: 'activity', hint: '服务、模型与资源' },
      { label: '模型管理', path: '/models', icon: 'box', hint: '模型文件、校验与能力声明' },
      { label: '系统设置', path: '/settings', icon: 'settings', hint: '通用、存储、资源与安全' },
    ],
  },
]

/** 扁平列表：保持既有调用方与测试不用改。 */
export const navigation: NavEntry[] = navigationGroups.flatMap(group => group.items)

/**
 * Which group the current path belongs to. Longest prefix wins, so
 * `/dashboard/events` highlights 结果 rather than 运行与观察.
 */
export function activeGroupLabel(path: string): string | null {
  let best: string | null = null
  let bestLength = -1
  for (const group of navigationGroups) {
    for (const item of group.items) {
      const matches = path === item.path || path.startsWith(item.path + '/')
      if (matches && item.path.length > bestLength) {
        best = group.label
        bestLength = item.path.length
      }
    }
  }
  return best
}

export function permittedRoutes(path: string): boolean {
  return /^\/(dashboard(?:\/events)?|runtime|create|models(?:\/[^/]+)?|agents(?:\/[^/]+(?:\/(?:live|config|history|events|reports))?)?|sources(?:\/[^/]+)?|settings(?:\/(general|storage|resources|security|diagnostics))?)$/.test(path)
}

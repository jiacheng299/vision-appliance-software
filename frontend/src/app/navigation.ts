export const navigation = [
  {label:'快速监控看板',path:'/dashboard',icon:'house'}, {label:'运行状态',path:'/runtime',icon:'activity'},
  {label:'视频源管理',path:'/sources',icon:'video'}, {label:'任务创建',icon:'file-plus',disabled:true},
  {label:'智能体管理',path:'/agents',icon:'bot'}, {label:'模型管理',icon:'box',disabled:true},
  {label:'系统设置',path:'/settings',icon:'settings'},
]
export function permittedRoutes(path: string): boolean {
  return /^\/(dashboard(?:\/events)?|runtime|agents(?:\/[^/]+(?:\/(?:live|config|history|events|reports))?)?|sources(?:\/[^/]+)?|settings(?:\/(general|storage|resources|security|diagnostics))?)$/.test(path)
}

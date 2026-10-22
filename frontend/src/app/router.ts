import { createRouter, createWebHistory } from 'vue-router'
import { useSession } from '../shared/auth/store'
export const router=createRouter({history:createWebHistory(),routes:[
  {path:'/',redirect:'/dashboard'},
  {path:'/login',component:()=>import('../shared/auth/AuthPage.vue')},
  {path:'/dashboard',component:()=>import('../modules/dashboard/DashboardPage.vue')},
  {path:'/dashboard/events',component:()=>import('../modules/dashboard/EventsPage.vue')},
  {path:'/runtime',component:()=>import('../modules/runtime/RuntimePage.vue')},
  {path:'/agents',component:()=>import('../modules/agents/AgentsPage.vue')},
  {path:'/agents/:id/:tab(live|config|history|events|reports)?',component:()=>import('../modules/agents/AgentDetailPage.vue')},
  {path:'/sources/:id?',component:()=>import('../modules/sources/SourcesPage.vue')},
  {path:'/settings',redirect:'/settings/general'},
  {path:'/settings/:section(general|storage|resources|security|diagnostics)',component:()=>import('../modules/settings/SettingsPage.vue')},
  {path:'/:pathMatch(.*)*',redirect:'/dashboard'},
]})
router.beforeEach(async to=>{
  const session=useSession()
  if(!session.ready){try{await session.restore()}catch{return true}}
  if(!session.user&&to.path!='/login')return '/login'
  if(session.user&&to.path==='/login')return '/dashboard'
  return true
})

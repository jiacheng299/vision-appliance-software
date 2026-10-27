import { createRouter, createWebHistory } from 'vue-router'
export const router=createRouter({history:createWebHistory(),routes:[
  {path:'/',redirect:'/dashboard'},
  {path:'/dashboard',component:()=>import('../modules/dashboard/DashboardPage.vue')},
  {path:'/dashboard/events',component:()=>import('../modules/dashboard/EventsPage.vue')},
  {path:'/runtime',component:()=>import('../modules/runtime/RuntimePage.vue')},
  {path:'/create',component:()=>import('../modules/task-create/TemplateTaskCreatePage.vue')},
  {path:'/create/legacy',component:()=>import('../modules/task-create/TaskCreatePage.vue'),props:{legacyOnly:true}},
  {path:'/models/:id?',component:()=>import('../modules/model-management/ModelsPage.vue')},
  {path:'/agents',component:()=>import('../modules/agents/AgentTemplatesPage.vue')},
  {path:'/agents/legacy',component:()=>import('../modules/agents/AgentsPage.vue'),props:{legacyOnly:true}},
  {path:'/agent-templates/:id',component:()=>import('../modules/agents/TemplateWorkspacePage.vue')},
  {path:'/agents/:id/:tab(live|config|history|events|reports)?',component:()=>import('../modules/agents/AgentDetailPage.vue')},
  {path:'/sources/:id?',component:()=>import('../modules/sources/SourcesPage.vue')},
  {path:'/settings',redirect:'/settings/general'},
  {path:'/settings/:section(general|storage|resources|security|diagnostics)',component:()=>import('../modules/settings/SettingsPage.vue')},
  {path:'/:pathMatch(.*)*',redirect:'/dashboard'},
]})

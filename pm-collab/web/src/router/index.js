import { createRouter, createWebHistory } from 'vue-router'
import Guide from '../views/Guide.vue'
import Dashboard from '../views/Dashboard.vue'
import Tasks from '../views/Tasks.vue'
import TaskDetail from '../views/TaskDetail.vue'
import Handoff from '../views/Handoff.vue'
import Governance from '../views/Governance.vue'
import Docs from '../views/Docs.vue'
import Wbs from '../views/Wbs.vue'
import Members from '../views/Members.vue'
import Roles from '../views/Roles.vue'
import TaskTimeline from '../views/TaskTimeline.vue'
import ModuleSwimlane from '../views/ModuleSwimlane.vue'

const routes = [
  { path: '/', redirect: '/guide' },
  { path: '/guide', name: 'guide', component: Guide, meta: { title: '项目进程' } },
  { path: '/dashboard', name: 'dashboard', component: Dashboard, meta: { title: '项目看板' } },
  { path: '/wbs', name: 'wbs', component: Wbs, meta: { title: 'WBS 分解' } },
  { path: '/tasks', name: 'tasks', component: Tasks, meta: { title: '任务卡' } },
  { path: '/tasks/:code', name: 'task-detail', component: TaskDetail, meta: { title: '任务详情' } },
  { path: '/handoff', name: 'handoff', component: Handoff, meta: { title: '交接区与卡点' } },
  { path: '/timeline', name: 'timeline', component: TaskTimeline, meta: { title: '任务时间线' } },
  { path: '/swimlane', name: 'swimlane', component: ModuleSwimlane, meta: { title: '模块泳道' } },
  { path: '/governance', name: 'governance', component: Governance, meta: { title: '流程与门禁' } },
  { path: '/docs', name: 'docs', component: Docs, meta: { title: '文档与版本' } },
  { path: '/members', name: 'members', component: Members, meta: { title: '成员名册' } },
  { path: '/roles', name: 'roles', component: Roles, meta: { title: '角色卡' } }
]

export default createRouter({ history: createWebHistory(), routes })

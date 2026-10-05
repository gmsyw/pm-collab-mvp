import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Tasks from '../views/Tasks.vue'
import Handoff from '../views/Handoff.vue'
import Governance from '../views/Governance.vue'
import Docs from '../views/Docs.vue'
import Wbs from '../views/Wbs.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: Dashboard, meta: { title: '项目看板' } },
  { path: '/wbs', name: 'wbs', component: Wbs, meta: { title: 'WBS 分解' } },
  { path: '/tasks', name: 'tasks', component: Tasks, meta: { title: '任务卡' } },
  { path: '/handoff', name: 'handoff', component: Handoff, meta: { title: '交接区与卡点' } },
  { path: '/governance', name: 'governance', component: Governance, meta: { title: '流程与门禁' } },
  { path: '/docs', name: 'docs', component: Docs, meta: { title: '文档与版本' } }
]

export default createRouter({ history: createWebHistory(), routes })

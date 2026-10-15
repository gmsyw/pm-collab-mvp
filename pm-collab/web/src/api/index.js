import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 15000 })

// 当前项目上下文：所有读写按项目隔离；切换项目即切换数据视图
let currentProjectId = localStorage.getItem('pm_project') || ''

export function setCurrentProject(id) {
  currentProjectId = id || ''
  if (id) localStorage.setItem('pm_project', id)
  else localStorage.removeItem('pm_project')
}

export function getCurrentProject() {
  return currentProjectId
}

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('pm_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (currentProjectId) {
    config.params = { ...(config.params || {}), project_id: currentProjectId }
  }
  return config
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail || err.message
    if (status === 401) {
      // OSS-02：token 失效（含改密吊销）→ 清除本地凭证并回到登录页
      localStorage.removeItem('pm_token')
      localStorage.removeItem('pm_user')
      window.location.href = '/'
    }
    return Promise.reject(new Error(detail))
  }
)

export const authApi = {
  login: (username, password) => http.post('/auth/login', { username, password }),
  me: () => http.get('/auth/me'),
  changePassword: (old_password, new_password) =>
    http.post('/auth/change-password', { old_password, new_password })
}

export const rolesApi = {
  list: (params) => http.get('/roles', { params }),
  byCode: (code) => http.get(`/roles/code/${encodeURIComponent(code)}`),
  create: (data) => http.post('/roles', data),
  update: (id, data) => http.put(`/roles/${id}`, data),
  remove: (id) => http.delete(`/roles/${id}`)
}

export const membersApi = {
  list: (params) => http.get('/members', { params }),
  byCode: (code) => http.get(`/members/code/${encodeURIComponent(code)}`),
  create: (data) => http.post('/members', data),
  update: (id, data) => http.put(`/members/${id}`, data),
  remove: (id) => http.delete(`/members/${id}`)
}

export const tasksApi = {
  list: (params) => http.get('/tasks', { params }),
  byCode: (code) => http.get(`/tasks/code/${encodeURIComponent(code)}`),
  get: (id) => http.get(`/tasks/${id}`),
  create: (data) => http.post('/tasks', data),
  update: (id, data) => http.put(`/tasks/${id}`, data),
  transition: (id, target, note) => http.post(`/tasks/${id}/transition`, { target, note }),
  evidence: (id, paths, summary) => http.post(`/tasks/${id}/evidence`, { paths, summary })
}

export const processApi = {
  instance: () => http.get('/process/instance'),
  gates: () => http.get('/process/gates'),
  sign: (data) => http.post('/process/gates/sign', data),
  advance: (target) => http.post('/process/advance', { target }),
  testResult: (data) => http.post('/process/test-result', data),
  checklist: () => http.get('/process/checklist'),
  guide: () => http.get('/process/guide')
}

export const handoffApi = {
  list: (params) => http.get('/handoff', { params }),
  get: (id) => http.get(`/handoff/${id}`),
  zones: () => http.get('/handoff/zones'),
  create: (data) => http.post('/handoff', data),
  transition: (id, target) => http.post(`/handoff/${id}/transition`, { target }),
  sync: (direction) => http.post('/handoff/sync', null, { params: { direction } }),
  feed: (taskId, receiver) => http.post(`/handoff/feed/${taskId}`, null, { params: { receiver } }),
  recycle: (id) => http.post(`/handoff/recycle/${id}`),
  close: (id) => http.post(`/handoff/${id}/close`)
}

export const filesApi = {
  previewUrl: (path) => `/api/files/preview?path=${encodeURIComponent(path)}`,
  preview: (path) => http.get('/files/preview', { params: { path }, responseType: 'blob' })
}

export const checkpointsApi = {
  list: (params) => http.get('/checkpoints', { params }),
  create: (data) => http.post('/checkpoints', data),
  handle: (id, note) => http.post(`/checkpoints/${id}/handle`, { note })
}

export const reportApi = {
  metrics: () => http.get('/report/metrics'),
  digest: (push = true) => http.post('/report/digest', null, { params: { push } }),
  latest: () => http.get('/report/latest'),
  logs: (limit = 100) => http.get('/report/logs', { params: { limit } })
}

export const vizApi = {
  timeline: (taskCode) => http.get('/viz/timeline', { params: { task_code: taskCode } }),
  swimlane: () => http.get('/viz/swimlane')
}

export const docsApi = {
  libs: () => http.get('/libs/tree'),
  list: (params) => http.get('/docs', { params }),
  create: (data) => http.post('/docs', data),
  update: (id, data) => http.put(`/docs/${id}`, data),
  remove: (id) => http.delete(`/docs/${id}`),
  verify: (id) => http.get(`/docs/${id}/verify`),
  versions: (params) => http.get('/versions', { params }),
  addVersion: (data) => http.post('/versions', data),
  baseline: (id) => http.post(`/versions/${id}/baseline`),
  requirements: (params) => http.get('/requirements', { params })
}

export const projectsApi = {
  list: () => http.get('/projects'),
  create: (data) => http.post('/projects', data),
  get: (id) => http.get(`/projects/${id}`),
  update: (id, data) => http.put(`/projects/${id}`, data)
}

// WBS 分解：里程碑 / 工作包 / 子任务（四层 + 任务下拆子任务）
export const milestonesApi = {
  list: () => http.get('/wbs/milestones'),
  create: (data) => http.post('/wbs/milestones', data),
  update: (id, data) => http.put(`/wbs/milestones/${id}`, data),
  remove: (id) => http.delete(`/wbs/milestones/${id}`)
}

export const workpackagesApi = {
  list: (params) => http.get('/wbs/workpackages', { params }),
  create: (data) => http.post('/wbs/workpackages', data),
  update: (id, data) => http.put(`/wbs/workpackages/${id}`, data),
  remove: (id) => http.delete(`/wbs/workpackages/${id}`)
}

export const subtasksApi = {
  list: (params) => http.get('/wbs/subtasks', { params }),
  create: (data) => http.post('/wbs/subtasks', data),
  update: (id, data) => http.put(`/wbs/subtasks/${id}`, data),
  transition: (id, target) => http.post(`/wbs/subtasks/${id}/transition`, { target }),
  remove: (id) => http.delete(`/wbs/subtasks/${id}`)
}

export const wbsApi = {
  tree: () => http.get('/wbs/tree')
}

export default http

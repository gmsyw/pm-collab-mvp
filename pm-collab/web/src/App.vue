<template>
  <div v-if="!authed" class="pm-login-mask">
    <div class="pm-login-card">
      <h2 style="margin:0 0 4px">PM-Collab</h2>
      <p class="pm-muted" style="margin:0 0 20px">人机共用项目管理软件 · MVP</p>
      <el-form @submit.prevent="login">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" style="width:100%" :loading="loading" @click="login">登录</el-button>
      </el-form>
      <p class="pm-muted" style="margin-top:14px">默认账号：admin（首次启动密码见控制台打印，登录后请立即修改）</p>
      <el-alert v-if="error" :title="error" type="error" style="margin-top:12px" show-icon />
    </div>
  </div>

  <div v-else class="pm-layout">
    <div class="pm-header">
      <div class="pm-brand">PM-Collab <small>人机共用项目管理软件 v0.1.0</small></div>
      <div class="pm-header-right">
        <el-select
          v-model="projId" size="small" placeholder="选择项目" style="width:220px"
          @change="onProjectChange"
        >
          <el-option v-for="p in projects" :key="p.id" :label="`${p.code} · ${p.name}`" :value="p.id" />
        </el-select>
        <el-button size="small" @click="openNew">新建项目</el-button>
        <el-button size="small" @click="openEditProject" :disabled="!projId">编辑项目</el-button>
        <el-tag type="info" effect="plain" style="margin-right:12px">阶段 {{ stage }}</el-tag>
        <span class="pm-muted" style="margin-right:12px">{{ me || '—' }}</span>
        <el-button size="small" @click="pwdDlg = true">修改密码</el-button>
        <el-button size="small" @click="logout">退出</el-button>
      </div>
    </div>
    <div class="pm-body">
      <div class="pm-aside">
        <el-menu :default-active="route.path" router>
          <el-menu-item index="/guide">项目进程</el-menu-item>
          <el-menu-item index="/dashboard">项目看板</el-menu-item>
          <el-menu-item index="/wbs">WBS 分解</el-menu-item>
          <el-menu-item index="/tasks">任务卡</el-menu-item>
          <el-menu-item index="/handoff">交接区与卡点</el-menu-item>
          <el-menu-item index="/timeline">任务时间线</el-menu-item>
          <el-menu-item index="/swimlane">模块泳道</el-menu-item>
          <el-menu-item index="/governance">流程与门禁</el-menu-item>
          <el-menu-item index="/docs">文档与版本</el-menu-item>
          <el-menu-item index="/members">成员名册</el-menu-item>
          <el-menu-item index="/roles">角色卡</el-menu-item>
          </el-menu>
      </div>
      <div class="pm-main">
        <router-view :key="projId + '|' + route.path" />
      </div>
    </div>

    <QuickView />
    <FilePreview />
    <ChangePasswordDialog v-model:visible="pwdDlg" />

    <el-dialog v-model="newDlg" title="新建项目" width="420px">
      <el-form label-width="80px">
        <el-form-item label="项目编号">
          <el-input v-model="newForm.code" placeholder="如 PROJ-APP" />
        </el-form-item>
        <el-form-item label="项目名称">
          <el-input v-model="newForm.name" placeholder="如 客户端 App" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newDlg = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createProject">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editDlg" title="编辑项目" width="420px">
      <el-form label-width="80px">
        <el-form-item label="项目编号">
          <el-input v-model="editForm.code" disabled />
        </el-form-item>
        <el-form-item label="项目名称">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-input v-model="editForm.owner" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width:100%">
            <el-option label="进行中" value="进行中" />
            <el-option label="已归档" value="已归档" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDlg = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="saveProject">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi, processApi, projectsApi } from './api'
import { setCurrentProject, getCurrentProject } from './api'
import QuickView from './components/QuickView.vue'
import FilePreview from './components/FilePreview.vue'
import ChangePasswordDialog from './components/ChangePasswordDialog.vue'

const route = useRoute()
const router = useRouter()
const form = ref({ username: 'admin', password: '' })
const loading = ref(false)
const error = ref('')
const authed = ref(!!localStorage.getItem('pm_token'))
const me = ref(localStorage.getItem('pm_user') || '')
const stage = ref('S1')
const projects = ref([])
const projId = ref(getCurrentProject())
const newDlg = ref(false)
const editDlg = ref(false)
const pwdDlg = ref(false)
const creating = ref(false)
const newForm = ref({ code: '', name: '', description: '' })
const editForm = ref({ id: '', code: '', name: '', owner: '', status: '进行中', description: '' })

const stageLabel = computed(() => stage.value)

async function loadProjects() {
  try {
    projects.value = await projectsApi.list()
    if (!getCurrentProject() && projects.value.length) {
      setCurrentProject(projects.value[0].id)
      projId.value = getCurrentProject()
    } else if (getCurrentProject()) {
      projId.value = getCurrentProject()
    }
  } catch (e) {
    projects.value = []
  }
}

function onProjectChange(id) {
  setCurrentProject(id)
}

async function login() {
  loading.value = true
  error.value = ''
  try {
    const res = await authApi.login(form.value.username, form.value.password)
    localStorage.setItem('pm_token', res.access_token)
    localStorage.setItem('pm_user', res.username)
    authed.value = true
    me.value = res.username
    await loadProjects()
    ElMessage.success('登录成功')
    router.push('/guide')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function logout() {
  localStorage.removeItem('pm_token')
  localStorage.removeItem('pm_user')
  localStorage.removeItem('pm_project')
  authed.value = false
}

function openNew() {
  newForm.value = { code: '', name: '', description: '' }
  newDlg.value = true
}

async function openEditProject() {
  if (!projId.value) return
  try {
    const p = await projectsApi.get(projId.value)
    editForm.value = { id: p.id, code: p.code, name: p.name, owner: p.owner || '', status: p.status || '进行中', description: p.description || '' }
    editDlg.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function saveProject() {
  if (!editForm.value.name) return ElMessage.warning('请填写项目名称')
  creating.value = true
  try {
    await projectsApi.update(editForm.value.id, {
      code: editForm.value.code, name: editForm.value.name, owner: editForm.value.owner,
      status: editForm.value.status, description: editForm.value.description,
    })
    ElMessage.success('项目已更新')
    editDlg.value = false
    await loadProjects()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

async function createProject() {
  if (!newForm.value.code || !newForm.value.name) {
    ElMessage.warning('请填写项目编号与名称')
    return
  }
  creating.value = true
  try {
    const res = await projectsApi.create({ ...newForm.value })
    ElMessage.success(`项目 ${res.code} 已创建`)
    newDlg.value = false
    await loadProjects()
    if (res.id) {
      setCurrentProject(res.id)
      projId.value = res.id
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

async function loadStage() {
  try {
    const res = await processApi.instance()
    stage.value = `${res.stage} ${res.stage_name}`
  } catch (e) {
    stage.value = '—'
  }
}

onMounted(() => {
  if (authed.value) {
    loadProjects()
    loadStage()
  }
})
</script>

<style>
.pm-header-right { display: flex; align-items: center; gap: 8px; }
</style>

<template>
  <el-drawer
    v-model="quickView.open"
    :title="title"
    direction="rtl"
    size="440px"
    :close-on-click-modal="true"
  >
    <div v-loading="loading" style="min-height: 120px">
      <el-alert v-if="error" :title="error" type="error" show-icon />
      <template v-else-if="data">
        <!-- 任务卡 -->
        <template v-if="quickView.type === 'task'">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="编号"><RefLink type="task" :value="data.code" :label="data.code" /></el-descriptions-item>
            <el-descriptions-item label="目标">{{ data.title }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusType(data.status)" size="small">{{ data.status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="优先级">{{ data.priority }}</el-descriptions-item>
            <el-descriptions-item label="里程碑 / 工作包">{{ data.milestone || '—' }} / {{ data.work_package || '—' }}</el-descriptions-item>
            <el-descriptions-item label="模块标签">{{ data.module_tag || '—' }}</el-descriptions-item>
            <el-descriptions-item label="截止">{{ data.due_date || '—' }}</el-descriptions-item>
            <el-descriptions-item label="人-A">
              <RefLink v-if="data.human_owner && data.human_owner !== 'H'" type="member" :value="data.human_owner" :label="data.human_owner" />
              <span v-else>{{ data.human_owner || '—' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="AI-R">
              <RefLink v-if="data.ai_executor" type="member" :value="data.ai_executor" :label="data.ai_executor" />
              <span v-else>—</span>
            </el-descriptions-item>
            <el-descriptions-item label="依赖">
              <span v-if="(data.dependencies || []).length">
                <RefLink v-for="d in data.dependencies" :key="d" type="task" :value="d" :label="d" style="margin-right:6px" />
              </span>
              <span v-else>—</span>
            </el-descriptions-item>
            <el-descriptions-item label="证据">
              <div v-if="(data.evidence || []).length">
                <div v-for="p in data.evidence" :key="p" class="ev-item" @click="openFilePreview(p)">
                  📎 {{ p }}
                </div>
              </div>
              <span v-else>—</span>
            </el-descriptions-item>
          </el-descriptions>
        </template>

        <!-- 成员 -->
        <template v-else-if="quickView.type === 'member'">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="编号">{{ data.code }}</el-descriptions-item>
            <el-descriptions-item label="姓名">{{ data.name }}</el-descriptions-item>
            <el-descriptions-item label="类型">{{ data.member_type }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ data.status }}</el-descriptions-item>
            <el-descriptions-item label="汇报对象">{{ data.reports_to || '—' }}</el-descriptions-item>
          </el-descriptions>
        </template>

        <!-- 角色卡 -->
        <template v-else-if="quickView.type === 'role'">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="编号">{{ data.code }}</el-descriptions-item>
            <el-descriptions-item label="名称">{{ data.name }}</el-descriptions-item>
            <el-descriptions-item label="权限级别">{{ data.permission_level }}</el-descriptions-item>
            <el-descriptions-item label="责任">{{ data.responsibility }}</el-descriptions-item>
          </el-descriptions>
        </template>

        <!-- 交接单 -->
        <template v-else-if="quickView.type === 'handoff'">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="编号">{{ data.code }}</el-descriptions-item>
            <el-descriptions-item label="任务">
              <RefLink v-if="data.task_code" type="task" :value="data.task_code" :label="data.task_code" />
              <span v-else>—</span>
            </el-descriptions-item>
            <el-descriptions-item label="发送 → 接收">{{ data.sender }} → {{ data.receiver }}</el-descriptions-item>
            <el-descriptions-item label="区域">{{ data.zone }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusType(data.status)" size="small">{{ data.status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="事件类型 / 轮次">{{ data.event_type || '—' }} / 第 {{ data.round || 0 }} 轮</el-descriptions-item>
            <el-descriptions-item label="QA 证据">
              <pre class="qa-json">{{ JSON.stringify(data.evidence || {}, null, 2) }}</pre>
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </template>
    </div>

    <template #footer>
      <el-button @click="closeQuickView">关闭</el-button>
      <el-button type="primary" @click="goFull">前往完整页面</el-button>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { quickView, closeQuickView } from '../composables/useQuickView'
import { openFilePreview } from '../composables/useFilePreview'
import { tasksApi, membersApi, rolesApi, handoffApi } from '../api'
import RefLink from './RefLink.vue'

const router = useRouter()
const loading = ref(false)
const data = ref(null)
const error = ref('')

const TITLE = { task: '任务卡速览', member: '成员速览', role: '角色卡速览', handoff: '交接单速览', doc: '文档速览' }
const ROUTE = { task: '/tasks', member: '/members', role: '/roles', handoff: '/handoff', doc: '/docs' }
const title = computed(() => TITLE[quickView.type] || '关联速览')

function statusType(s) {
  return { 待办: 'info', 进行中: 'primary', 待评审: 'warning', 通过: 'success', 返工: 'danger', 关闭: 'success', 阻塞: 'danger', 已投喂: 'warning', 已回收: 'warning', 已闭环: 'success', 取消: 'info' }[s] || 'info'
}

async function load() {
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const { type, value, by } = quickView
    if (type === 'task') data.value = by === 'id' ? await tasksApi.get(value) : await tasksApi.byCode(value)
    else if (type === 'member') data.value = await membersApi.byCode(value)
    else if (type === 'role') data.value = await rolesApi.byCode(value)
    else if (type === 'handoff') data.value = await handoffApi.get(value)
    else throw new Error('暂不支持的关联类型：' + type)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => quickView.open, (o) => { if (o) load() })

function goFull() {
  if (quickView.type === 'task') {
    // 跳转到真正的任务详情页（/tasks/:code），支持从详情页内依赖 RefLink 再跳转
    router.push(`/tasks/${encodeURIComponent(quickView.value)}`)
  } else {
    const q = quickView.type === 'handoff' ? { id: quickView.value } : { code: quickView.label }
    router.push({ path: ROUTE[quickView.type] || '/tasks', query: q })
  }
  closeQuickView()
}
</script>

<style scoped>
.ev-item { cursor: pointer; color: var(--el-color-primary); padding: 2px 0; }
.ev-item:hover { text-decoration: underline; }
.qa-json { margin: 0; font-size: 12px; white-space: pre-wrap; max-height: 200px; overflow: auto; background: var(--el-fill-color-light); padding: 6px; border-radius: 4px; }
</style>

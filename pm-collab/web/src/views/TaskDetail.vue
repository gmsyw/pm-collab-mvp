<template>
  <div v-loading="loading" class="task-detail">
    <el-alert v-if="error" :title="error" type="error" show-icon class="mb" />

    <div v-else-if="task" class="pm-card">
      <!-- 头部：编号 / 目标 / 状态 / 操作 -->
      <div class="td-head">
        <div class="td-title">
          <el-button text @click="goBack">← 返回任务卡</el-button>
          <h2 style="margin:6px 0">
            <RefLink type="task" :value="task.code" :label="task.code" />
            <span class="td-goal">{{ task.title }}</span>
          </h2>
          <div class="td-tags">
            <el-tag :type="statusType(task.status)" size="small">{{ task.status }}</el-tag>
            <el-tag :type="task.priority === 'P0' ? 'danger' : task.priority === 'P1' ? 'warning' : 'info'" size="small" effect="plain">{{ task.priority }}</el-tag>
            <span class="td-muted">里程碑：{{ task.milestone || '—' }} · 工作包：{{ task.work_package || '—' }}</span>
            <span class="td-muted" v-if="task.module_tag">· 模块：{{ task.module_tag }}</span>
          </div>
        </div>
        <div class="td-actions">
          <el-select v-model="target" size="small" placeholder="迁移至" style="width:130px">
            <el-option v-for="t in allowedTargets" :key="t" :label="t" :value="t" />
          </el-select>
          <el-button size="small" type="primary" :loading="acting" @click="doTransition">迁移</el-button>
        </div>
      </div>

      <el-descriptions :column="2" border size="small" class="mb">
        <el-descriptions-item label="背景目标" :span="2">{{ task.goal || '—' }}</el-descriptions-item>
        <el-descriptions-item label="输入" :span="2">{{ task.inputs || '—' }}</el-descriptions-item>
        <el-descriptions-item label="交付物及路径" :span="2">{{ task.deliverables || '—' }}</el-descriptions-item>
        <el-descriptions-item label="验收标准" :span="2">{{ task.acceptance || '—' }}</el-descriptions-item>
        <el-descriptions-item label="完成摘要" :span="2">{{ task.summary || '—' }}</el-descriptions-item>
        <el-descriptions-item label="人-A">
          <RefLink v-if="task.human_owner && task.human_owner !== 'H'" type="member" :value="task.human_owner" :label="task.human_owner" />
          <span v-else>{{ task.human_owner || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="AI-R">
          <RefLink v-if="task.ai_executor" type="member" :value="task.ai_executor" :label="task.ai_executor" />
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="依赖">
          <span v-if="(task.dependencies || []).length">
            <RefLink v-for="d in task.dependencies" :key="d" type="task" :value="d" :label="d" style="margin-right:6px" />
          </span>
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="返工次数">{{ task.rework_count || 0 }}</el-descriptions-item>
        <el-descriptions-item label="起止">
          {{ task.start_date || '—' }} → {{ task.due_date || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ task.updated_at || '—' }}</el-descriptions-item>
      </el-descriptions>

      <!-- 证据 -->
      <div class="td-ev">
        <h3>证据文件（{{ (task.evidence || []).length }}）</h3>
        <div v-if="(task.evidence || []).length">
          <div v-for="p in task.evidence" :key="p" class="ev-item" @click="openFilePreview(p)">📎 {{ p }}</div>
        </div>
        <el-empty v-else description="暂无证据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tasksApi } from '../api'
import RefLink from '../components/RefLink.vue'
import { openFilePreview } from '../composables/useFilePreview'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref('')
const task = ref(null)
const target = ref('')
const acting = ref(false)

const TRANSITIONS = {
  待办: ['进行中', '阻塞', '取消'],
  进行中: ['待评审', '阻塞', '取消'],
  待评审: ['通过', '返工', '阻塞'],
  通过: ['关闭'],
  返工: ['进行中', '阻塞', '取消'],
  阻塞: ['进行中', '取消'],
  关闭: [],
  取消: []
}
const allowedTargets = computed(() => TRANSITIONS[task.value?.status] || [])

function statusType(s) {
  return { 待办: 'info', 进行中: 'primary', 待评审: 'warning', 通过: 'success', 返工: 'danger', 关闭: 'success', 阻塞: 'danger', 取消: 'info' }[s] || 'info'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    task.value = await tasksApi.byCode(route.params.code)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/tasks')
}

async function doTransition() {
  if (!target.value) return ElMessage.warning('请选择目标状态')
  acting.value = true
  try {
    const note = target.value === '阻塞' ? (prompt('阻塞原因与责任方：') || '') : ''
    await tasksApi.transition(task.value.id, target.value, note)
    ElMessage.success(`${task.value.code}：${task.value.status} → ${target.value}`)
    target.value = ''
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    acting.value = false
  }
}

onMounted(load)
// 同一详情页在编号间切换时（如从依赖 RefLink 跳转）重新加载
watch(() => route.params.code, (c, old) => { if (c && c !== old) load() })
</script>

<style scoped>
.task-detail { max-width: 960px; margin: 0 auto; }
.td-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.td-goal { margin-left: 8px; font-weight: 600; }
.td-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.td-muted { color: var(--el-text-color-secondary); font-size: 13px; }
.td-actions { display: flex; gap: 8px; align-items: center; }
.mb { margin-bottom: 16px; }
.ev-item { cursor: pointer; color: var(--el-color-primary); padding: 4px 0; }
.ev-item:hover { text-decoration: underline; }
</style>

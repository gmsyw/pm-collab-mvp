<template>
  <div>
    <div class="pm-card">
      <h3>任务详情 · 过程时间线（V0.4）</h3>
      <div class="pm-row" style="align-items: center">
        <el-select
          v-model="code"
          filterable
          clearable
          placeholder="选择任务（可搜索编号/目标）"
          style="width: 320px"
          @change="query"
        >
          <el-option v-for="t in tasks" :key="t.id" :label="`${t.code} · ${t.title}`" :value="t.code" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="query">查询</el-button>
      </div>
      <el-alert v-if="err" :title="err" type="error" show-icon style="margin-top: 10px" />
    </div>

    <div v-if="task" class="pm-row">
      <div class="pm-card pm-flex1">
        <h4>任务卡（14 字段）</h4>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="编号"><RefLink type="task" :value="task.code" :label="task.code" /></el-descriptions-item>
          <el-descriptions-item label="标题">{{ task.title }}</el-descriptions-item>
          <el-descriptions-item label="目标">{{ task.goal }}</el-descriptions-item>
          <el-descriptions-item label="输入">{{ task.inputs }}</el-descriptions-item>
          <el-descriptions-item label="交付物">{{ task.deliverables }}</el-descriptions-item>
          <el-descriptions-item label="验收标准">{{ task.acceptance }}</el-descriptions-item>
          <el-descriptions-item label="人/AI">
            <RefLink v-if="task.human_owner && task.human_owner !== 'H'" type="member" :value="task.human_owner" :label="task.human_owner" />
            <span v-else>{{ task.human_owner || '—' }}</span>
            <span style="margin: 0 6px">/</span>
            <RefLink v-if="task.ai_executor" type="member" :value="task.ai_executor" :label="task.ai_executor" />
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">{{ task.status }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ task.priority }}</el-descriptions-item>
          <el-descriptions-item label="模块标签">{{ task.module_tag || '—' }}</el-descriptions-item>
          <el-descriptions-item label="父子链">{{ task.parent_task_id || '—' }}</el-descriptions-item>
          <el-descriptions-item label="完成摘要">{{ task.summary }}</el-descriptions-item>
        </el-descriptions>
      </div>
      <div class="pm-card pm-flex1">
        <h4>过程时间线</h4>
        <el-timeline v-if="nodes.length">
          <el-timeline-item
            v-for="(n, i) in nodes"
            :key="i"
            :color="colorOf(n.color)"
            :hollow="!n.human_sign"
          >
            <div :style="n.human_sign ? 'font-weight: 700' : ''">
              <el-tag :color="colorOf(n.color)" style="color: #fff; border: none">{{ n.event_type }}</el-tag>
              <span v-if="n.round" style="margin-left: 6px">第 {{ n.round }} 轮</span>
              <span v-if="n.human_sign" style="margin-left: 6px; color: #b8860b">★ 人类签字</span>
            </div>
            <div class="pm-muted">{{ n.sender }} → {{ n.receiver }} · {{ n.time }}</div>
            <div v-if="n.payload_path" class="pm-mono" style="font-size: 12px">{{ n.payload_path }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="该任务暂无交接单记录" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { vizApi, tasksApi } from '../api'
import RefLink from '../components/RefLink.vue'

const code = ref('')
const loading = ref(false)
const err = ref('')
const task = ref(null)
const nodes = ref([])
const tasks = ref([])

const COLOR = {
  blue: '#409EFF', purple: '#9C27B0', cyan: '#17C2B8', orange: '#FF9800',
  green: '#67C23A', gold: '#FFD700', gray: '#909399',
}
function colorOf(c) { return COLOR[c] || '#909399' }

async function loadTasks() {
  try {
    tasks.value = await tasksApi.list()
  } catch (e) {
    ElMessage.error('任务列表加载失败：' + e.message)
  }
}

async function query() {
  if (!code.value || !code.value.trim()) return ElMessage.warning('请选择任务')
  loading.value = true
  err.value = ''
  task.value = null
  nodes.value = []
  try {
    const res = await vizApi.timeline(code.value.trim())
    task.value = res.task
    nodes.value = res.nodes
    if (!res.nodes.length) ElMessage.info('该任务暂无交接单记录')
  } catch (e) {
    err.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(loadTasks)
</script>

<template>
  <div>
    <div class="pm-card">
      <h3>任务卡
        <el-button size="small" type="primary" style="float:right" @click="openCreate">新建任务卡</el-button>
      </h3>
      <el-table :data="tasks" size="small" border>
        <el-table-column label="编号" width="80">
          <template #default="{ row }">
            <RefLink type="task" :value="row.code" :label="row.code" />
          </template>
        </el-table-column>
        <el-table-column prop="title" label="目标" min-width="160" />
        <el-table-column prop="milestone" label="里程碑" width="100" />
        <el-table-column prop="work_package" label="工作包" width="130" />
        <el-table-column label="人-A" width="100">
          <template #default="{ row }">
            <RefLink v-if="row.human_owner && row.human_owner !== 'H'" type="member" :value="row.human_owner" :label="row.human_owner" />
            <span v-else>{{ row.human_owner || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AI-R" width="130">
          <template #default="{ row }">
            <RefLink v-if="row.ai_executor" type="member" :value="row.ai_executor" :label="row.ai_executor" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80">
          <template #default="{ row }">
            <el-tag :type="row.priority === 'P0' ? 'danger' : row.priority === 'P1' ? 'warning' : 'info'">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="due_date" label="截止" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="证据" width="70">
          <template #default="{ row }">
            <a class="ev-count" @click="openEvidenceList(row)">{{ (row.evidence || []).length }}</a>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-select size="small" v-model="row._target" placeholder="迁移至" style="width:110px">
              <el-option v-for="t in allowedTargets(row.status)" :key="t" :label="t" :value="t" />
            </el-select>
            <el-button size="small" type="primary" plain @click="doTransition(row)">迁移</el-button>
            <el-button size="small" @click="openEvidence(row)">证据</el-button>
            <el-button size="small" @click="goWbs(row)">拆解子任务</el-button>
            <el-button size="small" @click="feed(row)">投喂</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="createVisible" title="新建任务卡（14 字段）" width="640px">
      <el-form :model="form" label-width="110px" size="small">
        <el-form-item label="编号"><el-input v-model="form.code" placeholder="T26" /></el-form-item>
        <el-form-item label="目标"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="输入"><el-input v-model="form.inputs" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="交付物及路径"><el-input v-model="form.deliverables" /></el-form-item>
        <el-form-item label="验收标准"><el-input v-model="form.acceptance" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="人-A"><el-input v-model="form.human_owner" /></el-form-item>
        <el-form-item label="AI-R"><el-input v-model="form.ai_executor" /></el-form-item>
        <el-form-item label="依赖"><el-input v-model="form.dependencies" placeholder="逗号分隔：T01,T02" /></el-form-item>
        <el-form-item label="起止">
          <el-input v-model="form.start_date" placeholder="开始 YYYY-MM-DD" style="width:47%" />
          <el-input v-model="form.due_date" placeholder="截止 YYYY-MM-DD" style="width:47%;margin-left:6%" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="form.priority">
            <el-radio-button value="P0" label="P0" />
            <el-radio-button value="P1" label="P1" />
            <el-radio-button value="P2" label="P2" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="里程碑">
          <el-select v-model="form.milestone_id" placeholder="选择里程碑（可选）" clearable filterable style="width:100%">
            <el-option v-for="m in milestones" :key="m.id" :label="`${m.code} · ${m.name}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="工作包">
          <el-select v-model="form.work_package_id" placeholder="选择工作包（可选）" clearable filterable style="width:100%">
            <el-option v-for="w in workpackages" :key="w.id" :label="`${w.code} · ${w.name}`" :value="w.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="evidenceVisible" title="登记证据（无证据不得置为通过）" width="520px">
      <el-form label-width="80px" size="small">
        <el-form-item label="证据路径">
          <el-input v-model="evidenceForm.paths" type="textarea" :rows="3" placeholder="分号分隔多个路径" />
        </el-form-item>
        <el-form-item label="完成摘要">
          <el-input v-model="evidenceForm.summary" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="evidenceVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEvidence">登记</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑任务卡（14 字段）" width="640px">
      <el-form :model="editForm" label-width="110px" size="small">
        <el-form-item label="编号"><el-input v-model="editForm.code" disabled /></el-form-item>
        <el-form-item label="目标"><el-input v-model="editForm.title" /></el-form-item>
        <el-form-item label="输入"><el-input v-model="editForm.inputs" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="交付物及路径"><el-input v-model="editForm.deliverables" /></el-form-item>
        <el-form-item label="验收标准"><el-input v-model="editForm.acceptance" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="人-A"><el-input v-model="editForm.human_owner" /></el-form-item>
        <el-form-item label="AI-R"><el-input v-model="editForm.ai_executor" /></el-form-item>
        <el-form-item label="依赖"><el-input v-model="editForm.dependencies" placeholder="逗号分隔：T01,T02" /></el-form-item>
        <el-form-item label="当前依赖">
          <span v-if="splitDeps(editForm.dependencies).length">
            <RefLink v-for="d in splitDeps(editForm.dependencies)" :key="d" type="task" :value="d" :label="d" style="margin-right:6px" />
          </span>
          <span v-else class="pm-muted">无</span>
        </el-form-item>
        <el-form-item label="起止">
          <el-input v-model="editForm.start_date" placeholder="开始 YYYY-MM-DD" style="width:47%" />
          <el-input v-model="editForm.due_date" placeholder="截止 YYYY-MM-DD" style="width:47%;margin-left:6%" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="editForm.priority">
            <el-radio-button value="P0" label="P0" />
            <el-radio-button value="P1" label="P1" />
            <el-radio-button value="P2" label="P2" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="里程碑">
          <el-select v-model="editForm.milestone_id" placeholder="选择里程碑（可选）" clearable filterable style="width:100%">
            <el-option v-for="m in milestones" :key="m.id" :label="`${m.code} · ${m.name}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="工作包">
          <el-select v-model="editForm.work_package_id" placeholder="选择工作包（可选）" clearable filterable style="width:100%">
            <el-option v-for="w in workpackages" :key="w.id" :label="`${w.code} · ${w.name}`" :value="w.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="evListVisible" title="证据文件" width="520px">
      <div v-if="evList.length">
        <div v-for="p in evList" :key="p" class="ev-item" @click="openFilePreview(p)">📎 {{ p }}</div>
      </div>
      <el-empty v-else description="暂无证据" />
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { handoffApi, tasksApi, milestonesApi, workpackagesApi } from '../api'
import RefLink from '../components/RefLink.vue'
import { openFilePreview } from '../composables/useFilePreview'

const route = useRoute()
const router = useRouter()
const tasks = ref([])
const evListVisible = ref(false)
const evList = ref([])
const milestones = ref([])
const workpackages = ref([])
const createVisible = ref(false)
const evidenceVisible = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const current = ref(null)
const form = ref(blank())
const editForm = ref(blank())
const evidenceForm = ref({ paths: '', summary: '' })

// 与服务层 state_machine.TASK_TRANSITIONS 保持一致（非法迁移由后端最终拦截）
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

function blank() {
  return {
    code: '', title: '', inputs: '', deliverables: '', acceptance: '',
    human_owner: 'H', ai_executor: '', dependencies: '', start_date: '', due_date: '',
    priority: 'P2', milestone: 'MVP', work_package: '', milestone_id: '', work_package_id: ''
  }
}

function allowedTargets(status) {
  return TRANSITIONS[status] || []
}

function statusType(s) {
  return { 待办: 'info', 进行中: 'primary', 待评审: 'warning', 通过: 'success', 返工: 'danger', 关闭: 'success', 阻塞: 'danger', 取消: 'info' }[s] || 'info'
}

function openEvidenceList(row) {
  evList.value = Array.isArray(row.evidence) ? row.evidence : []
  evListVisible.value = true
}

function splitDeps(s) {
  if (!s) return []
  if (Array.isArray(s)) return s
  return String(s).split(/[,，]/).map((x) => x.trim()).filter(Boolean)
}

async function load() {
  try {
    const [ts, ms, wps] = await Promise.all([
      tasksApi.list(), milestonesApi.list(), workpackagesApi.list(),
    ])
    tasks.value = ts
    milestones.value = ms
    workpackages.value = wps
    if (route.query.code) {
      const t = ts.find((x) => x.code === route.query.code)
      if (t) openEdit(t)
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function goWbs() {
  router.push('/wbs')
}

async function submitCreate() {
  try {
    const payload = { ...form.value, dependencies: form.value.dependencies ? form.value.dependencies.split(/[,，]/).map((s) => s.trim()).filter(Boolean) : [] }
    await tasksApi.create(payload)
    ElMessage.success('任务卡已创建')
    createVisible.value = false
    form.value = blank()
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function doTransition(row) {
  if (!row._target) return ElMessage.warning('请选择目标状态')
  try {
    const note = row._target === '阻塞' ? (prompt('阻塞原因与责任方：') || '') : ''
    await tasksApi.transition(row.id, row._target, note)
    ElMessage.success(`${row.code}：${row.status} → ${row._target}`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function openEvidence(row) {
  current.value = row
  evidenceForm.value = { paths: (row.evidence || []).join(';'), summary: row.summary || '' }
  evidenceVisible.value = true
}

async function submitEvidence() {
  try {
    const paths = evidenceForm.value.paths.split(/[;；\n]/).map((s) => s.trim()).filter(Boolean)
    await tasksApi.evidence(current.value.id, paths, evidenceForm.value.summary)
    ElMessage.success('证据已登记')
    evidenceVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function feed(row) {
  try {
    await handoffApi.feed(row.id, row.ai_executor)
    ElMessage.success(`已生成派单文件至「派单/」，交接单置为已投喂`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function openCreate() {
  form.value = blank()
  createVisible.value = true
}

function openEdit(row) {
  editForm.value = {
    id: row.id, code: row.code, title: row.title, inputs: row.inputs || '', deliverables: row.deliverables || '',
    acceptance: row.acceptance || '', human_owner: row.human_owner || 'H', ai_executor: row.ai_executor || '',
    dependencies: Array.isArray(row.dependencies) ? row.dependencies.join(',') : (row.dependencies || ''),
    start_date: row.start_date || '', due_date: row.due_date || '', priority: row.priority || 'P2',
    milestone_id: row.milestone_id || '', work_package_id: row.work_package_id || '',
  }
  editVisible.value = true
}

async function submitEdit() {
  if (!editForm.value.title) return ElMessage.warning('请填写目标')
  saving.value = true
  try {
    const payload = {
      ...editForm.value,
      dependencies: editForm.value.dependencies
        ? editForm.value.dependencies.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
        : [],
    }
    delete payload.id
    await tasksApi.update(editForm.value.id, payload)
    ElMessage.success('任务卡已更新')
    editVisible.value = false
    load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

onMounted(load)
</script>

<style scoped>
.ev-count { color: var(--el-color-primary); cursor: pointer; font-weight: 600; }
.ev-count:hover { text-decoration: underline; }
.ev-item { cursor: pointer; color: var(--el-color-primary); padding: 4px 0; }
.ev-item:hover { text-decoration: underline; }
</style>

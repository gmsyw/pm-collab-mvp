<template>
  <div>
    <div class="pm-header-bar">
      <h3 style="margin:0">WBS 工作分解结构
        <el-tag size="small" type="info" effect="plain">项目 → 里程碑 → 工作包 → 任务 → 子任务</el-tag>
      </h3>
      <el-button size="small" type="primary" @click="openMilestone">+ 里程碑</el-button>
    </div>

    <div v-if="loading" class="pm-muted">加载中…</div>
    <div v-else>
      <div v-for="m in tree.milestones" :key="m.id" class="wbs-ms">
        <el-card shadow="never" class="wbs-card">
          <template #header>
            <div class="wbs-card-head">
              <span><b>{{ m.code }}</b> · {{ m.name }}</span>
              <el-tag size="small" :type="statusType(m.status)">{{ m.status }}</el-tag>
              <span class="wbs-actions">
                <el-button size="small" @click="openWorkPackage(m)">+ 工作包</el-button>
                <el-button size="small" text @click="editMilestone(m)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeMilestone(m)">删除</el-button>
              </span>
            </div>
          </template>

          <div v-for="wp in m.work_packages" :key="wp.id" class="wbs-wp">
            <div class="wbs-wp-head">
              <span><b>{{ wp.code }}</b> · {{ wp.name }}</span>
              <el-tag size="small" :type="statusType(wp.status)">{{ wp.status }}</el-tag>
              <span class="wbs-actions">
                <el-button size="small" text @click="editWorkPackage(wp)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeWorkPackage(wp)">删除</el-button>
              </span>
            </div>

            <div v-for="t in wp.tasks" :key="t.id" class="wbs-task">
              <div class="wbs-task-head">
                <RefLink type="task" :value="t.code" :label="t.code" class="wbs-code" />
                <span>{{ t.title }}</span>
                <el-tag size="small" :type="statusType(t.status)">{{ t.status }}</el-tag>
                <el-tag v-if="t.sub_task_count" size="small" type="warning">子任务 {{ t.sub_task_count }}</el-tag>
                <span class="wbs-actions">
                  <el-button size="small" type="primary" plain @click="openSubTask(t)">+ 子任务</el-button>
                </span>
              </div>
              <div v-if="t.sub_tasks && t.sub_tasks.length" class="wbs-subs">
                <div v-for="s in t.sub_tasks" :key="s.id" class="wbs-sub">
                  <span class="wbs-code">{{ s.code }}</span>
                  <span class="wbs-sub-title">{{ s.title }}</span>
                  <el-tag size="small" :type="statusType(s.status)">{{ s.status }}</el-tag>
                  <span class="wbs-muted">{{ s.assignee || '—' }} · {{ s.priority }}</span>
                  <span class="wbs-actions">
                    <el-button size="small" @click="openSubEdit(s)">编辑</el-button>
                    <el-select size="small" v-model="s._target" placeholder="迁移" style="width:100px">
                      <el-option v-for="tg in subTargets(s.status)" :key="tg" :label="tg" :value="tg" />
                    </el-select>
                    <el-button size="small" @click="transitionSub(s)">应用</el-button>
                    <el-button size="small" text type="danger" @click="removeSub(s)">删除</el-button>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <el-empty v-if="!m.work_packages.length" description="该里程碑下暂无工作包" :image-size="40" />
        </el-card>
      </div>

      <!-- 未归类任务 -->
      <div v-if="tree.unclassified_tasks && tree.unclassified_tasks.length" class="wbs-ms">
        <el-card shadow="never" class="wbs-card">
          <template #header><span>未归类任务</span></template>
          <div v-for="t in tree.unclassified_tasks" :key="t.id" class="wbs-task">
            <div class="wbs-task-head">
              <span class="wbs-code">{{ t.code }}</span>
              <span>{{ t.title }}</span>
              <el-tag size="small" :type="statusType(t.status)">{{ t.status }}</el-tag>
              <el-tag v-if="t.sub_task_count" size="small" type="warning">子任务 {{ t.sub_task_count }}</el-tag>
              <span class="wbs-actions">
                <el-button size="small" type="primary" plain @click="openSubTask(t)">+ 子任务</el-button>
              </span>
            </div>
            <div v-if="t.sub_tasks && t.sub_tasks.length" class="wbs-subs">
              <div v-for="s in t.sub_tasks" :key="s.id" class="wbs-sub">
                <span class="wbs-code">{{ s.code }}</span>
                <span class="wbs-sub-title">{{ s.title }}</span>
                <el-tag size="small" :type="statusType(s.status)">{{ s.status }}</el-tag>
                <span class="wbs-muted">{{ s.assignee || '—' }} · {{ s.priority }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </div>

      <el-empty v-if="!tree.milestones.length" description="暂无里程碑，点击右上角创建第一个里程碑" />
    </div>

    <!-- 里程碑对话框 -->
    <el-dialog v-model="msDlg" :title="msForm.id ? '编辑里程碑' : '新建里程碑'" width="460px">
      <el-form label-width="90px" size="small">
        <el-form-item label="编号"><el-input v-model="msForm.code" placeholder="如 M1 / MVP" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="msForm.name" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="msForm.status"><el-option v-for="s in MS_STATUS" :key="s" :label="s" :value="s" /></el-select>
        </el-form-item>
        <el-form-item label="负责人"><el-input v-model="msForm.owner" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="msForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="msDlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveMilestone">保存</el-button>
      </template>
    </el-dialog>

    <!-- 工作包对话框 -->
    <el-dialog v-model="wpDlg" :title="wpForm.id ? '编辑工作包' : '新建工作包'" width="460px">
      <el-form label-width="90px" size="small">
        <el-form-item label="所属里程碑">
          <el-select v-model="wpForm.milestone_id" :disabled="!!wpForm.id">
            <el-option v-for="m in milestones" :key="m.id" :label="`${m.code} · ${m.name}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="编号"><el-input v-model="wpForm.code" placeholder="如 WP0" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="wpForm.name" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="wpForm.status"><el-option v-for="s in MS_STATUS" :key="s" :label="s" :value="s" /></el-select>
        </el-form-item>
        <el-form-item label="负责人"><el-input v-model="wpForm.owner" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="wpForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="wpDlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveWorkPackage">保存</el-button>
      </template>
    </el-dialog>

    <!-- 子任务对话框 -->
    <el-dialog v-model="subDlg" :title="`新建子任务（隶属 ${subTaskParentCode}）`" width="480px">
      <el-form label-width="90px" size="small">
        <el-form-item label="编号"><el-input v-model="subForm.code" placeholder="如 ST-001" /></el-form-item>
        <el-form-item label="标题"><el-input v-model="subForm.title" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="subForm.assignee" /></el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="subForm.priority">
            <el-radio-button value="P0" label="P0" />
            <el-radio-button value="P1" label="P1" />
            <el-radio-button value="P2" label="P2" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="截止"><el-input v-model="subForm.due_date" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="subForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subDlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSubTask">保存</el-button>
      </template>
    </el-dialog>

    <!-- 子任务编辑对话框 -->
    <el-dialog v-model="subEditDlg" title="编辑子任务" width="480px">
      <el-form label-width="90px" size="small">
        <el-form-item label="编号"><el-input v-model="subEditForm.code" disabled /></el-form-item>
        <el-form-item label="标题"><el-input v-model="subEditForm.title" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="subEditForm.assignee" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="subEditForm.status" style="width:100%">
            <el-option v-for="s in Object.keys(SUB_TRANSITIONS)" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="subEditForm.priority">
            <el-radio-button value="P0" label="P0" />
            <el-radio-button value="P1" label="P1" />
            <el-radio-button value="P2" label="P2" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="截止"><el-input v-model="subEditForm.due_date" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="subEditForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subEditDlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSubEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { milestonesApi, workpackagesApi, subtasksApi, wbsApi } from '../api'
import RefLink from '../components/RefLink.vue'

const loading = ref(false)
const saving = ref(false)
const tree = ref({ milestones: [], orphan_work_packages: [], unclassified_tasks: [] })
const milestones = ref([])

// 子任务状态机（与任务卡一致）
const SUB_TRANSITIONS = {
  待办: ['进行中', '阻塞', '取消'],
  进行中: ['待评审', '阻塞', '取消'],
  待评审: ['通过', '返工', '阻塞'],
  通过: ['关闭'],
  返工: ['进行中', '阻塞', '取消'],
  阻塞: ['进行中', '取消'],
  关闭: [],
  取消: []
}
const MS_STATUS = ['进行中', '已完成', '已归档']

function subTargets(s) { return SUB_TRANSITIONS[s] || [] }
function statusType(s) {
  return { 进行中: 'primary', 待评审: 'warning', 通过: 'success', 返工: 'danger', 关闭: 'success', 阻塞: 'danger', 取消: 'info', 已完成: 'success', 已归档: 'info' }[s] || 'info'
}

// ---------------- 数据加载 ----------------
async function load() {
  loading.value = true
  try {
    const [t, ms] = await Promise.all([wbsApi.tree(), milestonesApi.list()])
    tree.value = t
    milestones.value = ms
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// ---------------- 里程碑 ----------------
const msDlg = ref(false)
const msForm = ref(blankMs())
function blankMs() { return { id: '', code: '', name: '', status: '进行中', owner: '', description: '' } }
function openMilestone() { msForm.value = blankMs(); msDlg.value = true }
function editMilestone(m) { msForm.value = { ...m }; msDlg.value = true }
async function saveMilestone() {
  if (!msForm.value.code || !msForm.value.name) return ElMessage.warning('请填写编号与名称')
  saving.value = true
  try {
    if (msForm.value.id) await milestonesApi.update(msForm.value.id, msForm.value)
    else await milestonesApi.create(msForm.value)
    ElMessage.success('已保存')
    msDlg.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function removeMilestone(m) {
  try { await milestonesApi.remove(m.id); ElMessage.success('已删除'); await load() }
  catch (e) { ElMessage.error(e.message) }
}

// ---------------- 工作包 ----------------
const wpDlg = ref(false)
const wpForm = ref(blankWp())
function blankWp() { return { id: '', milestone_id: '', code: '', name: '', status: '进行中', owner: '', description: '' } }
function openWorkPackage(m) { wpForm.value = blankWp(); wpForm.value.milestone_id = m.id; wpDlg.value = true }
function editWorkPackage(wp) { wpForm.value = { ...wp }; wpDlg.value = true }
async function saveWorkPackage() {
  if (!wpForm.value.milestone_id || !wpForm.value.code || !wpForm.value.name) return ElMessage.warning('请选择里程碑并填写编号与名称')
  saving.value = true
  try {
    if (wpForm.value.id) await workpackagesApi.update(wpForm.value.id, wpForm.value)
    else await workpackagesApi.create(wpForm.value)
    ElMessage.success('已保存')
    wpDlg.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function removeWorkPackage(wp) {
  try { await workpackagesApi.remove(wp.id); ElMessage.success('已删除'); await load() }
  catch (e) { ElMessage.error(e.message) }
}

// ---------------- 子任务 ----------------
const subDlg = ref(false)
const subEditDlg = ref(false)
const subTaskParentId = ref('')
const subTaskParentCode = ref('')
const subForm = ref(blankSub())
const subEditForm = ref(blankSub())
function blankSub() { return { id: '', code: '', title: '', assignee: '', priority: 'P2', status: '待办', due_date: '', description: '' } }
function openSubTask(t) { subTaskParentId.value = t.id; subTaskParentCode.value = t.code; subForm.value = blankSub(); subDlg.value = true }
function openSubEdit(s) {
  subEditForm.value = { id: s.id, code: s.code, title: s.title, assignee: s.assignee || '',
    priority: s.priority || 'P2', status: s.status || '待办', due_date: s.due_date || '', description: s.description || '' }
  subEditDlg.value = true
}
async function saveSubTask() {
  if (!subForm.value.code || !subForm.value.title) return ElMessage.warning('请填写编号与标题')
  saving.value = true
  try {
    await subtasksApi.create({ ...subForm.value, task_id: subTaskParentId.value })
    ElMessage.success('子任务已创建')
    subDlg.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function saveSubEdit() {
  if (!subEditForm.value.title) return ElMessage.warning('请填写标题')
  saving.value = true
  try {
    const { id, code, ...payload } = subEditForm.value
    await subtasksApi.update(id, payload)
    ElMessage.success('子任务已更新')
    subEditDlg.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function transitionSub(s) {
  if (!s._target) return ElMessage.warning('请选择目标状态')
  try {
    await subtasksApi.transition(s.id, s._target)
    ElMessage.success(`${s.code}：${s.status} → ${s._target}`)
    await load()
  } catch (e) { ElMessage.error(e.message) }
}
async function removeSub(s) {
  try { await subtasksApi.remove(s.id); ElMessage.success('已删除'); await load() }
  catch (e) { ElMessage.error(e.message) }
}

onMounted(load)
</script>

<style scoped>
.pm-header-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.wbs-ms { margin-bottom: 14px; }
.wbs-card { margin-bottom: 4px; }
.wbs-card-head, .wbs-wp-head, .wbs-task-head, .wbs-sub {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.wbs-card-head { font-size: 14px; }
.wbs-wp { border-left: 3px solid var(--el-color-primary, #409eff); padding: 8px 0 8px 12px; margin: 8px 0; }
.wbs-wp-head { font-weight: 600; }
.wbs-task { border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 8px 10px; margin: 8px 0; }
.wbs-task-head { font-size: 13px; }
.wbs-subs { margin-top: 6px; padding-left: 14px; border-left: 2px dashed var(--el-border-color); }
.wbs-sub { padding: 4px 0; font-size: 12px; }
.wbs-code { font-family: monospace; background: var(--el-fill-color-light); padding: 0 6px; border-radius: 4px; }
.wbs-sub-title { color: var(--el-text-color-regular); }
.wbs-muted { color: var(--el-text-color-secondary); font-size: 12px; }
.wbs-actions { margin-left: auto; display: flex; gap: 6px; align-items: center; }
</style>

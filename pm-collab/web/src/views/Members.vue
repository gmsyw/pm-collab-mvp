<template>
  <div>
    <div class="pm-card">
      <h3>成员名册
        <el-button size="small" type="primary" style="float:right" @click="openCreate">+ 成员</el-button>
      </h3>
      <p class="pm-muted" style="margin:0 0 10px">每个项目独立管理自身名册副本（新建项目自动从默认模板克隆，可自由调整且不影响其他项目）。人/AI 同表建档。</p>
      <el-table :data="members" size="small" border max-height="520">
        <el-table-column prop="code" label="编号" width="110" />
        <el-table-column prop="name" label="姓名/实例" min-width="160" />
        <el-table-column prop="member_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag :type="row.member_type === 'AI' ? 'warning' : 'info'">{{ row.member_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column prop="reports_to" label="汇报对象" width="140" />
        <el-table-column prop="username" label="登录账号" width="140" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dlg" :title="form.id ? '编辑成员' : '新建成员'" width="520px">
      <el-form :model="form" label-width="96px" size="small">
        <el-form-item label="编号"><el-input v-model="form.code" :disabled="!!form.id" placeholder="M-001" /></el-form-item>
        <el-form-item label="姓名/实例"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.member_type">
            <el-radio-button value="人类" label="人类" />
            <el-radio-button value="AI" label="AI" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option label="在岗" value="在岗" />
            <el-option label="停用" value="停用" />
          </el-select>
        </el-form-item>
        <el-form-item label="汇报对象"><el-input v-model="form.reports_to" placeholder="成员编号" /></el-form-item>
        <el-form-item label="登录账号"><el-input v-model="form.username" placeholder="可选；留空则不可登录" /></el-form-item>
        <el-form-item label="登录口令">
          <el-input v-model="form.password" type="password" show-password placeholder="可选；编辑时留空表示不变更" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { membersApi } from '../api'

const members = ref([])
const dlg = ref(false)
const saving = ref(false)
const form = ref(blank())

function blank() {
  return { id: '', code: '', name: '', member_type: '人类', status: '在岗', reports_to: '', username: '', password: '' }
}

async function load() {
  try { members.value = await membersApi.list() }
  catch (e) { ElMessage.error(e.message) }
}

function openCreate() { form.value = blank(); dlg.value = true }
function openEdit(row) {
  form.value = { id: row.id, code: row.code, name: row.name, member_type: row.member_type,
    status: row.status, reports_to: row.reports_to || '', username: row.username || '', password: '' }
  dlg.value = true
}

async function save() {
  if (!form.value.code || !form.value.name) return ElMessage.warning('请填写编号与姓名')
  saving.value = true
  try {
    const payload = { ...form.value }
    delete payload.id
    if (!payload.password) delete payload.password  // 编辑时留空不改口令
    if (form.value.id) await membersApi.update(form.value.id, payload)
    else await membersApi.create(payload)
    ElMessage.success('已保存')
    dlg.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除成员 ${row.code} ${row.name}？`, '删除确认', { type: 'warning' })
    await membersApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) { if (e && e.message) ElMessage.error(e.message) }
}

onMounted(load)
</script>

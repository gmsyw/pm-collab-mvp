<template>
  <div>
    <div class="pm-card">
      <h3>角色卡（8 字段）
        <el-button size="small" type="primary" style="float:right" @click="openCreate">+ 角色卡</el-button>
      </h3>
      <p class="pm-muted" style="margin:0 0 10px">每个项目独立管理自身角色卡副本（新建项目自动从默认模板克隆，可自由调整且不影响其他项目）。权限等级 L1–L4，AI 不代签门禁。</p>
      <el-table :data="roles" size="small" border max-height="520">
        <el-table-column prop="code" label="编号" width="110" />
        <el-table-column prop="role_type" label="类型" width="90" />
        <el-table-column prop="duty" label="职责" min-width="200" show-overflow-tooltip />
        <el-table-column prop="permission_level" label="权限等级" width="100">
          <template #default="{ row }">
            <el-tag :type="row.permission_level === 'L4' ? 'danger' : row.permission_level === 'L3' ? 'warning' : 'info'">{{ row.permission_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="data_boundary" label="数据与工具边界" min-width="160" show-overflow-tooltip />
        <el-table-column prop="reports_to" label="汇报对象" width="120" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dlg" :title="form.id ? '编辑角色卡' : '新建角色卡'" width="560px">
      <el-form :model="form" label-width="120px" size="small">
        <el-form-item label="编号"><el-input v-model="form.code" :disabled="!!form.id" placeholder="R-AI-01" /></el-form-item>
        <el-form-item label="角色类型">
          <el-radio-group v-model="form.role_type">
            <el-radio-button value="人类角色" label="人类角色" />
            <el-radio-button value="AI角色" label="AI角色" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="职责"><el-input v-model="form.duty" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="负面清单"><el-input v-model="form.negative_list" type="textarea" :rows="2" placeholder="禁止事项" /></el-form-item>
        <el-form-item label="权限等级（L1–L4）">
          <el-select v-model="form.permission_level" style="width:100%">
            <el-option label="L1" value="L1" />
            <el-option label="L2" value="L2" />
            <el-option label="L3" value="L3" />
            <el-option label="L4" value="L4" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据与工具边界"><el-input v-model="form.data_boundary" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="汇报对象"><el-input v-model="form.reports_to" placeholder="角色编号" /></el-form-item>
        <el-form-item label="降级预案"><el-input v-model="form.downgrade_plan" type="textarea" :rows="2" /></el-form-item>
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
import { rolesApi } from '../api'

const roles = ref([])
const dlg = ref(false)
const saving = ref(false)
const form = ref(blank())

function blank() {
  return { id: '', code: '', role_type: 'AI角色', duty: '', negative_list: '', permission_level: 'L2',
    data_boundary: '', reports_to: '', downgrade_plan: '' }
}

async function load() {
  try { roles.value = await rolesApi.list() }
  catch (e) { ElMessage.error(e.message) }
}

function openCreate() { form.value = blank(); dlg.value = true }
function openEdit(row) {
  form.value = { id: row.id, code: row.code, role_type: row.role_type, duty: row.duty,
    negative_list: row.negative_list || '', permission_level: row.permission_level,
    data_boundary: row.data_boundary || '', reports_to: row.reports_to || '', downgrade_plan: row.downgrade_plan || '' }
  dlg.value = true
}

async function save() {
  if (!form.value.code || !form.value.duty) return ElMessage.warning('请填写编号与职责')
  saving.value = true
  try {
    const payload = { ...form.value }
    delete payload.id
    if (form.value.id) await rolesApi.update(form.value.id, payload)
    else await rolesApi.create(payload)
    ElMessage.success('已保存')
    dlg.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除角色卡 ${row.code}？`, '删除确认', { type: 'warning' })
    await rolesApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) { if (e && e.message) ElMessage.error(e.message) }
}

onMounted(load)
</script>

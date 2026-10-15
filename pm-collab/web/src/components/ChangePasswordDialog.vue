<template>
  <el-dialog v-model="visible" title="修改密码" width="420px" @closed="reset">
    <el-form label-width="96px" :model="form">
      <el-form-item label="原密码">
        <el-input v-model="form.old_password" type="password" show-password autocomplete="current-password" />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="form.new_password" type="password" show-password placeholder="至少 8 位"
                  autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="form.confirm" type="password" show-password autocomplete="new-password" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { authApi } from '../api'

const visible = defineModel('visible', { default: false })
const form = reactive({ old_password: '', new_password: '', confirm: '' })
const loading = ref(false)

function reset() {
  form.old_password = ''
  form.new_password = ''
  form.confirm = ''
}

async function submit() {
  if (form.new_password.length < 8) return ElMessage.warning('新密码至少 8 位')
  if (form.new_password !== form.confirm) return ElMessage.warning('两次输入不一致')
  loading.value = true
  try {
    await authApi.changePassword(form.old_password, form.new_password)
    ElMessage.success('密码已更新，请重新登录')
    // 旧 token 已被后端吊销，强制回到登录页（OSS-02）
    localStorage.removeItem('pm_token')
    localStorage.removeItem('pm_user')
    window.location.href = '/'
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>

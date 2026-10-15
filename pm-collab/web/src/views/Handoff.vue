<template>
  <div>
    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>交接区文件（消息总线）
          <el-button size="small" style="float:right" @click="sync('both')">双向同步对账</el-button>
        </h3>
        <el-collapse>
          <el-collapse-item v-for="(files, zone) in zones" :key="zone" :title="`${zone}（${files.length}）`">
            <p v-if="!files.length" class="pm-muted">空目录</p>
            <p v-for="f in files" :key="f" class="pm-mono pm-link" @click="previewZone(zone, f)">{{ zone }}/{{ f }}</p>
          </el-collapse-item>
        </el-collapse>
      </div>

      <div class="pm-card pm-flex1">
        <h3>卡点队列（WebSocket 实时）
          <el-tag size="small" type="info">{{ wsConnected ? '实时连接中' : '未连接' }}</el-tag>
          <el-button size="small" type="primary" style="float:right" @click="openCheckpoint">+ 卡点</el-button>
        </h3>
        <el-table :data="checkpoints" size="small" max-height="360" border>
          <el-table-column prop="occurred_at" label="发生时间" width="150" />
          <el-table-column prop="category" label="类别" width="100" />
          <el-table-column prop="content" label="卡点内容" min-width="200" />
          <el-table-column prop="human_action" label="人类需要做什么" min-width="220" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button v-if="row.status === '待处理'" size="small" type="success" plain @click="handle(row)">标记处理</el-button>
              <el-tag v-else size="small">已处理</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="pm-card">
      <h3>交接单（待投喂 → 已投喂 → 已回收 → 已闭环）
        <el-button size="small" type="primary" style="float:right" @click="openOrder">+ 新建交接单</el-button>
      </h3>
      <el-button size="small" @click="sync('from')">文件→库</el-button>
      <el-button size="small" @click="sync('to')">库→文件</el-button>
      <el-table :data="orders" size="small" border style="margin-top:10px">
        <el-table-column prop="code" label="编号" width="110" />
        <el-table-column prop="sender" label="发起方" width="120" />
        <el-table-column prop="receiver" label="接收方" width="150" />
        <el-table-column prop="zone" label="目录" width="90" />
        <el-table-column prop="task_code" label="关联任务" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === '已闭环' ? 'success' : row.status === '待投喂' ? 'info' : 'primary'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="载体路径" min-width="240" class-name="pm-mono">
          <template #default="{ row }">
            <span class="pm-link" @click="previewPath(row.payload_path, row.code)">{{ row.payload_path }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="next(row)">推进状态</el-button>
            <el-button size="small" @click="recycle(row)">回收</el-button>
            <el-button size="small" type="success" plain @click="close(row)">闭环</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新建交接单 -->
    <el-dialog v-model="orderDlg" title="新建交接单" width="480px">
      <el-form :model="orderForm" label-width="90px" size="small">
        <el-form-item label="编号"><el-input v-model="orderForm.code" placeholder="HO-001" /></el-form-item>
        <el-form-item label="发起方"><el-input v-model="orderForm.sender" placeholder="PM-AI" /></el-form-item>
        <el-form-item label="接收方"><el-input v-model="orderForm.receiver" placeholder="目标角色/AI 实例" /></el-form-item>
        <el-form-item label="交接目录">
          <el-select v-model="orderForm.zone" style="width:100%">
            <el-option v-for="z in zonesList" :key="z" :label="z" :value="z" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联任务"><el-input v-model="orderForm.task_code" placeholder="如 T04（可选）" /></el-form-item>
        <el-form-item label="载体路径"><el-input v-model="orderForm.payload_path" placeholder="如 data/.../T04_派单_xxx_V1.md" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="orderDlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveOrder">创建</el-button>
      </template>
    </el-dialog>

    <!-- 新建卡点 -->
    <el-dialog v-model="cpDlg" title="新建卡点信号" width="520px">
      <el-form :model="cpForm" label-width="110px" size="small">
        <el-form-item label="触发者"><el-input v-model="cpForm.trigger" placeholder="PM-AI / 人类 / 系统" /></el-form-item>
        <el-form-item label="卡点内容"><el-input v-model="cpForm.content" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="人类需要做什么"><el-input v-model="cpForm.human_action" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="类别">
          <el-select v-model="cpForm.category" style="width:100%">
            <el-option label="搬运请求" value="搬运请求" />
            <el-option label="决策请求" value="决策请求" />
            <el-option label="审批请求" value="审批请求" />
            <el-option label="签字请求" value="签字请求" />
            <el-option label="越权失效" value="越权失效" />
            <el-option label="告警" value="告警" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联任务"><el-input v-model="cpForm.task_code" placeholder="如 T04（可选）" /></el-form-item>
        <el-form-item label="期望时限"><el-input v-model="cpForm.expect_by" placeholder="如 当日 / 2026-10-10" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cpDlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCheckpoint">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { checkpointsApi, handoffApi } from '../api'
import { openFilePreview } from '../composables/useFilePreview'

const zones = ref({})
const orders = ref([])
const checkpoints = ref([])
const wsConnected = ref(false)
const saving = ref(false)
const orderDlg = ref(false)
const cpDlg = ref(false)
const orderForm = ref({ code: '', sender: 'PM-AI', receiver: '', zone: '派单', task_code: '', payload_path: '' })
const cpForm = ref({ trigger: 'PM-AI', content: '', human_action: '', category: '搬运请求', task_code: '', expect_by: '' })
const zonesList = ['派单', '回执', '完成', '评审输入', '评审输出', '卡点']
let ws = null

const NEXT_STATUS = { 待投喂: '已投喂', 已投喂: '已回收', 已回收: '已闭环', 已闭环: null }

function previewPath(path, name) {
  if (path) openFilePreview(path, name)
}
// 交接区文件相对路径（data/交接区/<zone>/<file>），后端会兼容 projects/<项目>/ 子目录布局
function previewZone(zone, f) {
  openFilePreview(`交接区/${zone}/${f}`, `${zone}/${f}`)
}

function openOrder() { orderForm.value = { code: '', sender: 'PM-AI', receiver: '', zone: '派单', task_code: '', payload_path: '' }; orderDlg.value = true }
function openCheckpoint() { cpForm.value = { trigger: 'PM-AI', content: '', human_action: '', category: '搬运请求', task_code: '', expect_by: '' }; cpDlg.value = true }

async function saveOrder() {
  if (!orderForm.value.code) return ElMessage.warning('请填写交接单编号')
  saving.value = true
  try {
    await handoffApi.create(orderForm.value)
    ElMessage.success('交接单已创建')
    orderDlg.value = false
    load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function saveCheckpoint() {
  if (!cpForm.value.content) return ElMessage.warning('请填写卡点内容')
  saving.value = true
  try {
    await checkpointsApi.create(cpForm.value)
    ElMessage.success('卡点已创建')
    cpDlg.value = false
    load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function load() {
  try {
    zones.value = (await handoffApi.zones()).files
    orders.value = await handoffApi.list()
    checkpoints.value = await checkpointsApi.list({ status: '待处理' })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function sync(direction) {
  try {
    const res = await handoffApi.sync(direction)
    ElMessage.success(`同步完成：${JSON.stringify(res)}`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function next(row) {
  const target = NEXT_STATUS[row.status]
  if (!target) return ElMessage.info('已闭环，无需推进')
  await run(() => handoffApi.transition(row.id, target), `${row.code} → ${target}`)
}

async function recycle(row) {
  await run(() => handoffApi.recycle(row.id), `${row.code} 已回收并登记台账`)
}

async function close(row) {
  await run(() => handoffApi.close(row.id), `${row.code} 已闭环`)
}

async function handle(row) {
  await run(() => checkpointsApi.handle(row.id, 'H 已在队列确认处理'), '卡点已标记处理')
}

async function run(fn, okMsg) {
  try {
    await fn()
    ElMessage.success(okMsg)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function connectWs() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${window.location.host}/ws`)
  ws.onopen = () => { wsConnected.value = true }
  ws.onclose = () => { wsConnected.value = false }
  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      if (msg.event === 'checkpoint') {
        ElMessage({ message: `新卡点：${msg.data.content}`, type: 'warning', duration: 4000 })
        load()
      }
    } catch (e) {
      /* ignore */
    }
  }
}

onMounted(() => { load(); connectWs() })
onUnmounted(() => { if (ws) ws.close() })
</script>

<style scoped>
.pm-link { cursor: pointer; color: var(--el-color-primary); word-break: break-all; }
.pm-link:hover { text-decoration: underline; }
</style>

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
            <p v-for="f in files" :key="f" class="pm-mono">{{ zone }}/{{ f }}</p>
          </el-collapse-item>
        </el-collapse>
      </div>

      <div class="pm-card pm-flex1">
        <h3>卡点队列（WebSocket 实时）
          <el-tag size="small" type="info">{{ wsConnected ? '实时连接中' : '未连接' }}</el-tag>
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
      <h3>交接单（待投喂 → 已投喂 → 已回收 → 已闭环）</h3>
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
        <el-table-column prop="payload_path" label="载体路径" min-width="240" class-name="pm-mono" />
        <el-table-column label="操作" width="210">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="next(row)">推进状态</el-button>
            <el-button size="small" @click="recycle(row)">回收</el-button>
            <el-button size="small" type="success" plain @click="close(row)">闭环</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { checkpointsApi, handoffApi } from '../api'

const zones = ref({})
const orders = ref([])
const checkpoints = ref([])
const wsConnected = ref(false)
let ws = null

const NEXT_STATUS = { 待投喂: '已投喂', 已投喂: '已回收', 已回收: '已闭环', 已闭环: null }

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

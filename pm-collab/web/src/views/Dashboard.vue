<template>
  <div>
    <div class="pm-card">
      <h3>里程碑进度 · {{ checklist.stage || '—' }}</h3>
      <div class="pm-row">
        <div class="pm-stat pm-flex1"><div class="num">{{ metrics.task_total || 0 }}</div><div class="lbl">任务总数</div></div>
        <div class="pm-stat pm-flex1"><div class="num">{{ metrics.task_closed || 0 }}</div><div class="lbl">已完成</div></div>
        <div class="pm-stat pm-flex1"><div class="num">{{ metrics.overdue_count || 0 }}</div><div class="lbl">逾期任务</div></div>
        <div class="pm-stat pm-flex1"><div class="num">{{ metrics.blocked_count || 0 }}</div><div class="lbl">阻塞任务</div></div>
        <div class="pm-stat pm-flex1"><div class="num">{{ metrics.open_checkpoints || 0 }}</div><div class="lbl">待处理卡点</div></div>
      </div>
    </div>

    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>任务状态分布</h3>
        <div ref="statusChart" class="pm-chart"></div>
      </div>
      <div class="pm-card pm-flex1">
        <h3>四指标（需求书 §11.1）</h3>
        <div ref="metricChart" class="pm-chart"></div>
      </div>
    </div>

    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>8 阶段流水线</h3>
        <el-steps :active="currentStageIndex" finish-status="success" align-center>
          <el-step v-for="s in stages" :key="s.key" :title="s.key" :description="s.name" />
        </el-steps>
      </div>
    </div>

    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>门禁签字状态</h3>
        <el-table :data="checklist.gates || []" size="small">
          <el-table-column prop="gate_no" label="门禁" width="70" />
          <el-table-column prop="gate_name" label="名称" width="110" />
          <el-table-column prop="stage" label="阶段" width="70" />
          <el-table-column label="决策" width="90">
            <template #default="{ row }">
              <el-tag :type="row.decision === '通过' ? 'success' : 'info'">{{ row.decision }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="signed_by" label="签字人" width="90" />
          <el-table-column prop="opinion" label="意见" />
        </el-table>
      </div>
      <div class="pm-card pm-flex1">
        <h3>昨日摘要</h3>
        <pre v-if="latest.summary_text" class="pm-mono" style="max-height:280px;overflow:auto">{{ latest.summary_text }}</pre>
        <el-empty v-else description="尚无摘要，可在看板生成" />
        <el-button size="small" type="primary" style="margin-top:10px" @click="genDigest">生成每日摘要并推送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { processApi, reportApi, tasksApi } from '../api'

const metrics = ref({})
const checklist = ref({})
const latest = ref({})
const tasks = ref([])
const statusChart = ref(null)
const metricChart = ref(null)

const stages = [
  { key: 'S1', name: '需求录入' }, { key: 'S2', name: '设计' }, { key: 'S3', name: '设计评审' },
  { key: 'S4', name: '开发' }, { key: 'S5', name: '代码评审' }, { key: 'S6', name: '测试' },
  { key: 'S7', name: '验收' }, { key: 'S8', name: '归档' }
]

const currentStageIndex = computed(() => {
  const idx = stages.findIndex((s) => s.key === (checklist.value.stage || 'S1'))
  return idx < 0 ? 0 : idx
})

function renderStatusChart() {
  const counts = {}
  tasks.value.forEach((t) => { counts[t.status] = (counts[t.status] || 0) + 1 })
  const chart = echarts.init(statusChart.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: Object.keys(counts) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: Object.values(counts), itemStyle: { color: '#2f54eb', borderRadius: [4, 4, 0, 0] } }]
  })
}

function renderMetricChart() {
  const m = metrics.value
  const chart = echarts.init(metricChart.value)
  chart.setOption({
    tooltip: { formatter: '{b}: {c}%' },
    radar: {
      indicator: [
        { name: '按期率', max: 100 }, { name: '返工率', max: 100 },
        { name: 'AI采纳率', max: 100 }, { name: '评审关闭率', max: 100 }
      ]
    },
    series: [{
      type: 'radar',
      data: [{ value: [m.on_time_rate || 0, m.rework_rate || 0, m.ai_adoption_rate || 0, m.review_close_rate || 0], name: '当前' }]
    }]
  })
}

async function load() {
  try {
    metrics.value = await reportApi.metrics()
    checklist.value = await processApi.checklist()
    latest.value = await reportApi.latest()
    tasks.value = await tasksApi.list()
    await nextTick()
    renderStatusChart()
    renderMetricChart()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function genDigest() {
  try {
    await reportApi.digest(true)
    ElMessage.success('每日摘要已生成并推送')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

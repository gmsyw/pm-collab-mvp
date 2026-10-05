<template>
  <div>
    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>阶段推进（8 阶段不可跳过）</h3>
        <p>当前阶段：<b>{{ instance.stage }} {{ instance.stage_name }}</b>
          · 下一阶段：{{ instance.next_stage }} · 必需门禁：{{ instance.required_gate || '无' }} · 测试通过：{{ instance.test_passed ? '是' : '否' }}</p>
        <el-button size="small" type="primary" plain @click="advance">推进到 {{ instance.next_stage }}</el-button>
        <el-button size="small" @click="markTest(true)">登记测试通过</el-button>
      </div>
      <div class="pm-card pm-flex1">
        <h3>阶段准出自检</h3>
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="任务总数">{{ checklist.task_total }}</el-descriptions-item>
          <el-descriptions-item label="已关闭">{{ checklist.task_closed }}</el-descriptions-item>
          <el-descriptions-item label="文档条目">{{ checklist.doc_total }}</el-descriptions-item>
          <el-descriptions-item label="已基线文档">{{ checklist.doc_baselined }}</el-descriptions-item>
          <el-descriptions-item label="测试通过">{{ checklist.test_passed ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="当前阶段">{{ checklist.stage }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <div class="pm-card">
      <h3>4 门禁签字台（签字权在人类，AI 不代签）</h3>
      <el-table :data="gates" size="small" border>
        <el-table-column prop="gate_no" label="门禁" width="70" />
        <el-table-column prop="gate_name" label="名称" width="120" />
        <el-table-column prop="stage" label="阶段" width="70" />
        <el-table-column label="决策" width="90">
          <template #default="{ row }">
            <el-tag :type="row.decision === '通过' ? 'success' : 'info'">{{ row.decision }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="signed_by" label="签字人" width="90" />
        <el-table-column prop="opinion" label="意见" min-width="160" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" type="success" plain @click="sign(row, '通过')">签字通过</el-button>
            <el-button size="small" type="danger" plain @click="sign(row, '驳回')">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pm-card">
      <h3>追加式日志（只增不改、不可删除）</h3>
      <el-table :data="logs" size="small" border max-height="360">
        <el-table-column prop="occurred_at" label="时间" width="170" />
        <el-table-column prop="actor" label="执行者" width="150" />
        <el-table-column prop="action" label="动作" width="160" />
        <el-table-column prop="change" label="变更" min-width="220" />
        <el-table-column prop="next_step" label="下一步" width="160" />
        <el-table-column prop="open_issue" label="遗留问题" width="160" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { processApi, reportApi } from '../api'

const instance = ref({})
const gates = ref([])
const checklist = ref({})
const logs = ref([])

async function load() {
  try {
    instance.value = await processApi.instance()
    gates.value = await processApi.gates()
    checklist.value = await processApi.checklist()
    logs.value = (await reportApi.logs(200)).items
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function advance() {
  try {
    const res = await processApi.advance(instance.value.next_stage)
    ElMessage.success(`已进入 ${res.stage} ${res.stage_name}`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function markTest(passed) {
  try {
    const { value } = await ElMessageBox.prompt('测试报告路径', '登记测试结果', { inputValue: 'data/02_交付物/04_测试/' })
    await processApi.testResult({ passed, report_path: value })
    ElMessage.success(`已登记测试结果：${passed ? '通过' : '未通过'}`)
    load()
  } catch (e) {
    if (e && e.message) ElMessage.error(e.message)
  }
}

async function sign(row, decision) {
  try {
    if (decision === '通过') {
      const { value } = await ElMessageBox.prompt('评审意见（可留空）', `签署门禁${row.gate_no} ${row.gate_name}`, { inputValue: '' })
      await processApi.sign({ gate_no: row.gate_no, decision: '通过', signed_by: 'H', opinion: value || '' })
    } else {
      const { value } = await ElMessageBox.prompt('驳回理由', `驳回门禁${row.gate_no}`, { inputValue: '' })
      await processApi.sign({ gate_no: row.gate_no, decision: '驳回', signed_by: 'H', opinion: value || '' })
    }
    ElMessage.success('已记录')
    load()
  } catch (e) {
    if (e && e.message) ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

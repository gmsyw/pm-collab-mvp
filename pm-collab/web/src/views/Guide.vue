<template>
  <div>
    <!-- 1. 进度显示：8 阶段流水线 -->
    <div class="pm-card">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <h3 style="margin:0">项目进程</h3>
        <el-tag type="primary" effect="dark">当前 {{ g.stage }} {{ g.stage_name }}</el-tag>
        <el-tag v-if="g.open_checkpoints" type="danger">{{ g.open_checkpoints }} 个待处理卡点</el-tag>
        <el-tag v-else type="success" effect="plain">无待处理卡点</el-tag>
        <div style="flex:1"></div>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
      <el-progress :percentage="g.progress?.percent || 0" :stroke-width="14" style="margin:14px 0 6px" />
      <el-steps :active="g.progress?.index || 0" finish-status="success" align-center>
        <el-step v-for="s in g.stages || []" :key="s.key" :title="s.key" :description="s.name" />
      </el-steps>
    </div>

    <!-- 2. 下一步该做什么（操作指导核心） -->
    <div class="pm-card">
      <h3>下一步</h3>
      <el-alert :title="g.next_action?.label || '加载中…'" type="warning" show-icon :closable="false" />
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
        <el-button type="primary" @click="doNext">{{ g.next_action?.label }}</el-button>
        <el-button @click="go('/governance')">流程与门禁</el-button>
        <el-button @click="go('/handoff')">交接区与卡点</el-button>
        <el-button v-if="g.stage === 'S4'" @click="go('/members')">建 AI 成员</el-button>
        <el-button v-if="g.stage === 'S1'" @click="go('/docs')">登记需求基线</el-button>
      </div>
    </div>

    <!-- 3. 本阶段：目标 · 人机分工 · 准出条件 -->
    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>本阶段目标</h3>
        <p style="font-size:15px;margin:6px 0">{{ g.goal }}</p>

        <h3 style="margin-top:16px">准出条件</h3>
        <ul style="padding-left:20px;margin:6px 0">
          <li v-for="(c, i) in g.exit_criteria || []" :key="i">{{ c }}</li>
        </ul>

        <div style="margin-top:12px">
          <el-tag v-if="b.need_gate" :type="b.gate_signed ? 'success' : 'warning'">
            门禁{{ b.need_gate }}《{{ b.gate_name }}》{{ b.gate_signed ? '已签字' : '未签字' }}
          </el-tag>
          <el-tag v-if="b.need_test" :type="b.test_passed ? 'success' : 'warning'" style="margin-left:8px">
            测试{{ b.test_passed ? '已通过' : '未通过' }}
          </el-tag>
        </div>
      </div>

      <div class="pm-card pm-flex1">
        <h3>人类该做什么</h3>
        <ol style="padding-left:20px;margin:6px 0">
          <li v-for="(a, i) in g.human_actions || []" :key="'h' + i" style="margin-bottom:4px">{{ a }}</li>
        </ol>
        <h3 style="margin-top:16px">AI 该做什么</h3>
        <ol style="padding-left:20px;margin:6px 0">
          <li v-for="(a, i) in g.ai_actions || []" :key="'a' + i" style="margin-bottom:4px">{{ a }}</li>
        </ol>
      </div>
    </div>

    <!-- 4. 项目准备度（初始化进度） -->
    <div class="pm-card">
      <h3>项目准备度</h3>
      <el-descriptions :column="4" size="small" border>
        <el-descriptions-item label="成员">{{ r.members ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="AI 成员">{{ r.ai_members ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="角色卡">{{ r.roles ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="里程碑">{{ r.milestones ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="任务卡">{{ r.tasks ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="已关闭任务">{{ r.closed_tasks ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="文档条目">{{ r.docs ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="已基线文档">{{ r.baselined_docs ?? 0 }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="g.stage === 'S4' && !r.ai_members"
        title="当前已进入开发阶段但尚无 AI 成员：请先在「成员名册」建 AI 成员并在「角色卡」定义其职责，再投喂任务。"
        type="warning" show-icon :closable="false" style="margin-top:12px"
      />
      <el-alert
        v-if="g.stage === 'S1' && !r.docs"
        title="新项目第一步：先在「文档与版本」登记需求基线文档（命名：项目-需求基线-名称-V1.0.0.md），再组织需求评审并签署门禁①。"
        type="info" show-icon :closable="false" style="margin-top:12px"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { processApi } from '../api'

const router = useRouter()
const g = ref({})
const b = computed(() => g.value.blockers || {})
const r = computed(() => g.value.readiness || {})

async function load() {
  try {
    g.value = await processApi.guide()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function doNext() {
  const na = g.value.next_action || {}
  try {
    if (na.type === 'advance') {
      const res = await processApi.advance(na.target)
      ElMessage.success(`已进入 ${res.stage} ${res.stage_name}`)
    } else if (na.type === 'sign_gate') {
      const { value } = await ElMessageBox.prompt(
        '评审意见（可留空）', `人类签署门禁${na.gate_no}`, { inputValue: '' }
      )
      await processApi.sign({
        gate_no: na.gate_no, decision: '通过', signed_by: 'H', opinion: value || ''
      })
      ElMessage.success('已签字通过')
    } else if (na.type === 'record_test') {
      const { value } = await ElMessageBox.prompt(
        '测试报告路径', '登记测试结果', { inputValue: 'data/02_交付物/04_测试/' }
      )
      await processApi.testResult({ passed: true, report_path: value })
      ElMessage.success('已登记测试通过')
    } else {
      router.push(na.to || '/docs')
      return
    }
    load()
  } catch (e) {
    if (e && e.message) ElMessage.error(e.message)
  }
}

function go(path) {
  router.push(path)
}

onMounted(load)
</script>

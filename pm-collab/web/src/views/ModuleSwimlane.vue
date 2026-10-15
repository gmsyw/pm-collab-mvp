<template>
  <div>
    <div class="pm-card">
      <h3>模块泳道视图（V0.4）</h3>
      <p class="pm-muted">
        按 module_tag（S1~S8）聚合：模块下所有任务卡的交接单合并为一条泳道，
        一眼看到走到哪一步、是否被返工卡住。
      </p>
      <el-table :data="lanes" size="small" border>
        <el-table-column prop="module_tag" label="模块" width="110" />
        <el-table-column label="当前阶段" width="120">
          <template #default="{ row }">
            <el-tag :type="row.blocked ? 'danger' : 'success'">{{ row.stage }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="count" label="卡片数" width="90" />
        <el-table-column label="阻塞" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.blocked" type="danger">{{ row.blocked }}</el-tag>
            <span v-else>0</span>
          </template>
        </el-table-column>
        <el-table-column prop="latest" label="最近事件" />
      </el-table>
      <el-empty
        v-if="!lanes.length"
        description="暂无带模块标签的任务（请在任务卡填写 module_tag，如 S1）"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { vizApi } from '../api'

const lanes = ref([])
onMounted(async () => {
  try {
    const res = await vizApi.swimlane()
    lanes.value = res.lanes || []
  } catch (e) {
    lanes.value = []
  }
})
</script>

<template>
  <div>
    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>五库与交接区托管</h3>
        <el-tree :data="tree" :props="{ label: 'label', children: 'children' }" default-expand-all />
        <p class="pm-muted" style="margin-top:10px">根目录：{{ root }}</p>
      </div>
      <div class="pm-card pm-flex1">
        <h3>登记文档条目</h3>
        <el-form :model="docForm" label-width="90px" size="small">
          <el-form-item label="唯一编号"><el-input v-model="docForm.doc_no" placeholder="DOC-001" /></el-form-item>
          <el-form-item label="所属库">
            <el-select v-model="docForm.library">
              <el-option v-for="l in libraries" :key="l" :label="l" :value="l" />
            </el-select>
          </el-form-item>
          <el-form-item label="类型"><el-input v-model="docForm.category" placeholder="设计文档" /></el-form-item>
          <el-form-item label="名称"><el-input v-model="docForm.name" /></el-form-item>
          <el-form-item label="版本"><el-input v-model="docForm.version" placeholder="V1.0" /></el-form-item>
          <el-form-item label="责任人"><el-input v-model="docForm.owner" /></el-form-item>
          <el-form-item label="文件路径">
            <el-input v-model="docForm.path" placeholder="data/02_交付物/02_设计/xxx-V1.0.md（须符合命名规范）" />
          </el-form-item>
        </el-form>
        <el-button size="small" type="primary" @click="addDoc">登记</el-button>
      </div>
    </div>

    <div class="pm-row">
      <div class="pm-card pm-flex1">
        <h3>文档条目（含哈希校验）</h3>
        <el-table :data="docs" size="small" border max-height="320">
          <el-table-column prop="doc_no" label="编号" width="110" />
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="version" label="版本" width="80" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="path" label="路径" min-width="240" class-name="pm-mono" />
          <el-table-column label="哈希" width="120">
            <template #default="{ row }">
              <el-button size="small" @click="verify(row)">校验</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="pm-card pm-flex1">
        <h3>版本台账（只增不改）</h3>
        <el-table :data="versions" size="small" border max-height="320">
          <el-table-column prop="version" label="版本" width="80" />
          <el-table-column prop="item_name" label="条目" min-width="180" />
          <el-table-column prop="released_at" label="日期" width="110" />
          <el-table-column prop="review_status" label="评审状态" width="100" />
          <el-table-column label="基线" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.is_baseline" size="small" type="success">已基线</el-tag>
              <el-button v-else size="small" plain @click="baseline(row)">基线化</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="pm-card">
      <h3>需求条目库（追溯矩阵左端）
        <el-checkbox v-model="onlyMvp" style="float:right" @change="loadRequirements">仅看 MVP 范围</el-checkbox>
      </h3>
      <el-table :data="requirements" size="small" border max-height="320">
        <el-table-column prop="code" label="编号" width="90" />
        <el-table-column prop="section" label="章节" width="60" />
        <el-table-column prop="content" label="需求内容" min-width="420" />
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column prop="review_status" label="评审状态" width="100" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { docsApi, rolesApi } from '../api'

const root = ref('')
const tree = ref([])
const docs = ref([])
const versions = ref([])
const requirements = ref([])
const onlyMvp = ref(false)
const libraries = ['01_项目库', '02_交付物', '03_日志', '04_模板', '05_版本库']
const docForm = ref({ doc_no: '', library: '02_交付物', category: '设计文档', name: '', version: 'V1.0', owner: 'H', path: '' })

const versionCount = computed(() => versions.value.length)

async function load() {
  try {
    const libs = await docsApi.libs()
    root.value = libs.data_dir
    tree.value = libs.libraries.map((l) => ({ label: `${l.name}（${l.file_count} 个文件）`, children: [] }))
    docs.value = await docsApi.list()
    versions.value = await docsApi.versions()
    await loadRequirements()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadRequirements() {
  requirements.value = await docsApi.requirements(onlyMvp.value ? { in_mvp: true } : {})
}

async function addDoc() {
  try {
    await docsApi.create(docForm.value)
    ElMessage.success('文档条目已登记')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function verify(row) {
  try {
    const res = await docsApi.verify(row.id)
    if (res.alert) ElMessage.warning(`${res.doc_no}：${res.status}`)
    else ElMessage.success(`${res.doc_no}：${res.status}`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function baseline(row) {
  try {
    await docsApi.baseline(row.id)
    ElMessage.success(`${row.version} 已基线化`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

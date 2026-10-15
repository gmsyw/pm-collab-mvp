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
          <el-table-column label="路径" min-width="240" class-name="pm-mono">
            <template #default="{ row }">
              <span class="pm-link" @click="previewDoc(row)">{{ row.path }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" @click="verify(row)">校验</el-button>
              <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="pm-card pm-flex1">
        <h3>版本台账（只增不改）
          <el-button size="small" type="primary" style="float:right" @click="openVersion">+ 登记版本</el-button>
        </h3>
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

    <!-- 编辑文档条目 -->
    <el-dialog v-model="editDlg" title="编辑文档条目" width="560px">
      <el-form :model="editForm" label-width="96px" size="small">
        <el-form-item label="编号"><el-input v-model="editForm.doc_no" disabled /></el-form-item>
        <el-form-item label="所属库">
          <el-select v-model="editForm.library" style="width:100%">
            <el-option v-for="l in libraries" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型"><el-input v-model="editForm.category" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="版本"><el-input v-model="editForm.version" /></el-form-item>
        <el-form-item label="责任人"><el-input v-model="editForm.owner" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width:100%">
            <el-option label="草稿" value="草稿" />
            <el-option label="待评审" value="待评审" />
            <el-option label="评审通过" value="评审通过" />
            <el-option label="归档" value="归档" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件路径"><el-input v-model="editForm.path" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDlg = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 登记版本台账 -->
    <el-dialog v-model="verDlg" title="登记版本台账" width="520px">
      <el-form :model="verForm" label-width="96px" size="small">
        <el-form-item label="版本"><el-input v-model="verForm.version" placeholder="V1.0" /></el-form-item>
        <el-form-item label="条目名称"><el-input v-model="verForm.item_name" placeholder="如 T04 交付物" /></el-form-item>
        <el-form-item label="类型"><el-input v-model="verForm.item_type" placeholder="交付物/文档" /></el-form-item>
        <el-form-item label="执行者"><el-input v-model="verForm.executor" /></el-form-item>
        <el-form-item label="变更摘要"><el-input v-model="verForm.change_summary" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="路径"><el-input v-model="verForm.path" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="verDlg = false">取消</el-button>
        <el-button type="primary" @click="saveVersion">登记</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { docsApi, rolesApi } from '../api'
import { openFilePreview } from '../composables/useFilePreview'

const root = ref('')
const tree = ref([])
const docs = ref([])
const versions = ref([])
const requirements = ref([])
const onlyMvp = ref(false)
const libraries = ['01_项目库', '02_交付物', '03_日志', '04_模板', '05_版本库']
const docForm = ref({ doc_no: '', library: '02_交付物', category: '设计文档', name: '', version: 'V1.0', owner: 'H', path: '' })

const versionCount = computed(() => versions.value.length)

function previewDoc(row) {
  if (row.path) openFilePreview(row.path, row.name || row.doc_no)
}

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

// ---------------- 编辑文档条目 ----------------
const editDlg = ref(false)
const editForm = ref({ id: '', doc_no: '', library: '01_项目库', category: '', name: '', version: 'V1.0.0', owner: '', status: '草稿', path: '' })
function openEdit(row) {
  editForm.value = { id: row.id, doc_no: row.doc_no, library: row.library, category: row.category || '',
    name: row.name, version: row.version, owner: row.owner || '', status: row.status || '草稿', path: row.path || '' }
  editDlg.value = true
}
async function saveEdit() {
  try {
    const { id, ...payload } = editForm.value
    await docsApi.update(id, payload)
    ElMessage.success('文档条目已更新')
    editDlg.value = false
    load()
  } catch (e) { ElMessage.error(e.message) }
}
async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除文档条目 ${row.doc_no}（同时删除正文文件）？`, '删除确认', { type: 'warning' })
    await docsApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) { if (e && e.message) ElMessage.error(e.message) }
}

// ---------------- 手动登记版本台账 ----------------
const verDlg = ref(false)
const verForm = ref({ version: '', item_name: '', item_type: '', executor: '', change_summary: '', path: '' })
function openVersion() {
  verForm.value = { version: '', item_name: '', item_type: '', executor: '', change_summary: '', path: '' }
  verDlg.value = true
}
async function saveVersion() {
  if (!verForm.value.version || !verForm.value.item_name) return ElMessage.warning('请填写版本与条目名称')
  try {
    await docsApi.addVersion(verForm.value)
    ElMessage.success('版本台账已登记')
    verDlg.value = false
    load()
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(load)
</script>

<style scoped>
.pm-link { cursor: pointer; color: var(--el-color-primary); word-break: break-all; }
.pm-link:hover { text-decoration: underline; }
</style>

<template>
  <el-dialog
    v-model="filePreview.open"
    :title="'文件预览 · ' + filePreview.title"
    width="760px"
    top="6vh"
    @closed="onClosed"
  >
    <div v-loading="loading" style="min-height: 200px">
      <el-alert v-if="error" :title="error" type="error" show-icon />
      <template v-else-if="kind === 'image'">
        <img :src="url" style="max-width: 100%; border-radius: 6px" />
      </template>
      <template v-else-if="kind === 'pdf'">
        <iframe :src="url" style="width: 100%; height: 68vh; border: 0" />
      </template>
      <template v-else-if="kind === 'text'">
        <pre class="fp-text">{{ text }}</pre>
      </template>
      <template v-else>
        <el-empty description="该格式不支持内联预览">
          <el-button type="primary" tag="a" :href="url" :download="filename">下载文件</el-button>
        </el-empty>
      </template>
    </div>
    <template #footer>
      <el-button tag="a" :href="url" :download="filename">下载</el-button>
      <el-button @click="closeFilePreview">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { filePreview, closeFilePreview } from '../composables/useFilePreview'
import { filesApi } from '../api'

const loading = ref(false)
const error = ref('')
const url = ref('')
const text = ref('')
const kind = ref('other')

const TEXT_EXT = ['txt', 'md', 'json', 'log', 'csv', 'yaml', 'yml', 'py', 'js', 'ts', 'html', 'css', 'xml']
const IMG_EXT = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp']

const filename = computed(() => {
  const p = filePreview.path || ''
  return p.split(/[\\/]/).pop() || 'file'
})
const ext = computed(() => {
  const m = filename.value.toLowerCase().match(/\.([a-z0-9]+)$/)
  return m ? m[1] : ''
})

async function load() {
  loading.value = true
  error.value = ''
  url.value = ''
  text.value = ''
  kind.value = 'other'
  try {
    const blob = await filesApi.preview(filePreview.path)
    if (IMG_EXT.includes(ext.value)) kind.value = 'image'
    else if (ext.value === 'pdf') kind.value = 'pdf'
    else if (TEXT_EXT.includes(ext.value)) {
      kind.value = 'text'
      text.value = await blob.text()
    } else kind.value = 'other'
    url.value = URL.createObjectURL(blob)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => filePreview.open, (o) => { if (o) load() })

function onClosed() {
  if (url.value) { URL.revokeObjectURL(url.value); url.value = '' }
}
</script>

<style scoped>
.fp-text {
  margin: 0;
  max-height: 64vh;
  overflow: auto;
  background: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

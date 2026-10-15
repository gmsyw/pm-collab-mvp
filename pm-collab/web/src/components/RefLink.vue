<template>
  <span class="ref-link" :class="'rl-' + type" @click.stop.prevent="onClick" :title="'查看 ' + typeLabel + '：' + display">
    <span class="rl-mark">{{ mark }}</span>
    <span class="rl-text">{{ display }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { openQuickView } from '../composables/useQuickView'

const props = defineProps({
  type: { type: String, required: true },   // task | member | role | handoff | doc
  value: { type: [String, Number], required: true },
  by: { type: String, default: 'code' },     // code | id
  label: { type: String, default: '' }
})

const META = {
  task: { mark: '📋', name: '任务卡' },
  member: { mark: '👤', name: '成员' },
  role: { mark: '🏷️', name: '角色卡' },
  handoff: { mark: '🔄', name: '交接单' },
  doc: { mark: '📄', name: '文档' }
}
const meta = computed(() => META[props.type] || { mark: '🔗', name: '关联' })
const typeLabel = computed(() => meta.value.name)
const mark = computed(() => meta.value.mark)
const display = computed(() => (props.label != null && props.label !== '') ? props.label : props.value)

function onClick() {
  openQuickView(props.type, props.value, { by: props.by, label: display.value })
}
</script>

<style scoped>
.ref-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 12px;
  line-height: 18px;
  border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
  user-select: none;
  white-space: nowrap;
}
.ref-link:hover { background: var(--el-fill-color-light); border-color: var(--el-border-color); }
.rl-mark { font-size: 12px; }
.rl-text { font-weight: 500; }
.rl-task { color: #409EFF; }
.rl-member { color: #67C23A; }
.rl-role { color: #E6A23C; }
.rl-handoff { color: #9C27B0; }
.rl-doc { color: #909399; }
</style>

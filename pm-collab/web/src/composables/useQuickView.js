import { reactive } from 'vue'

// 全局就地抽屉状态：任意页面点击关联引用即可打开，不离开当前上下文。
export const quickView = reactive({
  open: false,
  type: '',      // task | member | role | handoff | doc
  value: '',     // 编号或 id
  by: 'code',    // code | id
  label: ''      // 展示用文本
})

export function openQuickView(type, value, opts = {}) {
  quickView.type = type
  quickView.value = value
  quickView.by = opts.by || 'code'
  quickView.label = opts.label != null ? opts.label : value
  quickView.open = true
}

export function closeQuickView() {
  quickView.open = false
}

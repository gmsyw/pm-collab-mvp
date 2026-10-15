import { reactive } from 'vue'

// 全局文件预览弹窗状态：证据路径点击后打开，支持图片/PDF/文本内联预览与下载。
export const filePreview = reactive({
  open: false,
  path: '',
  title: ''
})

export function openFilePreview(path, title = '') {
  filePreview.path = path
  filePreview.title = title || path
  filePreview.open = true
}

export function closeFilePreview() {
  filePreview.open = false
}

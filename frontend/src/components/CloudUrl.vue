<script setup>
/**
 * 个人云盘的完整网址 + 复制 + 打开（2.25.1）。「我的账号」和账号页的云盘卡片都用它。
 *
 * 网址按学生链接同一套规则取（publicUrl.js）：配了 PUBLIC_BASE_URL 用它，否则用浏览器当前地址；
 * 在服务器本机用 127.0.0.1 打开时换成服务器的网卡地址，复制给别人才打得开。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { loadPublicBase, studentLink } from '../publicUrl'

const ready = ref(false)
onMounted(async () => {
  await loadPublicBase()
  ready.value = true
})
const url = computed(() => (ready.value ? studentLink('/cloud/') : `${location.origin}/cloud/`))

async function copy() {
  const text = url.value
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // http 页面上没有 clipboard 接口（机房、内网大多是 http），退回老办法
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  ElMessage.success('云盘网址已复制')
}
</script>

<template>
  <div class="cloud-url">
    <span class="lbl">云盘网址</span>
    <a :href="url" target="_blank" rel="noopener" class="u">{{ url }}</a>
    <el-button size="small" link type="primary" @click="copy">复制</el-button>
  </div>
</template>

<style scoped>
.cloud-url {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  font-size: 13px;
}
.lbl {
  color: var(--el-text-color-secondary);
}
.u {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 600;
  color: var(--el-color-primary);
  text-decoration: none;
  word-break: break-all;
}
.u:hover {
  text-decoration: underline;
}
</style>

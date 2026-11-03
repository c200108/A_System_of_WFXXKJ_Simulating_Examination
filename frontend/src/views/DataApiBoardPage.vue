<script setup>
/**
 * API 数据大图的投屏页：新开标签页整屏看，深色大字，不套顶栏（2.16.0）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import DataApiBoard from '../components/DataApiBoard.vue'

const route = useRoute()
const id = computed(() => Number(route.params.id))
const title = ref('')
const clock = ref('')
function tick() {
  clock.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}
onMounted(async () => {
  // 投屏页固定深色：Element Plus 的下拉框也跟着变深（只改这个标签页，不改老师存的主题）
  document.documentElement.classList.add('dark')
  tick()
  setInterval(tick, 1000)
  try {
    const info = await api.dataApi(id.value)
    title.value = info.name
    document.title = `${info.name} · 数据大图`
  } catch { /* 没权限会被拦回登录 */ }
})
function full() {
  if (document.fullscreenElement) document.exitFullscreen()
  else document.documentElement.requestFullscreen?.()
}
</script>

<template>
  <DataApiBoard :api-id="id" big>
    <template #title>
      <span class="title">{{ title }}</span>
      <span class="clock">{{ clock }}</span>
      <el-button size="small" @click="full">全屏</el-button>
    </template>
  </DataApiBoard>
</template>

<style scoped>
.title { font-size: 24px; font-weight: 600; margin-right: 12px; color: #f0f0ec; }
.clock { font-size: 18px; color: #9a9a95; margin-right: 12px; font-variant-numeric: tabular-nums; }
</style>

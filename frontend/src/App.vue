<script setup>
/**
 * 应用外壳，只做两件事：挂路由出口、恢复深浅色主题。
 *
 * 界面的框由各自的布局组件负责：
 *   layouts/StudentLayout.vue  学生平台（侧边栏）
 *   layouts/TeacherLayout.vue  教师后台（顶栏）
 * 免登录的公开页（凭链接答题、/dazi）不套任何框，直接渲染。
 */
import { onMounted } from 'vue'

onMounted(() => {
  // 主题两边共用一个设置：同一个人切过深色，走到哪一侧都该是深色
  document.documentElement.classList.toggle('dark', localStorage.getItem('theme') === 'dark')
})
</script>

<template>
  <router-view />
</template>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
}
body {
  background: var(--el-bg-color-page);
}

/* 两套布局共用的一点基础样式 */
.page-card {
  margin-bottom: 16px;
}

/* 对话框宽度各页面写的都是固定像素（520px、760px……），手机上会超出屏幕、
   整页横向滚动。这里统一封一道顶：再宽也不超过屏幕。
   写在全局而不是各页面的 scoped 里 —— el-dialog 挂在 body 上，
   scoped 样式和 :deep() 都够不着它。 */
.el-dialog {
  max-width: calc(100vw - 24px);
}
.el-message-box {
  max-width: calc(100vw - 24px);
}
</style>

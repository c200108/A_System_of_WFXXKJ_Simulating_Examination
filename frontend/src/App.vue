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

/* 提示框（确认、警告、导入结果这些）跟着内容走，而不是一律 420px 宽。
   一句"确定删除？"占半屏太空，导入结果那种十几行又挤成一长条。
   规则：
     宽度 = 内容实际需要的宽度（fit-content）
     下限 300px —— 再窄按钮就排不开
     上限 2/3 屏幕 —— 左右合计至少留出 1/3，长文本在这个宽度内折行
   高度也封一道：错误行多的时候内容区自己滚，别把框撑得比屏幕还高。 */
.el-message-box {
  width: fit-content;
  min-width: 300px;
  max-width: min(66vw, 680px);
}
.el-message-box__content {
  max-height: 60vh;
  overflow: auto;
}
.el-message-box__message {
  /* 后端的换行照原样显示，过长的行自动折 */
  white-space: pre-wrap;
  word-break: break-word;
}

/* 窄屏上 2/3 屏就太挤了，这里放宽到贴边 */
@media (max-width: 600px) {
  .el-message-box {
    max-width: calc(100vw - 24px);
    min-width: 0;
  }
}
</style>

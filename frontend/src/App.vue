<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { api } from './api'
import { clearAuth, currentUser, setUser } from './auth'

const route = useRoute()
const router = useRouter()

// 深色模式：Element Plus 认 <html class="dark">，记在本机
const dark = ref(false)
function applyTheme() {
  document.documentElement.classList.toggle('dark', dark.value)
  localStorage.setItem('theme', dark.value ? 'dark' : 'light')
}
function toggleTheme() {
  dark.value = !dark.value
  applyTheme()
}
onMounted(() => {
  dark.value = localStorage.getItem('theme') === 'dark'
  applyTheme()
})

// 用响应式的 currentUser，不要在 computed 里读 localStorage —— 那样不会更新
const user = currentUser

// 登录页和学生答题页不套教师界面的框
const isBare = computed(() => route.path === '/login' || route.meta.bare === true)

// 以服务端为准刷新一次身份：localStorage 里可能是旧的（比如管理员把某人
// 降成了普通教师），登录状态下拉一次 /auth/me 就能纠正过来。
onMounted(async () => {
  if (!isBare.value && localStorage.getItem('token')) {
    try {
      setUser(await api.me())
    } catch {
      // 令牌失效时 api.js 的拦截器已经会跳登录页，这里不用再处理
    }
  }
})

async function logout() {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  clearAuth()
  router.push('/login')
}
</script>

<template>
  <router-view v-if="isBare" />

  <el-container v-else class="app">
    <el-header class="header">
      <div class="brand">信息技术组卷台</div>
      <el-menu :default-active="route.path" mode="horizontal" router :ellipsis="false" class="nav">
        <el-menu-item index="/paper">组卷</el-menu-item>
        <el-menu-item index="/bank">题库</el-menu-item>
        <el-menu-item index="/import">导入</el-menu-item>
        <el-menu-item index="/exams">考试</el-menu-item>
        <el-menu-item index="/typing">打字</el-menu-item>
        <el-menu-item v-if="user?.role === 'admin'" index="/users">账号</el-menu-item>
      </el-menu>
      <div class="right">
        <el-button link :title="dark ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
          {{ dark ? '☀' : '◐' }}
        </el-button>
        <span class="who">{{ user?.name || user?.username }}</span>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </el-header>

    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
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
.header {
  display: flex;
  align-items: center;
  gap: 24px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 0 24px;
}
.brand {
  font-size: 17px;
  font-weight: 600;
  white-space: nowrap;
}
.nav {
  flex: 1;
  border-bottom: none !important;
}
.right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.who {
  color: var(--el-text-color-regular);
  font-size: 14px;
}
.main {
  padding: 20px 24px;
}
.page-card {
  margin-bottom: 16px;
}
</style>

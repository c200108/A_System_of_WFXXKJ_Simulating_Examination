<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { api } from '../api'
import { clearAuth, currentUser, setUser } from '../auth'
import { siteConfig, year } from '../siteConfig'

const route = useRoute()
const router = useRouter()

// 平台名称、页脚、图标都在 siteConfig 里，main.js 启动时已经取回来了
const title = computed(() => siteConfig.site?.title || '信息科技教学平台')
const brand = computed(() => siteConfig.site?.brand || title.value)
const footer = computed(() => siteConfig.site?.footer || '')
const version = ref('')

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

// 以服务端为准刷新一次身份：localStorage 里可能是旧的（比如管理员把某人
// 降成了普通教师），登录状态下拉一次 /auth/me 就能纠正过来。
onMounted(async () => {
  try {
    version.value = (await api.changelogLatest()).version || ''
  } catch {
    /* 没有更新日志就不显示版本号 */
  }

  if (localStorage.getItem('token')) {
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
  router.push('/js/login')
}

function onUserCommand(cmd) {
  if (cmd === 'profile') router.push('/js/profile')
  if (cmd === 'logout') logout()
}
</script>

<template>
  <el-container class="app">
    <el-header class="header">
      <div class="brand">{{ brand }}</div>
      <el-menu :default-active="route.path" mode="horizontal" router :ellipsis="false" class="nav">
        <template v-if="user">
          <el-menu-item index="/js/paper">组卷</el-menu-item>
          <el-menu-item index="/js/bank">题库</el-menu-item>
          <el-menu-item index="/js/import">导入</el-menu-item>
          <el-menu-item index="/js/exams">考试</el-menu-item>
          <el-menu-item index="/js/students">学生</el-menu-item>
          <el-menu-item index="/js/typing">打字</el-menu-item>
          <el-menu-item index="/js/typing-texts">练习文本</el-menu-item>
        </template>
        <el-menu-item index="/js/feedback">反馈</el-menu-item>
        <el-menu-item index="/js/changelog">更新日志</el-menu-item>
        <el-menu-item v-if="user?.role === 'admin'" index="/js/users">账号</el-menu-item>
      </el-menu>
      <div class="right">
        <el-button link :title="dark ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
          {{ dark ? '☀' : '◐' }}
        </el-button>
        <el-dropdown v-if="user" trigger="click" @command="onUserCommand">
          <span class="who">
            {{ user.name || user.username }}
            <el-tag v-if="user.role === 'admin'" size="small" type="danger" effect="plain">管理员</el-tag>
            <i class="caret">▾</i>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">我的账号</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button v-else link type="primary" @click="router.push('/js/login')">教师登录</el-button>
      </div>
    </el-header>

    <el-main class="main">
      <router-view />
    </el-main>

    <el-footer class="footer">
      <span>© {{ year }} {{ title }}</span>
      <span v-if="version" class="ver">
        <router-link to="/js/changelog" title="查看更新日志">v{{ version }}</router-link>
      </span>
      <span v-if="footer">{{ footer }}</span>
    </el-footer>
  </el-container>
</template>

<style scoped>
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
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  cursor: pointer;
  outline: none;
}
.who:hover {
  color: var(--el-color-primary);
}
.caret {
  font-style: normal;
  font-size: 11px;
  opacity: 0.6;
}
.main {
  padding: 20px 24px;
}
.footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  height: 46px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}
.footer .ver a {
  color: var(--el-color-primary);
  text-decoration: none;
  font-family: ui-monospace, Consolas, monospace;
}
</style>

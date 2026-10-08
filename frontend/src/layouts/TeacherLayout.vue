<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Avatar, Collection, EditPen, Tickets, User } from '@element-plus/icons-vue'
import { api } from '../api'
import { clearAuth, currentUser, setUser } from '../auth'
import { appLogout, inApp } from '../appBridge'
import { isMobile } from '../mobile'
import { siteConfig, year } from '../siteConfig'
import BrandLogo from '../components/BrandLogo.vue'

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
  // APP 里登录页是原生的，交回外壳；浏览器里照旧去网页登录页
  if (inApp) appLogout()
  else router.push('/js/login')
}

function onUserCommand(cmd) {
  if (cmd === 'profile') router.push('/js/profile')
  if (cmd === 'logout') logout()
}

// ---------------------------------------------------------------- 手机布局（5.0.0）
// 窄屏（手机浏览器、教师端 APP）把顶栏菜单换成底部标签栏：四个主功能 + 「我的」。
// 反馈、更新日志、账号管理、深色模式、退出登录这些不常用的收进「我的」页。
const TABS = [
  { path: '/js/paper', label: '组卷', icon: EditPen },
  { path: '/js/bank', label: '题库', icon: Collection },
  { path: '/js/exams', label: '考试', icon: Tickets },
  { path: '/js/students', label: '学生', icon: User },
  { path: '/js/me', label: '我的', icon: Avatar }
]
// 「我的」下面的几页（我的账号、反馈、更新日志、账号）也算在「我的」标签里
const ME_PAGES = ['/js/me', '/js/profile', '/js/feedback', '/js/changelog', '/js/users']
const activeTab = computed(() => {
  if (ME_PAGES.includes(route.path)) return '/js/me'
  return TABS.find(t => route.path.startsWith(t.path))?.path || ''
})
// 二级页（从「我的」点进去的）顶栏左边给个返回
const canGoBack = computed(() => ME_PAGES.includes(route.path) && route.path !== '/js/me')
const pageTitle = computed(() => route.meta.title || brand.value)
</script>

<template>
  <!-- 手机布局 -->
  <div v-if="isMobile" class="m-app" :class="{ 'has-tabs': !!user }">
    <header class="m-bar">
      <button v-if="canGoBack" class="m-back" aria-label="返回" @click="router.push('/js/me')">
        <svg viewBox="0 0 24 24" width="22" height="22"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" /></svg>
      </button>
      <BrandLogo v-else :size="26" :radius="0.27" />
      <span class="m-title">{{ pageTitle }}</span>
      <el-button v-if="!user" link type="primary" @click="router.push('/js/login')">教师登录</el-button>
    </header>

    <main class="m-main">
      <router-view />
    </main>

    <nav v-if="user" class="m-tabs">
      <router-link
        v-for="t in TABS"
        :key="t.path"
        :to="t.path"
        class="m-tab"
        :class="{ on: activeTab === t.path }"
      >
        <el-icon :size="22"><component :is="t.icon" /></el-icon>
        <span>{{ t.label }}</span>
      </router-link>
    </nav>
  </div>

  <!-- 电脑布局：原来的顶栏 -->
  <el-container v-else class="app">
    <el-header class="header">
      <div class="brand">
        <BrandLogo :size="26" :radius="0.27" />
        <span>{{ brand }}</span>
      </div>
      <el-menu :default-active="route.path" mode="horizontal" router :ellipsis="false" class="nav">
        <template v-if="user">
          <el-menu-item index="/js/paper">组卷</el-menu-item>
          <el-menu-item index="/js/bank">题库</el-menu-item>
          <el-menu-item index="/js/exams">考试</el-menu-item>
          <el-menu-item index="/js/students">学生</el-menu-item>
        </template>
        <el-menu-item index="/js/feedback">反馈</el-menu-item>
        <template v-if="user?.role === 'admin'">
          <el-menu-item index="/js/changelog">更新日志</el-menu-item>
          <el-menu-item index="/js/users">账号</el-menu-item>
        </template>
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
        <!-- 版本号谁都看得到，但只有管理员点得进更新日志 -->
        <router-link
          v-if="user?.role === 'admin'"
          to="/js/changelog"
          title="查看更新日志"
        >v{{ version }}</router-link>
        <span v-else>v{{ version }}</span>
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
  display: flex;
  align-items: center;
  gap: 9px;
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

/* ---------------------------------------------------------------- 手机布局 */
.m-app {
  min-height: 100%;
  background: var(--el-bg-color-page);
}
.m-bar {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 52px;
  padding: 0 14px;
  background: var(--el-bg-color);
  box-shadow: 0 1px 0 var(--el-border-color-lighter);
}
.m-title {
  flex: 1;
  min-width: 0;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.m-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-left: -6px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-primary);
}
.m-back:active {
  background: var(--el-fill-color);
}
.m-main {
  padding: 12px 10px 16px;
}
.has-tabs .m-main {
  /* 给底部标签栏让位 */
  padding-bottom: calc(76px + env(safe-area-inset-bottom));
}
.m-tabs {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 60;
  display: flex;
  height: 58px;
  padding-bottom: env(safe-area-inset-bottom);
  background: var(--el-bg-color);
  box-shadow: 0 -1px 0 var(--el-border-color-lighter), 0 -6px 18px rgba(0, 0, 0, 0.04);
}
.m-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  text-decoration: none;
  -webkit-tap-highlight-color: transparent;
}
.m-tab.on {
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>

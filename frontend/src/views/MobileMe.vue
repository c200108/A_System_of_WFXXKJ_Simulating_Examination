<script setup>
/**
 * 手机布局的「我的」页（5.0.0）。
 *
 * 电脑上这些入口散在顶栏（反馈、更新日志、账号）和右上角下拉（我的账号、退出）里，
 * 手机底部标签栏只放得下五个，不常用的都收到这一页。
 * 电脑上没有「我的」这个标签，误进来直接转去「我的账号」。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { api } from '../api'
import { clearAuth, currentUser } from '../auth'
import { appLogout, inApp } from '../appBridge'
import { isMobile } from '../mobile'
import { siteConfig } from '../siteConfig'

const router = useRouter()
const user = currentUser
const isAdmin = computed(() => user.value?.role === 'admin')
const initial = computed(() => (user.value?.name || user.value?.username || '?').slice(0, 1))

const version = ref('')
const pending = ref(0)
const appVersion = ref('')
const dark = ref(document.documentElement.classList.contains('dark'))

watch(isMobile, m => {
  if (!m) router.replace('/js/profile')
})

onMounted(async () => {
  if (!isMobile.value) return router.replace('/js/profile')
  try {
    appVersion.value = (inApp && window.WfxxApp.getAppVersion?.()) || ''
  } catch {
    /* 旧版 APP 没有这个接口 */
  }
  try {
    version.value = (await api.changelogLatest()).version || ''
  } catch {
    /* 没有更新日志就不显示 */
  }
  try {
    pending.value = isAdmin.value ? (await api.feedbackPendingCount())?.pending || 0 : 0
  } catch {
    /* 角标拿不到不影响使用 */
  }
})

function setDark(v) {
  dark.value = v
  document.documentElement.classList.toggle('dark', v)
  localStorage.setItem('theme', v ? 'dark' : 'light')
}

async function logout() {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  clearAuth()
  if (inApp) appLogout()
  else router.push('/js/login')
}

const server = location.host
</script>

<template>
  <div class="me">
    <section class="card hero">
      <div class="avatar">{{ initial }}</div>
      <div class="who">
        <div class="name">
          {{ user?.name || user?.username }}
          <el-tag v-if="isAdmin" size="small" type="danger" effect="plain" round>管理员</el-tag>
        </div>
        <div class="sub">{{ user?.username }}<template v-if="user?.grade_class"> · {{ user.grade_class }}</template></div>
      </div>
    </section>

    <section class="card list">
      <router-link to="/js/profile" class="row">
        <span class="ico" style="--c: #5b7cfa">👤</span>
        <span class="lbl">我的账号<small>资料、修改密码</small></span>
        <span class="arrow">›</span>
      </router-link>
      <router-link to="/js/feedback" class="row">
        <span class="ico" style="--c: #22b07d">💬</span>
        <span class="lbl">需求反馈<small>提建议、报问题</small></span>
        <el-badge v-if="pending" :value="pending" class="badge" />
        <span class="arrow">›</span>
      </router-link>
      <template v-if="isAdmin">
        <router-link to="/js/users" class="row">
          <span class="ico" style="--c: #f0883e">🛡</span>
          <span class="lbl">账号管理<small>教师账号、权限</small></span>
          <span class="arrow">›</span>
        </router-link>
        <router-link to="/js/changelog" class="row">
          <span class="ico" style="--c: #8b5cf6">📋</span>
          <span class="lbl">更新日志<small>每个版本改了什么</small></span>
          <span class="arrow">›</span>
        </router-link>
      </template>
    </section>

    <section class="card list">
      <div class="row">
        <span class="ico" style="--c: #475569">🌙</span>
        <span class="lbl">深色模式</span>
        <el-switch :model-value="dark" @update:model-value="setDark" />
      </div>
    </section>

    <section class="card list info">
      <div class="row">
        <span class="lbl">服务器</span>
        <span class="val">{{ server }}</span>
      </div>
      <div v-if="version" class="row">
        <span class="lbl">系统版本</span>
        <span class="val mono">v{{ version }}</span>
      </div>
      <div v-if="appVersion" class="row">
        <span class="lbl">APP 版本</span>
        <span class="val mono">v{{ appVersion }}</span>
      </div>
      <div class="row">
        <span class="lbl">平台</span>
        <span class="val">{{ siteConfig.site?.title }}</span>
      </div>
    </section>

    <button class="logout" @click="logout">退出登录</button>
  </div>
</template>

<style scoped>
.me {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 640px;
  margin: 0 auto;
}
.card {
  background: var(--el-bg-color);
  border-radius: 14px;
  overflow: hidden;
}
.hero {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 18px;
  background: linear-gradient(135deg, #5b7cfa, #3f5bd8);
  color: #fff;
  box-shadow: 0 8px 24px rgba(63, 91, 216, 0.25);
}
.avatar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  font-size: 24px;
  font-weight: 600;
}
.who {
  min-width: 0;
}
.name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 19px;
  font-weight: 600;
}
.name :deep(.el-tag) {
  background: rgba(255, 255, 255, 0.92);
}
.sub {
  margin-top: 4px;
  font-size: 13px;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 54px;
  padding: 0 16px;
  color: var(--el-text-color-primary);
  text-decoration: none;
  -webkit-tap-highlight-color: transparent;
}
.row + .row {
  border-top: 1px solid var(--el-border-color-lighter);
}
a.row:active {
  background: var(--el-fill-color-light);
}
.ico {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: color-mix(in srgb, var(--c) 14%, transparent);
  font-size: 16px;
}
.lbl {
  flex: 1;
  display: flex;
  flex-direction: column;
  font-size: 15px;
}
.lbl small {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.arrow {
  font-size: 20px;
  color: var(--el-text-color-placeholder);
}
.badge {
  margin-right: 4px;
}
.info .row {
  min-height: 46px;
}
.info .lbl {
  flex: none;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.val {
  flex: 1;
  text-align: right;
  font-size: 14px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
}
.logout {
  height: 48px;
  margin-top: 4px;
  border: 0;
  border-radius: 14px;
  background: var(--el-bg-color);
  color: var(--el-color-danger);
  font-size: 16px;
  font-weight: 500;
}
.logout:active {
  background: var(--el-fill-color-light);
}
</style>

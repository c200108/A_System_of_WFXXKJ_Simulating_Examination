<script setup>
/**
 * 学生实践平台的外壳：可伸缩侧边栏 + 主内容区。
 *
 * 收起状态记在本机，下次进来还是上次的样子。窄屏（比如机房的老显示器
 * 横过来用，或者手机）默认收起，把地方留给内容。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { api } from '../api'
import { clearStudentAuth, currentStudent, setStudent } from '../auth'
import { siteConfig, year } from '../siteConfig'

const route = useRoute()
const router = useRouter()

const me = currentStudent
const title = computed(() => siteConfig.site?.student_title || '昌邑市实验中学信息科技学生实践平台')
// 侧边栏顶部放短名字，长标题在这么窄的地方排不开
const shortTitle = computed(() => siteConfig.site?.student_brand || '学生实践平台')

const MENU = [
  { path: '/home', icon: '🏠', label: '首页' },
  { path: '/exam', icon: '📝', label: '考试' },
  { path: '/typing', icon: '⌨', label: '打字训练' }
]

// 答题页是整页沉浸的，不显示侧边栏 —— 考试中途点走太容易误操作
const isFull = computed(() => route.meta.full === true)

const COLLAPSE_KEY = 'studentSidebarCollapsed'
const collapsed = ref(false)
const narrow = ref(false)

function syncWidth() {
  const wasNarrow = narrow.value
  narrow.value = window.innerWidth < 860
  // 从宽变窄时自动收起；反过来恢复成用户自己选的状态
  if (narrow.value && !wasNarrow) collapsed.value = true
  if (!narrow.value && wasNarrow) collapsed.value = localStorage.getItem(COLLAPSE_KEY) === '1'
}

function toggle() {
  collapsed.value = !collapsed.value
  if (!narrow.value) localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
}

const dark = ref(false)
function toggleTheme() {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
  localStorage.setItem('theme', dark.value ? 'dark' : 'light')
}

onMounted(async () => {
  dark.value = localStorage.getItem('theme') === 'dark'
  collapsed.value = localStorage.getItem(COLLAPSE_KEY) === '1'
  syncWidth()
  window.addEventListener('resize', syncWidth)

  // 以服务端为准刷新一次身份：老师可能改了班级，或者把账号停用了
  if (localStorage.getItem('studentToken')) {
    try {
      setStudent(await api.studentMe())
    } catch {
      // 令牌失效时拦截器已经会跳登录页
    }
  }
})
onUnmounted(() => window.removeEventListener('resize', syncWidth))

// 窄屏点完菜单自动收起，否则抽屉盖着内容
watch(() => route.path, () => {
  if (narrow.value) collapsed.value = true
})

async function logout() {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  clearStudentAuth()
  router.push('/login')
}
</script>

<template>
  <!-- 答题中：整页只留卷子 -->
  <router-view v-if="isFull" />

  <div v-else class="stu-shell" :class="{ collapsed, narrow }">
    <!-- 窄屏展开侧边栏时盖一层，点一下收回去 -->
    <div v-if="narrow && !collapsed" class="mask" @click="collapsed = true" />

    <aside class="side">
      <div class="brand" :title="title">
        <span class="logo">科</span>
        <span v-show="!collapsed" class="bname">{{ shortTitle }}</span>
      </div>

      <nav class="menu">
        <router-link
          v-for="m in MENU"
          :key="m.path"
          :to="m.path"
          class="item"
          :class="{ on: route.path === m.path || route.path.startsWith(m.path + '/') }"
          :title="collapsed ? m.label : ''"
        >
          <span class="ico">{{ m.icon }}</span>
          <span v-show="!collapsed" class="label">{{ m.label }}</span>
        </router-link>
      </nav>

      <div class="sidefoot">
        <button class="item plain" :title="collapsed ? '退出登录' : ''" @click="logout">
          <span class="ico">⏻</span>
          <span v-show="!collapsed" class="label">退出登录</span>
        </button>
      </div>
    </aside>

    <div class="body">
      <header class="topbar">
        <button class="toggle" :title="collapsed ? '展开菜单' : '收起菜单'" @click="toggle">
          {{ collapsed ? '☰' : '⟨' }}
        </button>
        <h1 class="ptitle">{{ route.meta.title || '' }}</h1>
        <span class="grow" />
        <button class="icobtn" :title="dark ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
          {{ dark ? '☀' : '◐' }}
        </button>
        <span v-if="me" class="who">
          {{ me.name }}
          <i class="cls">{{ me.student_class || '未分班' }}</i>
        </span>
      </header>

      <main class="main">
        <router-view />
      </main>

      <footer class="foot">© {{ year }} {{ title }}</footer>
    </div>
  </div>
</template>

<style scoped>
/* 类名要足够特别：Vue 的 scoped 样式也会落到子组件的根元素上，
   用 .wrap 这种大众名字会把子页面的根节点一起改掉。 */
.stu-shell {
  display: flex;
  min-height: 100vh;
  background: var(--el-bg-color-page);
}

/* ---------- 侧边栏 ---------- */
.side {
  width: 208px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-light);
  transition: width 0.18s ease;
  position: sticky;
  top: 0;
  height: 100vh;
  z-index: 20;
}
.collapsed .side {
  width: 60px;
}
.narrow .side {
  position: fixed;
  left: 0;
  top: 0;
  box-shadow: 2px 0 16px rgba(0, 0, 0, 0.14);
}
/* 窄屏收起时整条藏起来，不占位置 */
.narrow.collapsed .side {
  width: 0;
  border-right: none;
  overflow: hidden;
}
.mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 15;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
}
.logo {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 9px;
  background: linear-gradient(135deg, #5b7cfa, #3f5bd8);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
}
.bname {
  font-size: 14.5px;
  font-weight: 600;
  white-space: nowrap;
}

.menu {
  flex: 1;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}
.item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 42px;
  padding: 0 12px;
  border-radius: 9px;
  color: var(--el-text-color-regular);
  text-decoration: none;
  font-size: 14px;
  white-space: nowrap;
  transition: background 0.14s, color 0.14s;
}
.item:hover {
  background: var(--el-fill-color-light);
}
.item.on {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.item .ico {
  width: 20px;
  flex: none;
  text-align: center;
  font-size: 16px;
}
.item.plain {
  width: 100%;
  border: none;
  background: none;
  cursor: pointer;
  font-family: inherit;
}
.item.plain:hover {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.sidefoot {
  padding: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

/* ---------- 右侧 ---------- */
.body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 56px;
  padding: 0 20px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  position: sticky;
  top: 0;
  z-index: 10;
}
.toggle,
.icobtn {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 17px;
  color: var(--el-text-color-secondary);
  padding: 6px 9px;
  border-radius: 8px;
  line-height: 1;
}
.toggle:hover,
.icobtn:hover {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
}
.ptitle {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.grow {
  flex: 1;
}
.who {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: var(--el-text-color-regular);
}
.who .cls {
  font-style: normal;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}
.main {
  flex: 1;
  padding: 20px;
}
.foot {
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>

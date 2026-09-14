import { createRouter, createWebHistory } from 'vue-router'
import { currentUser } from './auth'

/**
 * 两套平台共用一个单页应用，靠路径前缀分开：
 *
 *   /      学生实践平台（侧边栏布局）
 *   /js    教师后台（顶栏布局，js = 教师的首字母缩写）
 *
 * 两边的登录状态也分开存：学生令牌在 studentToken，教师令牌在 token。
 * 一台机器上老师和学生各自登录互不挤掉，机房里同一台电脑轮流用很常见。
 */

// 学生平台：侧边栏 + 主内容
const studentRoutes = {
  path: '/',
  component: () => import('./layouts/StudentLayout.vue'),
  children: [
    { path: '', redirect: '/home' },
    { path: 'home', component: () => import('./views/student/Home.vue'), meta: { title: '首页' } },
    { path: 'exam', component: () => import('./views/student/Exams.vue'), meta: { title: '考试' } },
    {
      path: 'exam/:id',
      component: () => import('./views/student/ExamTake.vue'),
      meta: { title: '答题', full: true }
    },
    { path: 'typing', component: () => import('./views/student/Typing.vue'), meta: { title: '打字训练' } }
  ]
}

// 教师后台：原来那套顶栏界面，整体挪到 /js 下
const teacherRoutes = {
  path: '/js',
  component: () => import('./layouts/TeacherLayout.vue'),
  children: [
    { path: '', redirect: '/js/paper' },
    { path: 'paper', component: () => import('./views/Paper.vue'), meta: { title: '组卷' } },
    // 题库 = 题库管理 + 批量导入；考试 = 考试 + 打字学情 + 练习文本。
    // 两个工作台页面用同一个折叠面板组件，加功能只改各自的 panels 数组。
    { path: 'bank', component: () => import('./views/BankHub.vue'), meta: { title: '题库' } },
    { path: 'exams', component: () => import('./views/ExamHub.vue'), meta: { title: '考试' } },
    { path: 'students', component: () => import('./views/Students.vue'), meta: { title: '学生' } },
    { path: 'classes', component: () => import('./views/Classes.vue'), meta: { title: '班级' } },

    // 合并前的老地址：重定向到新位置，并带上要展开哪个面板。
    // 老师收藏夹里存的链接不会失效。
    { path: 'import', redirect: { path: '/js/bank', query: { panel: 'import' } } },
    { path: 'typing', redirect: { path: '/js/exams', query: { panel: 'typing' } } },
    {
      path: 'typing-texts',
      redirect: { path: '/js/exams', query: { panel: 'typing-texts' } }
    },
    { path: 'profile', component: () => import('./views/Profile.vue'), meta: { title: '我的账号' } },
    { path: 'users', component: () => import('./views/Users.vue'), meta: { title: '账号', admin: true } },
    // 反馈公开可看，登录的老师多出管理操作
    {
      path: 'feedback',
      component: () => import('./views/Feedback.vue'),
      meta: { title: '反馈', public: true }
    },
    // 更新日志只给管理员：讲的是系统这次改了什么，是维护者之间的事
    {
      path: 'changelog',
      component: () => import('./views/Changelog.vue'),
      meta: { title: '更新日志', admin: true }
    }
  ]
}

const routes = [
  // 两个登录页，各管各的
  { path: '/login', component: () => import('./views/student/Login.vue'), meta: { public: true } },
  { path: '/js/login', component: () => import('./views/Login.vue'), meta: { public: true } },

  // 免登录的公开页：凭链接答题、公开打字练习。不套任何平台的框。
  {
    path: '/take/:token',
    component: () => import('./views/Take.vue'),
    meta: { public: true, bare: true }
  },
  {
    path: '/dazi',
    component: () => import('./views/Typing.vue'),
    meta: { public: true, bare: true }
  },

  teacherRoutes,
  studentRoutes,

  // 兜底：老书签可能还指着改版前的教师端地址
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(to => {
  const isTeacherSide = to.path === '/js' || to.path.startsWith('/js/')

  if (isTeacherSide) {
    if (to.meta.public) return true
    if (!localStorage.getItem('token')) return '/js/login'
    // meta.admin 的页面以前只靠菜单 v-if 藏着，手敲地址照样进得去
    // （虽然接口会 403，但页面会先闪一下再报错）。这里真的拦住。
    if (to.meta.admin && currentUser.value?.role !== 'admin') return '/js/paper'
    return true
  }

  // 学生侧
  if (to.meta.public) return true
  return localStorage.getItem('studentToken') ? true : '/login'
})

export default router

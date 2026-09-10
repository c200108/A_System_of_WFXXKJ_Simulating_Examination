import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  // 学生答题页：不需要登录，凭链接里的口令访问
  {
    path: '/take/:token',
    component: () => import('./views/Take.vue'),
    meta: { public: true, bare: true }
  },
  // 打字训练学生页：和答题页一样免登录、不套教师界面的框
  {
    path: '/dazi',
    component: () => import('./views/Typing.vue'),
    meta: { public: true, bare: true }
  },
  // 反馈与更新日志：不登录也能看，但套教师界面的框（登录了能多出管理操作）
  {
    path: '/feedback',
    component: () => import('./views/Feedback.vue'),
    meta: { public: true, title: '反馈' }
  },
  {
    path: '/changelog',
    component: () => import('./views/Changelog.vue'),
    meta: { public: true, title: '更新日志' }
  },
  { path: '/', redirect: '/paper' },
  { path: '/paper', component: () => import('./views/Paper.vue'), meta: { title: '组卷' } },
  { path: '/bank', component: () => import('./views/Questions.vue'), meta: { title: '题库' } },
  { path: '/import', component: () => import('./views/Import.vue'), meta: { title: '导入' } },
  { path: '/exams', component: () => import('./views/Exams.vue'), meta: { title: '考试' } },
  { path: '/typing', component: () => import('./views/TypingAdmin.vue'), meta: { title: '打字' } },
  { path: '/typing-texts', component: () => import('./views/TypingTexts.vue'), meta: { title: '练习文本' } },
  { path: '/profile', component: () => import('./views/Profile.vue'), meta: { title: '我的账号' } },
  { path: '/users', component: () => import('./views/Users.vue'), meta: { title: '账号', admin: true } }
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(to => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) return '/login'
  // 老师已登录时打开学生链接，仍然按学生视角显示，不跳转
  if (to.path === '/login' && token) return '/paper'
  return true
})

export default router

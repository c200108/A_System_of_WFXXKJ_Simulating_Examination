/**
 * 当前登录用户的响应式状态。
 *
 * 为什么单独抽出来：原先 App.vue 里写的是
 *   const user = computed(() => JSON.parse(localStorage.getItem('user')))
 * localStorage 不是响应式的，computed 没有可依赖的响应源，Vue 只求值一次就
 * 永久缓存。结果登录前算出 null，登录后仍返回 null —— 用户名不显示、
 * 管理员的「账号」菜单也出不来，只有刷新整页才恢复。
 *
 * 改成 ref 之后，登录/登出直接改这个 ref，界面立刻跟着变。
 */
import { ref } from 'vue'

const STORAGE_KEY = 'user'

function readStored() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    return null // 存过 "undefined" 之类的脏值时不要让整个页面崩掉
  }
}

/** 全局唯一的当前用户。初值取自 localStorage，刷新页面后仍在。 */
export const currentUser = ref(readStored())

export function setUser(user) {
  currentUser.value = user || null
  if (user) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
}

export function clearAuth() {
  localStorage.removeItem('token')
  setUser(null)
}

export const isAdmin = () => currentUser.value?.role === 'admin'

// ---------------------------------------------------------------- 学生侧
/**
 * 学生的登录状态和教师的完全分开存：令牌、用户信息、清除逻辑都是两套。
 *
 * 这样做不只是为了干净 —— 机房里同一台电脑老师和学生轮流用很常见，
 * 共用一个 key 的话谁登录都会把对方挤掉。
 */
const STUDENT_KEY = 'student'

function readStudent() {
  try {
    return JSON.parse(localStorage.getItem(STUDENT_KEY) || 'null')
  } catch {
    return null
  }
}

export const currentStudent = ref(readStudent())

export function setStudent(student) {
  currentStudent.value = student || null
  if (student) {
    localStorage.setItem(STUDENT_KEY, JSON.stringify(student))
  } else {
    localStorage.removeItem(STUDENT_KEY)
  }
}

export function clearStudentAuth() {
  localStorage.removeItem('studentToken')
  setStudent(null)
}

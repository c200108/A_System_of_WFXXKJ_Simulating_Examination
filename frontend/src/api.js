import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from './router'
import { clearAuth } from './auth'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

// 每个请求自动带上登录令牌
http.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  res => res.data,
  err => {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (status === 401) {
      clearAuth() // 清 token 和响应式登录状态，顶栏同步变回未登录
      router.push('/login')
      ElMessage.error('登录已过期，请重新登录')
    } else {
      ElMessage.error(typeof detail === 'string' ? detail : '请求失败，请稍后再试')
    }
    return Promise.reject(err)
  }
)

/** 触发浏览器下载。后端返回的是二进制流，文件名在前端拼，省得解析响应头。 */
export async function download(blobPromise, filename) {
  const blob = await blobPromise
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

/** 去掉 Windows 文件名里不允许的字符 */
export function safeName(name) {
  return (String(name || '').replace(/[\\/:*?"<>|]/g, '').trim()) || '试卷'
}

export const api = {
  // 前后端共用 config.yaml，这里取界面要用的那部分
  siteConfig: () => http.get('/config'),

  login(username, password) {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    return http.post('/auth/login', form)
  },
  me: () => http.get('/auth/me'),
  updateMe: data => http.patch('/auth/me', data),
  changePassword: data => http.post('/auth/password', data),
  listUsers: () => http.get('/auth/users'),
  createUser: data => http.post('/auth/users', data),
  disableUser: id => http.delete(`/auth/users/${id}`),
  updateUser: (id, data) => http.patch(`/auth/users/${id}`, data),

  dicts: category => http.get('/dicts', { params: { category } }),
  addDict: data => http.post('/dicts', data),

  questions: params => http.get('/questions', { params }),
  stats: () => http.get('/questions/stats'),
  createQuestion: data => http.post('/questions', data),
  updateQuestion: (id, data) => http.put(`/questions/${id}`, data),
  deleteQuestion: id => http.delete(`/questions/${id}`),

  importQuestions(file) {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/imports/questions', fd)
  },
  importLogs: () => http.get('/imports/logs'),

  generate: data => http.post('/papers/generate', data),
  previewPlan: data => http.post('/papers/preview-plan', data),
  papers: () => http.get('/papers'),
  paper: id => http.get(`/papers/${id}`),
  deletePaper: id => http.delete(`/papers/${id}`),

  // 导出：都返回二进制流，配合上面的 download() 用
  exportPaperXlsx: paper =>
    http.post('/papers/export/xlsx', paper, { responseType: 'blob' }),
  exportStudentHtml: paper =>
    http.post('/papers/export/student-html', paper, { responseType: 'blob' }),
  exportBank: params =>
    http.get('/questions/export.xlsx', { params, responseType: 'blob' }),
  templateFile: () =>
    http.get('/imports/template', { responseType: 'blob' }),

  // 考试（教师端）
  exams: () => http.get('/exams'),
  createExam: data => http.post('/exams', data),
  updateExam: (id, data) => http.patch(`/exams/${id}`, data),
  deleteExam: id => http.delete(`/exams/${id}`),
  submissions: id => http.get(`/exams/${id}/submissions`),
  submission: (id, sid) => http.get(`/exams/${id}/submissions/${sid}`),
  examStats: id => http.get(`/exams/${id}/stats`),
  exportScores: id => http.get(`/exams/${id}/export.xlsx`, { responseType: 'blob' }),

  // 打字训练
  typingConfig: () => http.get('/typing/config'),
  typingPassage: (mode, difficulty) =>
    http.get('/typing/passage', { params: { mode, difficulty } }),
  typingSubmit: data => http.post('/typing/records', data),
  typingRecords: params => http.get('/typing/records', { params }),
  typingStats: () => http.get('/typing/stats'),
  typingClasses: () => http.get('/typing/classes'),
  typingExport: () => http.get('/typing/export.xlsx', { responseType: 'blob' }),
  typingDelete: id => http.delete(`/typing/records/${id}`),
  typingClear: student_class =>
    http.delete('/typing/records', { params: { student_class } }),

  // 打字文本库
  typingTexts: params => http.get('/typing/texts', { params }),
  typingTextStats: () => http.get('/typing/texts/stats'),
  typingTextCreate: data => http.post('/typing/texts', data),
  typingTextUpdate: (id, data) => http.put(`/typing/texts/${id}`, data),
  typingTextDelete: id => http.delete(`/typing/texts/${id}`),
  typingTextBulk: (ids, action) => http.post('/typing/texts/bulk', { ids, action }),

  // 需求反馈（提交与浏览都不需要登录）
  feedbackList: params => http.get('/feedback', { params }),
  feedbackCreate: data => http.post('/feedback', data),
  feedbackAll: () => http.get('/feedback/all'),
  feedbackReply: (id, reply) => http.post(`/feedback/${id}/reply`, { reply }),
  feedbackReplyDelete: rid => http.delete(`/feedback/replies/${rid}`),
  feedbackLike: id => http.post(`/feedback/${id}/like`),
  feedbackVisibility: (id, is_public) =>
    http.patch(`/feedback/${id}/visibility`, null, { params: { is_public } }),
  feedbackDelete: id => http.delete(`/feedback/${id}`),

  // 更新日志
  changelog: () => http.get('/changelog'),
  changelogTypes: () => http.get('/changelog/types'),
  changelogLatest: () => http.get('/changelog/latest'),
  changelogCreate: data => http.post('/changelog', data),
  changelogDelete: id => http.delete(`/changelog/${id}`),

  // 学生端（不需要登录）
  takePaper: token => http.get(`/take/${token}`),
  submitPaper: (token, data) => http.post(`/take/${token}/submit`, data)
}

export default http

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

// 字段名 → 中文，用来把 FastAPI 的 422 翻成人话
const FIELD_CN = {
  username: '用户名',
  password: '密码',
  new_password: '新密码',
  old_password: '原密码',
  name: '姓名',
  role: '角色',
  grade_class: '任教年级班级',
  contact: '联系方式',
  content: '内容',
  author: '称呼',
  category: '类型',
  reply: '回复',
  version: '版本号',
  released_on: '发布日期',
  change_type: '变动类型',
  title: '标题',
  difficulty: '难度',
  mode: '语言',
  ids: '选中项',
  action: '操作'
}

// pydantic 的报错类型 → 中文模板。少数几个高频的翻一下就够，
// 其余原样带出来，总比"请求失败"强。
function explainOne(e) {
  const field = FIELD_CN[String(e.loc?.at(-1) ?? '')] || e.loc?.at(-1) || '有个字段'
  const n = e.ctx?.min_length ?? e.ctx?.max_length
  switch (e.type) {
    case 'missing':
      return `${field}不能为空`
    case 'string_too_short':
      return `${field}太短，至少 ${n} 个字符`
    case 'string_too_long':
      return `${field}太长，最多 ${n} 个字符`
    case 'string_pattern_mismatch':
      return `${field}格式不对`
    case 'int_parsing':
    case 'float_parsing':
      return `${field}要填数字`
    case 'literal_error':
    case 'enum':
      return `${field}只能是 ${(e.ctx?.expected ?? '').toString().replace(/'/g, '')}`
    default:
      return `${field}填得不对：${e.msg || '格式不符合要求'}`
  }
}

/** 把后端的 detail 变成一句能读的中文。422 的 detail 是数组，不能直接显示。 */
export function explainError(err) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    // 一次最多说三条，全列出来会糊一屏
    const msgs = [...new Set(detail.map(explainOne))]
    return msgs.slice(0, 3).join('；') + (msgs.length > 3 ? ` 等 ${msgs.length} 处` : '')
  }
  if (err?.response?.status >= 500) return '服务器出错了，请把这个页面截图发给管理员'
  if (err?.code === 'ERR_NETWORK') return '连不上服务器，检查一下网络或问问管理员'
  return '请求失败，请稍后再试'
}

http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 401) {
      clearAuth() // 清 token 和响应式登录状态，顶栏同步变回未登录
      router.push('/login')
      ElMessage.error('登录已过期，请重新登录')
    } else {
      ElMessage.error(explainError(err))
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
  bulkUsers: (ids, action) => http.post('/auth/users/bulk', { ids, action }),
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

import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from './router'
import { clearAuth, clearStudentAuth } from './auth'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

/**
 * 该带哪个令牌：教师端和学生端是两套身份，各存各的。
 *
 * - /student/* 永远用学生令牌，不看在哪个页面；
 * - 其余接口看当前在哪一侧：/js 开头算教师端，别的算学生端。
 *
 * 公开页面（/take/xxx、/dazi）没登录时两个令牌都没有，就不带 Authorization，
 * 后端按匿名处理 —— 这正是那两个页面要的效果。
 */
function pickToken(url) {
  // 必须带上末尾的斜杠：学生平台是 /student/xxx，教师端的学生管理是 /students，
  // 只写 '/student' 的话 '/students' 也会命中，教师接口就被塞进学生令牌了。
  if (String(url || '').startsWith('/student/')) {
    return localStorage.getItem('studentToken')
  }
  const onTeacherSide = window.location.pathname.startsWith('/js')
  return localStorage.getItem(onTeacherSide ? 'token' : 'studentToken')
}

/**
 * 这台电脑的设备号：打字「每分钟只能交一次、最多换三次文本」按它认电脑（2.11.0）。
 *
 * 不用 IP —— 线上服务器那边，整个机房走一个出口 IP，认 IP 就成了全机房每分钟只能交一次。
 * 存在浏览器里，第一次用的时候随手生成。crypto.randomUUID 只在 https 下有，
 * 机房是 http，所以用 getRandomValues 自己拼。localStorage 用不了（隐私模式）就每次现生成，
 * 大不了这台电脑少受点限制。
 */
function deviceId() {
  try {
    let id = localStorage.getItem('deviceId')
    if (!/^[A-Za-z0-9_-]{8,64}$/.test(id || '')) {
      const bytes = crypto.getRandomValues(new Uint8Array(16))
      id = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
      localStorage.setItem('deviceId', id)
    }
    return id
  } catch {
    return ''
  }
}

http.interceptors.request.use(config => {
  const token = pickToken(config.url)
  if (token) config.headers.Authorization = `Bearer ${token}`
  const dev = deviceId()
  if (dev) config.headers['X-Device-Id'] = dev
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
    // 后台悄悄问的（答题页每 30 秒问一次设置）：出错不弹窗、不踢人，调用方自己吞掉
    if (err.config?.silent) return Promise.reject(err)
    if (err.response?.status === 401) {
      // 在哪一侧就清哪一侧的登录状态，别把另一边的人也踢下线
      if (window.location.pathname.startsWith('/js')) {
        clearAuth()
        router.push('/js/login')
      } else {
        clearStudentAuth()
        router.push('/login')
      }
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
  // ---- 系统管理员：数据备份、一键更新（routers/system.py）
  systemStatus: () => http.get('/system/status'),
  systemJob: id => http.get(`/system/jobs/${id}`, { silent: true, timeout: 10000 }),
  exportBackup: () => http.get('/system/backup/export', { responseType: 'blob', timeout: 0 }),
  importBackup: (file, password, onUploadProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('password', password)
    return http.post('/system/backup/import', fd, { timeout: 0, onUploadProgress })
  },
  updateFromGithub: password => {
    const fd = new FormData()
    fd.append('password', password)
    return http.post('/system/update/github', fd)
  },
  updateFromZip: (file, password, onUploadProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('password', password)
    return http.post('/system/update/upload', fd, { timeout: 0, onUploadProgress })
  },

  // 前后端共用 config.yaml，这里取界面要用的那部分
  siteConfig: () => http.get('/config'),
  // 服务器自己的网卡地址（老师在服务器本机用 localhost 打开后台时拼学生链接用，要登录）
  serverAddresses: () => http.get('/config/addresses'),
  // 全站界面主题、字号（系统管理员，2.22.0）
  uiSave: body => http.put('/config/ui', body),

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

  // 班级：老师能看列表（发考试要选班），增删改要管理员
  classes: params => http.get('/classes', { params }),
  classGrades: () => http.get('/classes/grades'),
  classCreate: data => http.post('/classes', data),
  classBatch: data => http.post('/classes/batch', data),
  classUpdate: (id, data) => http.patch(`/classes/${id}`, data),
  classDelete: (id, force) => http.delete(`/classes/${id}`, { params: { force } }),
  // 批量删班。force 之前后端会先告诉你哪几个班里还有人
  classBulkDelete: (ids, force) => http.post('/classes/bulk', { ids, force }),
  // 批量分配班主任。owner_id 传 null 就是批量取消分配
  classBulkOwner: (ids, owner_id) => http.post('/classes/bulk-owner', { ids, owner_id }),
  // 上机座次表：图片直接打开 seat_url；表格走下载接口（保留上传时的原名）
  classSeatUpload: (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return http.post(`/classes/${id}/seat`, form)
  },
  classSeatDelete: id => http.delete(`/classes/${id}/seat`),
  classSeatFile: id => http.get(`/classes/${id}/seat/file`, { responseType: 'blob' }),
  // 在线座次（2.20.0）：每班一份表格 JSON；排座位只算不存
  classSeatSheet: id => http.get(`/classes/${id}/seat-sheet`),
  classSeatSheetSave: (id, sheet) => http.put(`/classes/${id}/seat-sheet`, { sheet }),
  classSeatSheetDelete: id => http.delete(`/classes/${id}/seat-sheet`),
  classSeatPlan: (id, body) => http.post(`/classes/${id}/seat-plan`, body),
  // 课堂情况日志：在线座次右边那一栏，每次上机一条
  classLogs: id => http.get(`/classes/${id}/logs`),
  classLogCreate: (id, body) => http.post(`/classes/${id}/logs`, body),
  classLogUpdate: (id, lid, body) => http.put(`/classes/${id}/logs/${lid}`, body),
  classLogDelete: (id, lid) => http.delete(`/classes/${id}/logs/${lid}`),
  // 课堂加减分：在线座次里右键学生
  classPoints: id => http.get(`/classes/${id}/points`),
  classPointAdd: (id, body) => http.post(`/classes/${id}/points`, body),
  classPointUndo: (id, pid) => http.delete(`/classes/${id}/points/${pid}`),
  classPointBulk: (id, body) => http.post(`/classes/${id}/points/bulk`, body),

  // 数据回收站：删掉的东西放 7 天，可还原
  recycleList: (kind = '') => http.get('/recycle', { params: { kind } }),
  recycleRestore: ids => http.post('/recycle/restore', { ids }),
  recycleDestroy: ids => http.post('/recycle/destroy', { ids }),
  recycleClear: () => http.delete('/recycle'),

  // 仿真操作题：题面环境 + 检查点。检查点等同于答案，只有教师端拿得到
  sims: params => http.get('/sims', { params }),
  simBlank: kind => http.get('/sims/blank', { params: { kind } }),
  simGet: id => http.get(`/sims/${id}`),
  simCreate: data => http.post('/sims', data),
  simUpdate: (id, data) => http.patch(`/sims/${id}`, data),
  simDelete: id => http.delete(`/sims/${id}`),
  // 老师把题做一遍，拿差异换一份检查点草稿
  simPropose: data => http.post('/sims/propose', data),
  // 试判：拿一份终态跑一遍检查点，存题之前自己验
  simTry: (id, data) => http.post(`/sims/${id}/try`, data),

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
  // 历史试卷多选：批量删（进回收站，连考试一起）、批量导出 zip（fmt: xlsx / html / both）
  bulkDeletePapers: ids => http.post('/papers/bulk-delete', { ids }),
  bulkExportPapers: (ids, fmt) => http.post('/papers/bulk-export', { ids, fmt }, { responseType: 'blob' }),

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
  // 主观题人工赋分：scores 是 {题目id: 得分}
  gradeManual: (id, sid, scores) =>
    http.patch(`/exams/${id}/submissions/${sid}/manual`, { scores }),
  examStats: id => http.get(`/exams/${id}/stats`),
  exportScores: id => http.get(`/exams/${id}/export.xlsx`, { responseType: 'blob' }),
  // 删答卷（要改得动这场考试）：删掉的学生可以重新交卷
  deleteSubmission: (id, sid) => http.delete(`/exams/${id}/submissions/${sid}`),
  deleteSubmissions: (id, ids) => http.post(`/exams/${id}/submissions/delete`, { ids }),
  // 样卷：带答案，只给老师
  examPaper: id => http.get(`/exams/${id}/paper`),
  // 成绩分析：params 可带 classes（逗号分隔班级名）或 students（逗号分隔答卷 id）
  examAnalysis: (id, params = {}) => http.get(`/exams/${id}/analysis`, { params }),
  // 桌面考试包：正常流程用不着（学生端联网自己取卷），这是机房断网时的后路
  exportDeskPack: id =>
    http.get(`/desk/export/${id}`, { params: { server: location.origin }, responseType: 'blob' }),

  // 打字训练
  typingConfig: () => http.get('/typing/config'),
  typingPassage: (mode, difficulty) =>
    http.get('/typing/passage', { params: { mode, difficulty } }),
  typingSubmit: data => http.post('/typing/records', data),
  typingRecords: params => http.get('/typing/records', { params }),
  typingStats: () => http.get('/typing/stats'),
  typingClasses: () => http.get('/typing/classes'),
  typingRosterClasses: () => http.get('/typing/roster-classes'),
  typingCheckStudent: (student_class, student_name) =>
    http.get('/typing/check-student', { params: { student_class, student_name } }),
  // 数组参数要写成 classes=a&classes=b（后端认这种），axios 默认会写成 classes[]=a
  typingExport: (params = {}) => http.get('/typing/export.xlsx', { params, responseType: 'blob' }),
  typingDelete: id => http.delete(`/typing/records/${id}`),
  typingClear: (params = {}) => http.delete('/typing/records', { params }),
  typingSearch: params => http.get('/typing/records/search', { params }),
  typingDeleteMany: ids => http.post('/typing/records/delete', { ids }),
  typingAnalysis: params =>
    http.get('/typing/analysis', { params, paramsSerializer: { indexes: null } }),

  // 打字文本库
  typingTexts: params => http.get('/typing/texts', { params }),
  typingTextStats: () => http.get('/typing/texts/stats'),
  typingTextCreate: data => http.post('/typing/texts', data),
  typingTextUpdate: (id, data) => http.put(`/typing/texts/${id}`, data),
  typingTextDelete: id => http.delete(`/typing/texts/${id}`),
  // extra：改主题时带 { theme_id }
  typingTextBulk: (ids, action, extra = {}) => http.post('/typing/texts/bulk', { ids, action, ...extra }),
  // 主题（学生取文本时先挑一个启用的主题，再只在这个主题里抽段）
  typingThemes: () => http.get('/typing/themes'),
  typingThemeCreate: name => http.post('/typing/themes', { name }),
  typingThemeUpdate: (id, data) => http.put(`/typing/themes/${id}`, data),
  typingThemeDelete: id => http.delete(`/typing/themes/${id}`),

  // 需求反馈（提交与浏览都不需要登录）
  feedbackList: params => http.get('/feedback', { params }),
  feedbackCreate: data => http.post('/feedback', data),
  feedbackAll: () => http.get('/feedback/all'),
  feedbackReply: (id, reply) => http.post(`/feedback/${id}/reply`, { reply }),
  feedbackReplyDelete: rid => http.delete(`/feedback/replies/${rid}`),
  feedbackLike: id => http.post(`/feedback/${id}/like`),
  feedbackPendingCount: () => http.get('/feedback/pending-count'),
  feedbackReview: (id, status, note = '') =>
    http.patch(`/feedback/${id}/review`, { status, note }),
  feedbackReviewBulk: (ids, status) =>
    http.post('/feedback/review-bulk', { ids, status }),
  feedbackUploadImage(file) {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/feedback/images', fd)
  },
  feedbackDelete: id => http.delete(`/feedback/${id}`),

  // 更新日志
  changelog: () => http.get('/changelog'),
  changelogTypes: () => http.get('/changelog/types'),
  changelogLatest: () => http.get('/changelog/latest'),
  changelogCreate: data => http.post('/changelog', data),
  changelogDelete: id => http.delete(`/changelog/${id}`),

  // 学生平台（认学生令牌）
  studentLogin: (student_no, password) =>
    http.post('/student/login', null, { params: { student_no, password } }),
  // 姓名登录：先选班级，账号填中文姓名（重名的填学号）
  studentLoginClasses: () => http.get('/student/classes'),
  studentLoginByName: (name, password, class_id) =>
    http.post('/student/login-by-name', null, { params: { name, password, class_id } }),
  studentMe: () => http.get('/student/me'),
  studentChangePassword: data => http.post('/student/password', data),
  studentHome: () => http.get('/student/home'),
  studentExams: () => http.get('/student/exams'),
  studentPaper: id => http.get(`/student/exams/${id}/paper`),
  studentExamLive: id => http.get(`/student/exams/${id}/live`, { silent: true }),
  studentSubmit: (id, answers) => http.post(`/student/exams/${id}/submit`, { answers }),
  studentTypingRecords: () => http.get('/student/typing/records'),

  // 学生账号管理（教师端）
  students: params => http.get('/students', { params }),
  studentClasses: () => http.get('/students/classes'),
  studentCreate: data => http.post('/students', data),
  studentBatch: data => http.post('/students/batch', data),
  studentUpdate: (id, data) => http.patch(`/students/${id}`, data),
  studentBulk: (ids, action) => http.post('/students/bulk', { ids, action }),
  studentTemplate: () => http.get('/students/template.xlsx', { responseType: 'blob' }),
  studentExport: params =>
    http.get('/students/export.xlsx', { params, responseType: 'blob' }),
  studentImport(file, class_id) {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/students/import', fd, { params: { class_id } })
  },

  // 学生学情：考试、排名、打字、第三方网页数据
  studentInsight: id => http.get(`/students/${id}/insight`),

  // 教师端「API」板块：收第三方教学网页的数据（各老师互不相通，管理员看全部）
  dataApis: params => http.get('/data-apis', { params }),
  dataApiCreate: data => http.post('/data-apis', data),
  dataApi: id => http.get(`/data-apis/${id}`),
  dataApiUpdate: (id, data) => http.put(`/data-apis/${id}`, data),
  dataApiDelete: id => http.delete(`/data-apis/${id}`),
  dataApiRotate: (id, which, enable = true) => http.post(`/data-apis/${id}/rotate-token`, { which, enable }),
  dataApiTransfer: (id, owner_id) => http.post(`/data-apis/${id}/transfer`, { owner_id }),
  dataApiRecords: (id, params) => http.get(`/data-apis/${id}/records`, { params }),
  dataApiFlag: (id, ids, flag) => http.patch(`/data-apis/${id}/records`, { ids, flag }),
  dataApiDeleteRecords: (id, data) => http.post(`/data-apis/${id}/records/delete`, data),
  dataApiSources: id => http.get(`/data-apis/${id}/sources`),
  dataApiStats: (id, params, silent = false) => http.get(`/data-apis/${id}/stats`, { params, silent }),
  dataApiTest: id => http.post(`/data-apis/${id}/test`),
  dataApiPrompt: (id, base) => http.get(`/data-apis/${id}/ai-prompt`, { params: { base } }),
  dataApiExport: (id, params) =>
    http.get(`/data-apis/${id}/export`, { params, responseType: 'blob' }),

  // 凭链接答题（不需要登录）
  takePaper: token => http.get(`/take/${token}`),
  takeLive: token => http.get(`/take/${token}/live`, { silent: true }),
  submitPaper: (token, data) => http.post(`/take/${token}/submit`, data)
}

export default http

<script setup>
/**
 * 课堂情况日志：在线座次右边那一栏（便签样式，不是表格）。
 *
 * 每次上机新建一条：日期、标题（可空）、正文 —— 请假缺勤、设备问题、课堂情况随手记。
 * 存在服务器上（/api/classes/{id}/logs），保存后一直列在右边，最新的在最上面。
 * 看谁都能看；写、改、删只给本班老师和管理员（和座次表一样，后端 _can_seat 拦）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const props = defineProps({
  cls: { type: Object, required: true },
  canEdit: { type: Boolean, default: false },
  students: { type: Array, default: () => [] }     // 本班学生（插缺勤名单用）
})

const logs = ref([])
const loading = ref(false)
const saving = ref(false)
const editingId = ref(null)       // null = 没在写；0 = 新建；其他 = 改这条
const draft = reactive({ lesson_date: '', title: '', content: '' })
const absent = ref([])
let original = ''

const WEEK = '日一二三四五六'
function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function dayLabel(s) {
  const [y, m, d] = String(s).split('-').map(Number)
  const w = new Date(y, m - 1, d).getDay()
  return `${m} 月 ${d} 日 周${WEEK[w]}`
}
const stamp = s => String(s || '').replace('T', ' ').slice(5, 16)

const dirty = computed(
  () => editingId.value !== null && JSON.stringify([draft.lesson_date, draft.title, draft.content]) !== original
)

async function load() {
  loading.value = true
  try {
    logs.value = await api.classLogs(props.cls.id)
  } finally {
    loading.value = false
  }
}

function startNew() {
  const n = logs.value.length + 1
  Object.assign(draft, {
    lesson_date: today(),
    title: `第 ${n} 次上机`,
    content: '请假 / 缺勤：\n设备问题：\n课堂情况：'
  })
  absent.value = []
  editingId.value = 0
  original = JSON.stringify([draft.lesson_date, draft.title, draft.content])
}

function startEdit(log) {
  Object.assign(draft, { lesson_date: log.lesson_date, title: log.title, content: log.content })
  absent.value = []
  editingId.value = log.id
  original = JSON.stringify([draft.lesson_date, draft.title, draft.content])
}

async function cancel() {
  if (dirty.value) {
    await ElMessageBox.confirm('写的内容还没保存，确定不要了？', '课堂日志', { type: 'warning' })
  }
  editingId.value = null
}

/** 选好的缺勤同学写进「请假 / 缺勤：」那一行（没有这一行就加在最前面） */
function insertAbsent() {
  if (!absent.value.length) return
  const names = absent.value.join('、')
  const lines = draft.content.split('\n')
  const i = lines.findIndex(l => /^(请假|缺勤)/.test(l))
  if (i >= 0) {
    const k = lines[i].search(/[:：]/)
    const head = k >= 0 ? lines[i].slice(0, k + 1) : `${lines[i]}：`
    const rest = k >= 0 ? lines[i].slice(k + 1).trim() : ''
    lines[i] = head + (rest ? `${rest}、${names}` : names)
  } else {
    lines.unshift(`请假 / 缺勤：${names}`)
  }
  draft.content = lines.join('\n')
  absent.value = []
}

async function save() {
  if (!draft.lesson_date) return ElMessage.warning('先选上课日期')
  if (!draft.title.trim() && !draft.content.trim()) return ElMessage.warning('标题和内容至少写一样')
  saving.value = true
  try {
    const body = { ...draft }
    if (editingId.value) {
      const got = await api.classLogUpdate(props.cls.id, editingId.value, body)
      logs.value = logs.value.map(l => (l.id === got.id ? got : l))
    } else {
      logs.value.unshift(await api.classLogCreate(props.cls.id, body))
    }
    logs.value.sort((a, b) => (a.lesson_date === b.lesson_date ? b.id - a.id : a.lesson_date < b.lesson_date ? 1 : -1))
    editingId.value = null
    ElMessage.success('日志已保存')
  } finally {
    saving.value = false
  }
}

async function remove(log) {
  await ElMessageBox.confirm(`删掉 ${dayLabel(log.lesson_date)} 这条日志？`, '课堂日志', { type: 'warning' })
  await api.classLogDelete(props.cls.id, log.id)
  logs.value = logs.value.filter(l => l.id !== log.id)
  if (editingId.value === log.id) editingId.value = null
  ElMessage.success('已删除')
}

onMounted(load)
defineExpose({ dirty })
</script>

<template>
  <aside class="logs" v-loading="loading">
    <header class="lhead">
      <b>📝 课堂日志</b>
      <span class="muted">{{ logs.length }} 条</span>
      <div class="flex-1" />
      <el-button v-if="canEdit && editingId === null" type="primary" size="small" @click="startNew">
        + 新建
      </el-button>
    </header>

    <div class="lbody">
      <!-- 正在写的这一条 -->
      <section v-if="editingId !== null" class="note editing">
        <div class="frow">
          <el-date-picker
            v-model="draft.lesson_date"
            type="date"
            value-format="YYYY-MM-DD"
            :clearable="false"
            size="small"
            style="width: 150px; flex: none"
          />
          <el-input v-model="draft.title" size="small" maxlength="64" placeholder="标题（可不写）" />
        </div>
        <el-input
          v-model="draft.content"
          type="textarea"
          :autosize="{ minRows: 5, maxRows: 14 }"
          maxlength="20000"
          placeholder="请假缺勤、设备问题、课堂情况……"
        />
        <div v-if="students.length" class="frow">
          <el-select
            v-model="absent"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            size="small"
            placeholder="选缺勤 / 请假的同学"
            style="flex: 1"
          >
            <el-option v-for="s in students" :key="s.id" :label="s.name" :value="s.name">
              {{ s.name }}<span class="muted">　{{ s.student_no }}</span>
            </el-option>
          </el-select>
          <el-button size="small" :disabled="!absent.length" @click="insertAbsent">写进去</el-button>
        </div>
        <div class="frow end">
          <el-button size="small" @click="cancel">取消</el-button>
          <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
        </div>
      </section>

      <el-empty
        v-if="!loading && !logs.length && editingId === null"
        :image-size="60"
        :description="canEdit ? '还没有日志。每次上机点「+ 新建」记一笔：谁请假、哪台机器坏了……' : '还没有日志'"
      />

      <article v-for="log in logs" v-show="editingId !== log.id" :key="log.id" class="note">
        <div class="ntop">
          <span class="ndate">{{ dayLabel(log.lesson_date) }}</span>
          <span v-if="log.title" class="ntitle">{{ log.title }}</span>
        </div>
        <div v-if="log.content.trim()" class="ntext">{{ log.content }}</div>
        <div class="nfoot">
          <span>{{ log.author_name }} · {{ stamp(log.updated_at) }}</span>
          <div class="flex-1" />
          <template v-if="canEdit && editingId === null">
            <el-button link size="small" type="primary" @click="startEdit(log)">改</el-button>
            <el-button link size="small" type="danger" @click="remove(log)">删</el-button>
          </template>
        </div>
      </article>
    </div>
  </aside>
</template>

<style scoped>
/* 独立的一栏：自己的圆角边框、浅色底，和左边的表格隔开一段，不连在一起 */
.logs {
  flex: 0 0 330px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  background: var(--el-fill-color-lighter);
  overflow: hidden;
}
.lhead {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  font-size: 14px;
}
.lbody {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.flex-1 {
  flex: 1;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
/* 便签：每条一张小卡片，左边一道色条 */
.note {
  padding: 10px 12px;
  border-radius: 8px;
  background: #fffbea;
  border: 1px solid #f3e2a6;
  border-left: 4px solid #e6a23c;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.note.editing {
  background: var(--el-bg-color);
  border-color: var(--el-color-primary-light-5);
  border-left-color: var(--el-color-primary);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.frow {
  display: flex;
  gap: 6px;
  align-items: center;
}
.frow.end {
  justify-content: flex-end;
}
.ntop {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
  margin-bottom: 6px;
}
.ndate {
  font-weight: 700;
  font-size: 13px;
  color: #b26b00;
}
.ntitle {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ntext {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.nfoot {
  display: flex;
  align-items: center;
  margin-top: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.nfoot :deep(.el-button + .el-button) {
  margin-left: 6px;
}
/* 深色模式（Element Plus 在 html 上加 .dark） */
:global(html.dark) .note:not(.editing) {
  background: #3a3320;
  border-color: #5a4c25;
}
:global(html.dark) .ndate {
  color: #f0b75a;
}
</style>

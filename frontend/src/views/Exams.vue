<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { siteConfig } from '../siteConfig'
import { api, download } from '../api'
import { optionText } from '../optionText'
import { loadPublicBase, studentLink } from '../publicUrl'
import { currentUser } from '../auth'
import ClassPicker from '../components/ClassPicker.vue'
import { perQuestion } from '../scoreNote'

// 管理员看得到全校的考试；老师看得到自己的 + 管理员发的（后者只读）。
// 能不能改由后端给的 can_edit 决定，界面只是照着显示 —— 真正拦人的在后端。
const isAdmin = computed(() => currentUser.value?.role === 'admin')

const exams = ref([])
const papers = ref([])
const loading = ref(false)

// 能发给哪些班：老师只列自己名下的，管理员列全校
const myClasses = ref([])

const publishDlg = ref(false)
const form = reactive({
  paper_id: null,
  title: '',
  target_class_ids: [],
  is_open: siteConfig.exam.defaults.is_open,
  allow_retake: siteConfig.exam.defaults.allow_retake,
  show_score: siteConfig.exam.defaults.show_score,
  show_answer: siteConfig.exam.defaults.show_answer,
  early_submit: false,
  // 2.28.0：重考次数（0 = 不限）、交卷频率（rate_window 分钟内最多 rate_max 次，0 = 不限）
  max_attempts: 0,
  rate_window: 0,
  rate_max: 0
})

const router = useRouter()
const current = ref(null) // 正在看成绩的那场考试
const subs = ref([])
const stats = ref(null)

// 成绩表的筛选：按班、按姓名学号搜。都在前端做 —— 一场考试最多几百份，
// 全拿下来再筛比每敲一个字问一次服务器快
const filterClass = ref('')
const keyword = ref('')
// 按交卷时间查（2.27.0）：[起, 止]，两头都是 'YYYY-MM-DD HH:mm:ss'
const timeRange = ref(null)
const subTime = s => String(s.submitted_at || '').replace('T', ' ').slice(0, 19)
/** 班级排序：「七年级2班」排在「七年级10班」前面（数字按大小比） */
const byClass = (a, b) =>
  String(a.student_class || '').localeCompare(String(b.student_class || ''), 'zh-CN', { numeric: true })
const byTime = (a, b) => subTime(a).localeCompare(subTime(b))
const selected = ref([])
const classOptions = computed(() =>
  [...new Set(subs.value.map(s => s.student_class || '未填班级'))].sort()
)
const shownSubs = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  const [from, to] = timeRange.value || []
  return subs.value.filter(s =>
    (!filterClass.value || (s.student_class || '未填班级') === filterClass.value) &&
    (!from || subTime(s) >= from) &&
    (!to || subTime(s) <= to) &&
    (!k ||
      String(s.student_name || '').toLowerCase().includes(k) ||
      String(s.student_no || '').toLowerCase().includes(k))
  )
})

// 样卷
const paperDlg = ref(false)
const paper = ref(null)
const detailDlg = ref(false)
const detail = ref(null)
// 阅卷：{题目id: 老师给的分}。操作题这类机器判不了的题由老师逐题给分，
// 存完总分自动重算，学生那边的分数跟着更新。
const manual = reactive({})
const saving = ref(false)

/** 这份答卷里要老师给分的题 */
const manualItems = computed(() => (detail.value?.detail || []).filter(d => d.manual))
/** 已给的分加起来，对话框顶上实时显示，不用等保存 */
const manualGot = computed(() =>
  manualItems.value.reduce((a, d) => a + (Number(manual[d.id]) || 0), 0)
)
const manualFull = computed(() => manualItems.value.reduce((a, d) => a + (d.score || 0), 0))

function linkOf(exam) {
  return studentLink(`/take/${exam.token}`)
}

async function load() {
  loading.value = true
  try {
    exams.value = await api.exams()
    papers.value = await api.papers()
    // 老师只能发给自己的班，所以下拉里只列自己的；管理员列全校
    myClasses.value = await api.classes(isAdmin.value ? {} : { mine: true })
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  await loadPublicBase()
  await load()
})

function openPublish() {
  if (!papers.value.length) {
    ElMessage.warning('还没有存档的试卷。先去组卷页勾上「把这套卷子存档」再生成一份。')
    return
  }
  Object.assign(form, {
    paper_id: papers.value[0].id,
    title: '',
    target_class_ids: [],
    is_open: siteConfig.exam.defaults.is_open,
    allow_retake: siteConfig.exam.defaults.allow_retake,
    show_score: siteConfig.exam.defaults.show_score,
    show_answer: siteConfig.exam.defaults.show_answer,
    early_submit: false,
    max_attempts: 0,
    rate_window: 0,
    rate_max: 0
  })
  publishDlg.value = true
}

async function publish() {
  const created = await api.createExam({ ...form, title: form.title || null })
  publishDlg.value = false
  await load()
  ElMessage.success('已发布，把链接发给学生就行')
  copy(linkOf(created))
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('链接已复制：' + text)
  } catch {
    // 非 https 或浏览器不允许时退回到手动复制
    ElMessageBox.alert(text, '手动复制这个链接', { confirmButtonText: '知道了' })
  }
}

// 发布后临时加班：学生在平台上只看得到发给自己班的考试，
// 漏发了某个班不用重发一场，在这里把班补上就行（已交的答卷不受影响）
const classDlg = ref(false)
const classForm = reactive({ exam: null, ids: [] })

function editClasses(exam) {
  classForm.exam = exam
  classForm.ids = [...(exam.target_class_ids || [])]
  classDlg.value = true
}

async function saveClasses() {
  await api.updateExam(classForm.exam.id, { target_class_ids: classForm.ids })
  classDlg.value = false
  await load()
  ElMessage.success('发放班级已更新，新加的班学生刷新一下就能看到这场考试')
}

async function toggle(exam, field, value) {
  await api.updateExam(exam.id, { [field]: value })
  await load()
  if (current.value?.id === exam.id) current.value = exams.value.find(e => e.id === exam.id)
}

async function remove(exam) {
  await ElMessageBox.confirm(
    `确定删除《${exam.title}》？已经收到的 ${exam.submission_count} 份答卷会一起删掉。`,
    '提示',
    { type: 'warning' }
  )
  await api.deleteExam(exam.id)
  if (current.value?.id === exam.id) current.value = null
  await load()
  ElMessage.success('已删除')
}

async function openScores(exam) {
  if (current.value?.id !== exam.id) {
    filterClass.value = ''
    keyword.value = ''
    timeRange.value = null
  }
  selected.value = []
  current.value = exam
  subs.value = await api.submissions(exam.id)
  stats.value = await api.examStats(exam.id)
}

/** 成绩分析新开一个标签页：图多，铺满整屏看 */
function openAnalysis(exam) {
  window.open(router.resolve({ path: `/js/analysis/${exam.id}` }).href, '_blank')
}

async function openPaper() {
  paper.value = await api.examPaper(current.value.id)
  durationEdit.value = Number(paper.value.duration) || null
  paperDlg.value = true
}

// 样卷里单独改这场考试的时长（2.28.0）：只改这一场，试卷本身和别的考试不受影响
const durationEdit = ref(null)
async function saveDuration(reset = false) {
  const value = reset ? '' : String(durationEdit.value || '')
  await api.updateExam(current.value.id, { duration: value })
  paper.value = await api.examPaper(current.value.id)
  durationEdit.value = Number(paper.value.duration) || null
  await load()
  current.value = exams.value.find(e => e.id === current.value.id) || current.value
  ElMessage.success(reset ? '已恢复成试卷上的时长' : `考试时长改成 ${value} 分钟，学生刷新后按新时长算`)
}

// 重考次数、交卷频率（2.28.0）：发布后也能改
const ruleDlg = ref(false)
const rule = reactive({ exam: null, allow_retake: false, max_attempts: 0, rate_window: 0, rate_max: 0 })
function openRules(exam) {
  Object.assign(rule, {
    exam,
    allow_retake: exam.allow_retake,
    max_attempts: exam.max_attempts || 0,
    rate_window: exam.rate_window || 0,
    rate_max: exam.rate_max || 0
  })
  ruleDlg.value = true
}
async function saveRules() {
  const { exam, ...body } = rule
  await api.updateExam(exam.id, body)
  ruleDlg.value = false
  await load()
  ElMessage.success('交卷规则已更新')
}
function ruleText(e) {
  const parts = [!e.allow_retake ? '只能交 1 次' : e.max_attempts ? `最多交 ${e.max_attempts} 次` : '重考不限次']
  if (e.rate_window && e.rate_max) parts.push(`每 ${e.rate_window} 分钟最多 ${e.rate_max} 次`)
  return parts.join('，')
}

async function removeSub(row) {
  await ElMessageBox.confirm(
    `删除 ${row.student_name}（${row.student_no || '无学号'}）的答卷？删掉后这个学生可以重新交卷。`,
    '删除答卷',
    { type: 'warning' }
  )
  await api.deleteSubmission(current.value.id, row.id)
  ElMessage.success('已删除')
  await openScores(current.value)
  await load()
}

async function removeSelected() {
  const rows = selected.value
  if (!rows.length) return
  await ElMessageBox.confirm(
    `删除选中的 ${rows.length} 份答卷？删掉后这些学生可以重新交卷，删了找不回来。`,
    '批量删除答卷',
    { type: 'warning', confirmButtonText: `删除 ${rows.length} 份` }
  )
  const res = await api.deleteSubmissions(current.value.id, rows.map(r => r.id))
  ElMessage.success(`已删除 ${res.deleted} 份`)
  await openScores(current.value)
  await load()
}

async function openDetail(row) {
  detail.value = await api.submission(current.value.id, row.id)
  Object.keys(manual).forEach(k => delete manual[k])
  // 已经给过分的回填，没给过的留空（留空和给 0 分是两回事）。
  // 按检查点判过的操作题（d.auto）也回填：全过 / 全没过的系统已经定了分；
  // 部分通过的按比例预填，老师看一眼、点保存就行
  detail.value.detail
    .filter(d => d.manual && (d.graded || d.auto))
    .forEach(d => (manual[d.id] = d.earned))
  detailDlg.value = true
}

async function saveManual() {
  const scores = {}
  for (const d of manualItems.value) {
    const v = manual[d.id]
    if (v === '' || v === null || v === undefined) continue
    if (v > d.score) {
      return ElMessage.warning(`第 ${d.id} 题最多 ${d.score} 分，给多了`)
    }
    scores[d.id] = Number(v)
  }
  saving.value = true
  try {
    const res = await api.gradeManual(current.value.id, detail.value.id, scores)
    ElMessage.success(
      res.pending_manual
        ? `已保存，还有 ${res.pending_manual} 道题没给分`
        : `已评完，这份卷子 ${res.score} 分`
    )
    detailDlg.value = false
    await openScores(current.value)   // 成绩表里的分数立刻跟着变
    await load()                      // 考试列表上的「待阅」也要更新
  } finally {
    saving.value = false
  }
}

async function exportDeskPack(row) {
  // 平时不用点：学生端 exe 联网登录后会自己把卷子取下来。
  // 这个按钮是给"机房网断了"准备的 —— 导出来拷过去，照样能考，考完收 .ans。
  await download(api.exportDeskPack(row.id), `${row.title}.ekb`)
  ElMessage.success('考试包已下载，拷到学生机上和 exe 放一起即可离线开考')
}

/** 错得最多的题导出 Excel：按正确率从低到高，完整题干、选项、正确答案、答错的人最多选了什么 */
async function exportHardest() {
  await download(api.exportHardest(current.value.id), `${current.value.title}_错得最多的题.xlsx`)
}

async function exportScores() {
  await download(api.exportScores(current.value.id), `${current.value.title}_成绩.xlsx`)
  ElMessage.success('已下载成绩汇总')
}

/** 及格没有。卷面总分不一定是 100（老师能改大题分值），所以按比例比。 */
function passed(row) {
  const full = row.full_score || 100
  return row.score / full * 100 >= siteConfig.exam.pass_score
}

const hardest = computed(() => {
  if (!stats.value) return []
  return stats.value.questions
    .filter(q => q.scorable)
    .slice()
    // 抽卷的考试每题作答的人不一样多：没人抽到的不列，同样正确率时作答人多的排前面
    .filter(q => q.right + q.wrong + q.blank > 0)
    .sort((a, b) => a.accuracy - b.accuracy || b.right + b.wrong + b.blank - (a.right + a.wrong + a.blank))
    .slice(0, 20)
})
</script>

<template>
  <el-card shadow="never" class="page-card">
    <template #header>
      <div class="head">
        <span>考试</span>
        <el-button type="primary" size="small" @click="openPublish">发布新考试</el-button>
      </div>
    </template>

    <el-alert type="info" :closable="false" class="hint">
      把存档的试卷发布成考试，学生打开链接直接答题，<b>不需要账号</b>。
      题目发给学生时<b>不带答案</b>，判分在服务器上做，成绩自动汇总。
      <template v-if="isAdmin">
        <br />你是管理员，这里列的是<b>全校所有老师</b>发布的考试。
      </template>
      <template v-else>
        <br />这里列<b>你自己发布的</b>考试，以及<b>管理员发布的</b>（多半是全校统考）。
        管理员发的那几场你可以查成绩、导出，但改不了设置也删不掉；
        别的老师发的考试你看不到，他们也看不到你的。
      </template>
    </el-alert>

    <el-empty v-if="!exams.length && !loading" description="还没有发布过考试" />
    <el-table v-else :data="exams" v-loading="loading" border size="small">
      <el-table-column prop="title" label="考试" min-width="160" show-overflow-tooltip />
      <el-table-column label="发布人" width="110" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.owner_name }}
          <el-tag v-if="!row.can_edit" size="small" type="info" effect="plain" class="ro">只读</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发放班级" min-width="150">
        <template #default="{ row }">
          <span class="cls" :title="row.target_classes">
            {{ row.target_classes ? row.target_classes.split(',').join('、') : '全部' }}
          </span>
          <el-button v-if="row.can_edit" link type="primary" size="small" @click="editClasses(row)">
            加班级
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="学生链接" min-width="230">
        <template #default="{ row }">
          <el-input :model-value="linkOf(row)" readonly size="small">
            <template #append>
              <el-button @click="copy(linkOf(row))">复制</el-button>
            </template>
          </el-input>
        </template>
      </el-table-column>
      <el-table-column label="开放" width="72">
        <template #default="{ row }">
          <el-switch
            :model-value="row.is_open"
            :disabled="!row.can_edit"
            @change="v => toggle(row, 'is_open', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="交卷看分" width="86">
        <template #default="{ row }">
          <el-switch
            :model-value="row.show_score"
            :disabled="!row.can_edit"
            @change="v => toggle(row, 'show_score', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="交卷看答案" width="96">
        <template #default="{ row }">
          <el-switch
            :model-value="row.show_answer"
            :disabled="!row.can_edit"
            @change="v => toggle(row, 'show_answer', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="提前交卷" width="86">
        <template #default="{ row }">
          <el-tooltip content="打开后不受「时间过一半、答完一半的题」限制，随时能交卷" placement="top">
            <el-switch
              :model-value="row.early_submit"
              :disabled="!row.can_edit"
              @change="v => toggle(row, 'early_submit', v)"
            />
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="可重考" width="76">
        <template #default="{ row }">
          <el-tooltip :content="ruleText(row)" placement="top">
            <el-switch
              :model-value="row.allow_retake"
              :disabled="!row.can_edit"
              @change="v => toggle(row, 'allow_retake', v)"
            />
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="交卷" width="76">
        <template #default="{ row }">
          <span :title="`${row.student_count} 人交了 ${row.submission_count} 份`">
            {{ row.student_count }}<span v-if="row.submission_count !== row.student_count" class="of"> 人/{{ row.submission_count }} 份</span>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="待阅" width="72">
        <template #default="{ row }">
          <el-tag v-if="row.ungraded_count" size="small" type="warning" effect="dark">
            {{ row.ungraded_count }}
          </el-tag>
          <span v-else class="nodel">—</span>
        </template>
      </el-table-column>
      <el-table-column label="均分" width="76">
        <template #default="{ row }">
          {{ row.avg_score ?? '—' }}<span v-if="row.full_score" class="of">/{{ row.full_score }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="214" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openScores(row)">成绩</el-button>
          <el-button v-if="row.can_edit" link type="primary" :title="ruleText(row)" @click="openRules(row)">规则</el-button>
          <el-button
            link
            type="primary"
            title="机房断网时的后路：导出来拷到学生机上，和考试客户端 exe 放一个文件夹"
            @click="exportDeskPack(row)"
          >考试包</el-button>
          <el-button
            v-if="row.can_edit"
            link
            type="danger"
            @click="remove(row)"
          >删除</el-button>
          <span v-else class="nodel" title="管理员发布的考试，只能查看成绩">—</span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <!-- 成绩 -->
  <el-card v-if="current" shadow="never">
    <template #header>
      <div class="head">
        <span>{{ current.title }} — 成绩</span>
        <div>
          <el-button size="small" @click="openScores(current)">刷新</el-button>
          <el-button size="small" @click="openPaper">样卷</el-button>
          <el-button size="small" type="success" @click="openAnalysis(current)">成绩分析</el-button>
          <el-button size="small" type="primary" @click="exportScores">导出成绩 Excel</el-button>
        </div>
      </div>
    </template>

    <div v-if="stats" class="kpi">
      <!-- 交卷人数和交卷份数分开（2.28.0）：允许重考时一个人可能交好几份 -->
      <div class="k"><span>交卷人数</span><b>{{ stats.student_count ?? stats.submission_count }}</b></div>
      <div class="k"><span>交卷份数</span><b>{{ stats.submission_count }}</b></div>
      <div class="k"><span>均分</span><b>{{ stats.avg_score ?? '—' }}</b></div>
      <div class="k"><span>最高</span><b>{{ stats.max_score ?? '—' }}</b></div>
      <div class="k"><span>最低</span><b>{{ stats.min_score ?? '—' }}</b></div>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <div class="sub-t">学生成绩</div>
        <el-empty v-if="!subs.length" description="还没有人交卷" :image-size="60" />
        <template v-else>
        <div class="bar">
          <el-select v-model="filterClass" clearable placeholder="全部班级" size="small" style="width: 130px">
            <el-option v-for="c in classOptions" :key="c" :label="c" :value="c" />
          </el-select>
          <el-input
            v-model="keyword"
            clearable
            size="small"
            placeholder="搜姓名或学号"
            style="width: 150px"
          />
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            size="small"
            value-format="YYYY-MM-DD HH:mm:ss"
            range-separator="至"
            start-placeholder="交卷时间起"
            end-placeholder="交卷时间止"
            :default-time="[new Date(2000, 0, 1, 0, 0, 0), new Date(2000, 0, 1, 23, 59, 59)]"
          />
          <span class="of">
            {{ shownSubs.length === subs.length ? `共 ${subs.length} 人` : `筛出 ${shownSubs.length} / ${subs.length} 人` }}
          </span>
          <el-button
            v-if="current.can_edit && selected.length"
            size="small"
            type="danger"
            plain
            @click="removeSelected"
          >删除选中的 {{ selected.length }} 份</el-button>
        </div>
        <el-table
          :data="shownSubs"
          border
          size="small"
          max-height="420"
          row-key="id"
          :default-sort="{ prop: 'score', order: 'descending' }"
          @selection-change="rows => (selected = rows)"
        >
          <el-table-column v-if="current.can_edit" type="selection" width="36" reserve-selection />
          <el-table-column prop="student_name" label="姓名" width="90" />
          <!-- 班级、交卷时间都能点表头升降序（2.27.0） -->
          <el-table-column
            prop="student_class"
            label="班级"
            width="110"
            show-overflow-tooltip
            sortable
            :sort-method="byClass"
          />
          <el-table-column prop="student_no" label="学号" width="110" show-overflow-tooltip />
          <el-table-column prop="score" label="总分" width="84" sortable>
            <template #default="{ row }">
              <b :class="passed(row) ? 'ok' : 'no'">{{ row.score }}</b>
              <span v-if="row.full_score" class="of">/{{ row.full_score }}</span>
            </template>
          </el-table-column>
          <el-table-column label="客观 / 操作" width="118">
            <template #default="{ row }">
              <template v-if="row.full_score">
                {{ row.objective_score }}<span class="of">/{{ row.objective_total }}</span>
                　
                <template v-if="row.subjective_total">
                  {{ row.subjective_score }}<span class="of">/{{ row.subjective_total }}</span>
                  <!-- 批了一半也要把已给的分显示出来，只是标一下还剩几道 -->
                  <span v-if="row.pending_manual" class="no"> 待阅{{ row.pending_manual }}</span>
                </template>
                <span v-else class="of">无操作题</span>
              </template>
              <span v-else class="of">{{ row.right_count }} / {{ row.objective_count }} 题</span>
            </template>
          </el-table-column>
          <el-table-column prop="submitted_at" label="交卷时间" min-width="128" sortable :sort-method="byTime">
            <template #default="{ row }">
              {{ String(row.submitted_at).replace('T', ' ').slice(5, 19) }}
            </template>
          </el-table-column>
          <el-table-column label="" :width="current.can_edit ? 132 : 86">
            <template #default="{ row }">
              <!-- 别的班的答卷只能看，不显示「阅卷」 -->
              <el-button link :type="row.pending_manual && row.can_grade ? 'warning' : 'primary'" @click="openDetail(row)">
                {{ !row.can_grade ? '查看' : row.pending_manual ? '阅卷 ' + row.pending_manual : '答卷' }}
              </el-button>
              <el-button v-if="current.can_edit" link type="danger" @click="removeSub(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        </template>
      </el-col>

      <el-col :span="10">
        <div class="sub-t">
          错得最多的题
          <el-button v-if="hardest.length" link type="primary" size="small" @click="exportHardest">
            导出完整题目（含选项）
          </el-button>
        </div>
        <el-empty v-if="!hardest.length" description="等有人交卷后这里会列出来" :image-size="60" />
        <!-- 题干完整显示、自动折行；题多了表格自己上下滚（2.29.1） -->
        <el-table v-else :data="hardest" border size="small" max-height="460" class="hardest">
          <el-table-column type="index" label="#" width="42" />
          <el-table-column prop="stem" label="题干" min-width="200" />
          <el-table-column prop="answer" label="答案" width="62" />
          <el-table-column label="作答" width="56">
            <template #default="{ row }">{{ row.right + row.wrong + row.blank }}</template>
          </el-table-column>
          <el-table-column label="正确率" width="76">
            <template #default="{ row }">
              <span :class="row.accuracy >= 60 ? 'ok' : 'no'">{{ row.accuracy }}%</span>
            </template>
          </el-table-column>
        </el-table>
        <p class="note">这里列正确率最低的 20 道；「导出完整题目」导出全部作答过的题（完整题干和选项）。</p>
      </el-col>
    </el-row>
  </el-card>

  <!-- 发布 -->
  <el-dialog v-model="publishDlg" title="发布新考试" width="520px">
    <el-form label-width="110px">
      <el-form-item label="选一份试卷">
        <el-select v-model="form.paper_id" style="width: 100%">
          <el-option
            v-for="p in papers"
            :key="p.id"
            :label="`${p.title}　${p.code}　${p.question_count} 题`"
            :value="p.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="考试名称">
        <el-input v-model="form.title" placeholder="留空就用试卷标题" />
      </el-form-item>
      <el-form-item label="发给哪些班">
        <!-- 按年级分行，点年级名一键全选这个年级（2.28.0） -->
        <ClassPicker v-model="form.target_class_ids" :classes="myClasses" />
        <span class="fh">
          <template v-if="isAdmin">不选就是<b>全体学生</b>；选了就只发给这几个班。</template>
          <template v-else>只能选自己带的班。不选就是<b>我带的全部班</b>。</template>
          学生在平台上只看得到发给自己班的考试；<b>凭链接答题不受影响</b>。
        </span>
      </el-form-item>
      <el-form-item label="立即开放">
        <el-switch v-model="form.is_open" />
        <span class="fh">关掉后学生打不开，考试当天再开</span>
      </el-form-item>
      <el-form-item label="交卷看分数">
        <el-switch v-model="form.show_score" />
        <span class="fh">关掉则只提示交卷成功，成绩由老师公布</span>
      </el-form-item>
      <el-form-item label="交卷看答案">
        <el-switch v-model="form.show_answer" />
        <span class="fh">正式考试建议关，否则先考的学生能把答案带出去</span>
      </el-form-item>
      <el-form-item label="允许提前交卷">
        <el-switch v-model="form.early_submit" />
        <span class="fh">默认要考试时间过一半、并且答完一半的题才能交卷；打开后全程随时能交。发布后也能在列表里改</span>
      </el-form-item>
      <el-form-item label="允许重考">
        <el-switch v-model="form.allow_retake" />
        <template v-if="form.allow_retake">
          <span class="fh inl">最多交</span>
          <el-input-number v-model="form.max_attempts" :min="0" :max="99" size="small" style="width: 96px" />
          <span class="fh inl">次（0 = 不限）</span>
        </template>
        <span v-else class="fh">默认同一个人只能交一次</span>
      </el-form-item>
      <el-form-item label="交卷频率">
        <span class="fh inl">每</span>
        <el-select v-model="form.rate_window" size="small" style="width: 104px">
          <el-option label="不限" :value="0" />
          <el-option label="5 分钟" :value="5" />
          <el-option label="10 分钟" :value="10" />
          <el-option label="30 分钟" :value="30" />
          <el-option label="60 分钟" :value="60" />
        </el-select>
        <template v-if="form.rate_window">
          <span class="fh inl">最多交</span>
          <el-input-number v-model="form.rate_max" :min="1" :max="99" size="small" style="width: 96px" />
          <span class="fh inl">次</span>
        </template>
        <span class="fh">超了提示「提交次数过多，请等多久后再交卷」，作答不丢</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="publishDlg = false">取消</el-button>
      <el-button type="primary" @click="publish">发布并复制链接</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="classDlg" :title="`发放班级 · ${classForm.exam?.title || ''}`" width="480px">
    <ClassPicker v-model="classForm.ids" :classes="myClasses" />
    <p class="fh">{{ isAdmin ? '一个都不选 = 全体学生' : '一个都不选 = 我带的全部班' }}</p>
    <p class="fh">
      考试已经发布也能改：勾上新的班，那个班的学生就能在平台上看到并参加这场考试；
      已经交卷的答卷、成绩都不受影响。<template v-if="!isAdmin">只能选自己带的班。</template>
    </p>
    <template #footer>
      <el-button @click="classDlg = false">取消</el-button>
      <el-button type="primary" @click="saveClasses">保存</el-button>
    </template>
  </el-dialog>

  <!-- 样卷：带答案，老师看。样式和组卷页的卷面一样（2.28.0），这里还能单独改这场考试的时长 -->
  <el-dialog v-model="paperDlg" :title="`样卷 · ${paper?.title || ''}`" width="860px" top="4vh">
    <div v-if="paper" class="paper">
      <div class="paper-head">
        <h1>{{ paper.paper_title || paper.title }}</h1>
        <div class="meta">
          <span v-if="paper.school">{{ paper.school }}　·　</span>
          <span>考试时长 {{ paper.duration || '—' }} 分钟　·　</span>
          <span>满分 {{ paper.full_score }} 分</span>
          <span v-if="paper.code">　·　{{ paper.code }}</span>
        </div>
      </div>
      <div v-if="current?.can_edit" class="durbar">
        <span>这场考试的时长</span>
        <el-input-number v-model="durationEdit" :min="1" :max="600" size="small" style="width: 120px" />
        <span>分钟</span>
        <el-button size="small" type="primary" :disabled="!durationEdit" @click="saveDuration(false)">保存</el-button>
        <el-button
          v-if="paper.paper_duration && paper.duration !== paper.paper_duration"
          size="small"
          link
          @click="saveDuration(true)"
        >恢复试卷上的 {{ paper.paper_duration }} 分钟</el-button>
        <span class="fh">只改这一场考试，试卷和别的考试不受影响；考试中途改了，学生刷新后按新时长</span>
      </div>
      <template v-for="(g, gi) in paper.groups" :key="g.name">
        <div class="sect">
          <h2>
            {{ ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'][gi] || gi + 1 }}、{{ g.name }}（共 {{ g.items.length }} 题<template
              v-if="g.score"
            >，{{ perQuestion(g.items) }}，共 {{ g.score }} 分</template>）
          </h2>
        </div>
        <div v-for="q in g.items" :key="q.id" class="q">
          <div class="q-stem">
            <span class="q-no">{{ q.no }}.</span>{{ q.stem }}
            <span v-if="q.score" class="pt">（{{ q.score }} 分）</span>
          </div>
          <img v-if="q.image_url" :src="q.image_url" class="q-img" alt="题目配图" />
          <div v-if="q.options.length" class="opts flat">
            <span
              v-for="o in q.options"
              :key="o.label"
              class="op-flat"
              :class="{ right: String(q.answer).includes(o.label) && q.type === '选择题' }"
            >
              <span class="L">{{ o.label }}</span>{{ o.content }}
            </span>
          </div>
          <div v-if="q.answer" class="ans">答案：<b>{{ optionText(q.options, q.answer) }}</b></div>
          <div v-if="q.checks.length" class="checks">
            <span v-for="(c, i) in q.checks" :key="i" class="chip">判分点 {{ i + 1 }}：{{ c }}</span>
          </div>
          <div class="q-tag">
            <span v-if="q.scope" class="tag k">{{ q.scope }}</span>
            <span class="tag">{{ q.type }}</span>
          </div>
        </div>
      </template>
    </div>
    <template #footer>
      <el-button @click="paperDlg = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 交卷规则：重考次数、交卷频率（2.28.0） -->
  <el-dialog v-model="ruleDlg" :title="`交卷规则 · ${rule.exam?.title || ''}`" width="500px">
    <el-form label-width="90px">
      <el-form-item label="允许重考">
        <el-switch v-model="rule.allow_retake" />
        <template v-if="rule.allow_retake">
          <span class="fh inl">最多交</span>
          <el-input-number v-model="rule.max_attempts" :min="0" :max="99" size="small" style="width: 96px" />
          <span class="fh inl">次（0 = 不限）</span>
        </template>
        <span v-else class="fh inl">一个人只能交 1 次</span>
      </el-form-item>
      <el-form-item label="交卷频率">
        <span class="fh inl">每</span>
        <el-select v-model="rule.rate_window" size="small" style="width: 104px">
          <el-option label="不限" :value="0" />
          <el-option label="5 分钟" :value="5" />
          <el-option label="10 分钟" :value="10" />
          <el-option label="30 分钟" :value="30" />
          <el-option label="60 分钟" :value="60" />
        </el-select>
        <template v-if="rule.rate_window">
          <span class="fh inl">最多交</span>
          <el-input-number v-model="rule.rate_max" :min="1" :max="99" size="small" style="width: 96px" />
          <span class="fh inl">次</span>
        </template>
      </el-form-item>
      <p class="fh">
        超出次数：提示交满了、请联系老师；超出频率：提示「提交次数过多，请等多久后再交卷」。两种情况学生的作答都不丢、页面不刷新。
      </p>
    </el-form>
    <template #footer>
      <el-button @click="ruleDlg = false">取消</el-button>
      <el-button type="primary" @click="saveRules">保存</el-button>
    </template>
  </el-dialog>

  <!-- 单份答卷 + 主观题阅卷 -->
  <el-dialog v-model="detailDlg" title="学生答卷" width="760px" top="6vh">
    <template v-if="detail">
      <p class="who">
        {{ detail.student_name }}　{{ detail.student_class }}　{{ detail.student_no }}
        <template v-if="detail.full_score">
          　总分 <b>{{ detail.score }}</b><span class="of">/{{ detail.full_score }}</span>
          （客观 {{ detail.objective_score }}<span class="of">/{{ detail.objective_total }}</span>
          <template v-if="detail.subjective_total">
            　操作题 {{ manualGot }}<span class="of">/{{ manualFull }}</span>
          </template>）
        </template>
        <template v-else>
          　得分 <b>{{ detail.score }}</b>（答对 {{ detail.right_count }} / {{ detail.objective_count }}）
        </template>
        <span v-if="detail.graded_by_name" class="of">　{{ detail.graded_by_name }} 已评阅</span>
      </p>

      <el-alert v-if="manualItems.length && !detail.can_grade" type="info" :closable="false" class="hint">
        这份答卷是「{{ detail.student_class || '未填班级' }}」的，不是你带的班，<b>只能查看，不能评分</b>；请该班老师批改。
      </el-alert>
      <el-alert v-else-if="manualItems.length" type="warning" :closable="false" class="hint">
        下面带输入框的是<b>操作题</b>。按检查点判过的：<b>全部通过的已经给了满分、全部没过的给了 0 分</b>，
        不用再管；部分通过的按比例预填了分数，看一眼没问题就保存（觉得不对可以改）。
        没挂仿真的机器判不了，要你看着作答给分。
        给完保存，总分自动重算，学生在「我的考试」里就能看到更新后的分数。
        留空表示<b>还没评</b>，和给 0 分不是一回事。
      </el-alert>

      <div v-for="(d, i) in detail.detail" :key="d.id" class="dq" :class="{ pend: d.manual }">
        <div class="dstem">
          {{ i + 1 }}. {{ d.stem }}
          <span v-if="d.score" class="of">（{{ d.score }} 分）</span>
          <el-tag v-if="d.auto" size="small" type="success" effect="plain">
            自动判分 {{ d.check_passed }}/{{ d.check_total }} 问
          </el-tag>
          <el-tag v-if="d.auto_graded" size="small" type="success">
            {{ d.earned >= d.score ? '检查点全过，已自动给满分' : '检查点全没过，已自动给 0 分' }}
          </el-tag>
          <el-tag v-else-if="d.manual && d.auto && !d.graded" size="small" type="warning">
            部分通过，已按比例预填，待复核
          </el-tag>
          <el-tag v-else-if="d.manual" size="small" :type="manual[d.id] === undefined ? 'warning' : 'success'">
            {{ manual[d.id] === undefined ? '待评阅' : '已给分' }}
          </el-tag>
          <el-tag v-else-if="!d.scored" size="small" type="info">不计分</el-tag>
          <el-tag v-else-if="d.ok" size="small" type="success">✓ {{ d.earned || '' }}</el-tag>
          <el-tag v-else size="small" type="danger">✕</el-tag>
        </div>
        <!-- 仿真题：机器按检查点判过了，把每一问的结果摆出来，扣在哪一眼看清。
             这类题的原始作答是一大段 JSON，显示出来没人看得懂，所以不显示。 -->
        <div v-if="d.checks" class="checks">
          <span v-for="c in d.checks" :key="c.no" class="chip" :class="{ no: !c.ok }">
            {{ c.ok ? '✓' : '✕' }} {{ c.desc }}
            <em v-if="!c.ok">（{{ c.why }}）</em>
          </span>
        </div>
        <div v-else class="dans">
          学生作答：<span :class="d.scored && !d.ok ? 'no' : ''">{{ optionText(d.options, d.mine) || '未作答' }}</span>
          <template v-if="d.answer">　参考答案：<b>{{ optionText(d.options, d.answer) }}</b></template>
        </div>
        <div v-if="d.manual" class="grade">
          <span>给分</span>
          <el-input-number
            v-model="manual[d.id]"
            :min="0"
            :max="d.score"
            :disabled="!detail.can_grade"
            size="small"
            controls-position="right"
            style="width: 96px"
          />
          <span class="of">/ {{ d.score }} 分</span>
          <template v-if="detail.can_grade">
            <el-button link size="small" @click="manual[d.id] = d.score">给满分</el-button>
            <el-button link size="small" @click="manual[d.id] = 0">给 0 分</el-button>
          </template>
        </div>
      </div>
    </template>
    <template #footer>
      <span v-if="manualItems.length" class="foot-sum">
        操作题合计 <b>{{ manualGot }}</b> / {{ manualFull }} 分
      </span>
      <el-button @click="detailDlg = false">关闭</el-button>
      <el-button
        v-if="manualItems.length && detail.can_grade"
        type="primary"
        :loading="saving"
        @click="saveManual"
      >保存评分</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.hint {
  margin-bottom: 14px;
}
.ro {
  margin-left: 4px;
}
.nodel {
  color: var(--el-text-color-placeholder);
  margin-left: 8px;
}
/* 样卷：和组卷页同一套卷面样式 */
.paper-head {
  text-align: center;
  margin: 4px 0 10px;
}
.paper-head h1 {
  margin: 0 0 6px;
  font-size: 21px;
  font-family: 'Heiti SC', 'SimHei', 'Microsoft YaHei', sans-serif;
  letter-spacing: 0.05em;
}
.paper .meta {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.durbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 8px 0 14px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  font-size: 13px;
}
.paper .sect {
  margin: 22px 0 10px;
}
.paper .sect h2 {
  margin: 0;
  font-size: 16px;
  font-family: 'Heiti SC', 'SimHei', 'Microsoft YaHei', sans-serif;
}
.paper .q {
  margin-bottom: 14px;
  line-height: 1.85;
}
.q-no {
  font-weight: 600;
  margin-right: 5px;
}
.q-stem {
  white-space: pre-wrap;
}
.q-img {
  display: block;
  max-width: 360px;
  margin: 8px 0 4px 20px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
}
.paper .opts {
  margin: 4px 0 0 20px;
}
.paper .opts.flat {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 24px;
}
.op-flat {
  min-width: 42%;
}
.op-flat.right {
  color: var(--el-color-success);
  font-weight: 600;
}
.paper .L {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-right: 6px;
}
.paper .ans {
  margin: 6px 0 0 20px;
  color: var(--el-color-danger);
  font-size: 13.5px;
}
.paper .pt {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
  white-space: nowrap;
}
.q-tag {
  margin: 4px 0 0 20px;
  display: flex;
  gap: 6px;
}
.paper .tag {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 0 6px;
}
.paper .tag.k {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
}
.fh.inl {
  margin: 0 6px;
}
.kpi {
  display: flex;
  gap: 26px;
  margin-bottom: 14px;
}
.k span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-right: 8px;
}
.k b {
  font-size: 20px;
  font-family: ui-monospace, Consolas, monospace;
}
.sub-t {
  font-weight: 600;
  margin-bottom: 8px;
}
.ok {
  color: var(--el-color-success);
}
.no {
  color: var(--el-color-danger);
}
.note {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 8px;
}
.fh {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 10px;
}
.who {
  margin: 0 0 12px;
}
.dq {
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 8px 0;
}
.dstem {
  line-height: 1.7;
}
.dans {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 3px;
  white-space: pre-wrap;
}
/* 要阅的题左边留一道竖线，一眼看得出哪些等着给分 */
.dq.pend {
  border-left: 3px solid var(--el-color-warning);
  padding-left: 10px;
  background: var(--el-color-warning-light-9);
}
.grade {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 13px;
}
.of {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.foot-sum {
  float: left;
  line-height: 32px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.checks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}
.checks .chip {
  background: var(--el-color-success-light-9);
  border: 1px solid var(--el-color-success-light-7);
  border-radius: 10px;
  padding: 1px 9px;
  font-size: 12px;
}
.checks .chip.no {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger-light-7);
  color: var(--el-color-danger);
}
.checks .chip em { font-style: normal; opacity: 0.85; }
.bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.pg {
  margin-bottom: 10px;
}
.pg-h {
  font-weight: 600;
  margin: 10px 0 2px;
}
.opts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  font-size: 13px;
  margin-top: 4px;
}
.opts .right {
  color: var(--el-color-success);
  font-weight: 600;
}
.qimg {
  max-width: 100%;
  max-height: 240px;
  margin-top: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.cls { margin-right: 6px; }
</style>

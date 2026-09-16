<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { siteConfig } from '../siteConfig'
import { api, download } from '../api'
import { loadPublicBase, studentLink } from '../publicUrl'
import { currentUser } from '../auth'

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
  show_answer: siteConfig.exam.defaults.show_answer
})

const current = ref(null) // 正在看成绩的那场考试
const subs = ref([])
const stats = ref(null)
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
    show_answer: siteConfig.exam.defaults.show_answer
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
  current.value = exam
  subs.value = await api.submissions(exam.id)
  stats.value = await api.examStats(exam.id)
}

async function openDetail(row) {
  detail.value = await api.submission(current.value.id, row.id)
  Object.keys(manual).forEach(k => delete manual[k])
  // 已经给过分的回填，没给过的留空（留空和给 0 分是两回事）
  detail.value.detail
    .filter(d => d.manual && d.graded)
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
    .sort((a, b) => a.accuracy - b.accuracy)
    .slice(0, 5)
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
      <el-table-column label="可重考" width="76">
        <template #default="{ row }">
          <el-switch
            :model-value="row.allow_retake"
            :disabled="!row.can_edit"
            @change="v => toggle(row, 'allow_retake', v)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="submission_count" label="交卷" width="64" />
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
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openScores(row)">成绩</el-button>
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
          <el-button size="small" type="primary" @click="exportScores">导出成绩 Excel</el-button>
        </div>
      </div>
    </template>

    <div v-if="stats" class="kpi">
      <div class="k"><span>交卷</span><b>{{ stats.submission_count }}</b></div>
      <div class="k"><span>均分</span><b>{{ stats.avg_score ?? '—' }}</b></div>
      <div class="k"><span>最高</span><b>{{ stats.max_score ?? '—' }}</b></div>
      <div class="k"><span>最低</span><b>{{ stats.min_score ?? '—' }}</b></div>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <div class="sub-t">学生成绩</div>
        <el-empty v-if="!subs.length" description="还没有人交卷" :image-size="60" />
        <el-table v-else :data="subs" border size="small" max-height="420">
          <el-table-column prop="student_name" label="姓名" width="90" />
          <el-table-column prop="student_class" label="班级" width="110" show-overflow-tooltip />
          <el-table-column prop="student_no" label="学号" width="110" show-overflow-tooltip />
          <el-table-column label="总分" width="84">
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
          <el-table-column label="交卷时间" min-width="120">
            <template #default="{ row }">
              {{ String(row.submitted_at).replace('T', ' ').slice(5, 19) }}
            </template>
          </el-table-column>
          <el-table-column label="" width="86">
            <template #default="{ row }">
              <el-button link :type="row.pending_manual ? 'warning' : 'primary'" @click="openDetail(row)">
                {{ row.pending_manual ? '阅卷 ' + row.pending_manual : '答卷' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-col>

      <el-col :span="10">
        <div class="sub-t">错得最多的题</div>
        <el-empty v-if="!hardest.length" description="等有人交卷后这里会列出来" :image-size="60" />
        <el-table v-else :data="hardest" border size="small">
          <el-table-column prop="stem" label="题干" show-overflow-tooltip />
          <el-table-column prop="answer" label="答案" width="66" />
          <el-table-column label="正确率" width="76">
            <template #default="{ row }">
              <span :class="row.accuracy >= 60 ? 'ok' : 'no'">{{ row.accuracy }}%</span>
            </template>
          </el-table-column>
        </el-table>
        <p class="note">完整的每题分析在导出的 Excel 第二张表里。</p>
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
        <el-select
          v-model="form.target_class_ids"
          multiple
          collapse-tags
          collapse-tags-tooltip
          :placeholder="isAdmin ? '不选 = 全体学生' : '不选 = 我带的全部班'"
          style="width: 100%"
        >
          <el-option v-for="c in myClasses" :key="c.id" :label="c.display" :value="c.id" />
        </el-select>
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
      <el-form-item label="允许重考">
        <el-switch v-model="form.allow_retake" />
        <span class="fh">默认同一学号只能交一次</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="publishDlg = false">取消</el-button>
      <el-button type="primary" @click="publish">发布并复制链接</el-button>
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

      <el-alert v-if="manualItems.length" type="warning" :closable="false" class="hint">
        下面带输入框的是<b>操作题</b>。挂了仿真任务的已经按检查点自动判过分，分数填在框里了，
        你觉得不对可以改；没挂仿真的机器判不了，要你看着作答给分。
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
          <el-tag v-if="d.manual" size="small" :type="manual[d.id] === undefined ? 'warning' : 'success'">
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
          学生作答：<span :class="d.scored && !d.ok ? 'no' : ''">{{ d.mine || '未作答' }}</span>
          <template v-if="d.answer">　参考答案：<b>{{ d.answer }}</b></template>
        </div>
        <div v-if="d.manual" class="grade">
          <span>给分</span>
          <el-input-number
            v-model="manual[d.id]"
            :min="0"
            :max="d.score"
            size="small"
            controls-position="right"
            style="width: 96px"
          />
          <span class="of">/ {{ d.score }} 分</span>
          <el-button link size="small" @click="manual[d.id] = d.score">给满分</el-button>
          <el-button link size="small" @click="manual[d.id] = 0">给 0 分</el-button>
        </div>
      </div>
    </template>
    <template #footer>
      <span v-if="manualItems.length" class="foot-sum">
        操作题合计 <b>{{ manualGot }}</b> / {{ manualFull }} 分
      </span>
      <el-button @click="detailDlg = false">关闭</el-button>
      <el-button
        v-if="manualItems.length"
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

</style>

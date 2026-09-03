<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { siteConfig } from '../siteConfig'
import { api, download } from '../api'

const exams = ref([])
const papers = ref([])
const loading = ref(false)

const publishDlg = ref(false)
const form = reactive({
  paper_id: null,
  title: '',
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

function linkOf(exam) {
  return `${location.origin}/take/${exam.token}`
}

async function load() {
  loading.value = true
  try {
    exams.value = await api.exams()
    papers.value = await api.papers()
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openPublish() {
  if (!papers.value.length) {
    ElMessage.warning('还没有存档的试卷。先去组卷页勾上「把这套卷子存档」再生成一份。')
    return
  }
  Object.assign(form, {
    paper_id: papers.value[0].id,
    title: '',
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
  detailDlg.value = true
}

async function exportScores() {
  await download(api.exportScores(current.value.id), `${current.value.title}_成绩.xlsx`)
  ElMessage.success('已下载成绩汇总')
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
    </el-alert>

    <el-empty v-if="!exams.length && !loading" description="还没有发布过考试" />
    <el-table v-else :data="exams" v-loading="loading" border size="small">
      <el-table-column prop="title" label="考试" min-width="160" show-overflow-tooltip />
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
            @change="v => toggle(row, 'is_open', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="交卷看分" width="86">
        <template #default="{ row }">
          <el-switch :model-value="row.show_score" @change="v => toggle(row, 'show_score', v)" />
        </template>
      </el-table-column>
      <el-table-column label="交卷看答案" width="96">
        <template #default="{ row }">
          <el-switch :model-value="row.show_answer" @change="v => toggle(row, 'show_answer', v)" />
        </template>
      </el-table-column>
      <el-table-column label="可重考" width="76">
        <template #default="{ row }">
          <el-switch :model-value="row.allow_retake" @change="v => toggle(row, 'allow_retake', v)" />
        </template>
      </el-table-column>
      <el-table-column prop="submission_count" label="交卷" width="64" />
      <el-table-column label="均分" width="66">
        <template #default="{ row }">{{ row.avg_score ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openScores(row)">成绩</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
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
          <el-table-column label="得分" width="70">
            <template #default="{ row }">
              <b :class="row.score >= siteConfig.exam.pass_score ? 'ok' : 'no'">{{ row.score }}</b>
            </template>
          </el-table-column>
          <el-table-column label="答对" width="80">
            <template #default="{ row }">{{ row.right_count }} / {{ row.objective_count }}</template>
          </el-table-column>
          <el-table-column label="交卷时间" min-width="130">
            <template #default="{ row }">
              {{ String(row.submitted_at).replace('T', ' ').slice(5, 19) }}
            </template>
          </el-table-column>
          <el-table-column label="" width="60">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row)">答卷</el-button>
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

  <!-- 单份答卷 -->
  <el-dialog v-model="detailDlg" title="学生答卷" width="720px">
    <template v-if="detail">
      <p class="who">
        {{ detail.student_name }}　{{ detail.student_class }}　{{ detail.student_no }}
        得分 <b>{{ detail.score }}</b>（答对 {{ detail.right_count }} / {{ detail.objective_count }}）
      </p>
      <div v-for="(d, i) in detail.detail" :key="d.id" class="dq">
        <div class="dstem">
          {{ i + 1 }}. {{ d.stem }}
          <el-tag v-if="!d.scored" size="small" type="warning">
            {{ d.type === '操作题' ? '需人工评阅' : '不计分' }}
          </el-tag>
          <el-tag v-else-if="d.ok" size="small" type="success">✓</el-tag>
          <el-tag v-else size="small" type="danger">✕</el-tag>
        </div>
        <div class="dans">
          学生作答：<span :class="d.scored && !d.ok ? 'no' : ''">{{ d.mine || '未作答' }}</span>
          <template v-if="d.answer">　参考答案：<b>{{ d.answer }}</b></template>
        </div>
      </div>
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
</style>

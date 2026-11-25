<script setup>
/**
 * 学生平台里的答题页。
 *
 * 和 /take/:token 那个公开页最大的不同：**身份来自账号**，学生不用也不能
 * 填姓名班级 —— 交卷时后端直接按令牌里的学生写库，成绩不会张冠李戴。
 * 相同的一点：这个页面永远拿不到答案，取卷接口不下发，判分在后端做。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api'
import { optionText } from '../../optionText'
import { applyShuffle } from '../../shuffle'
import { currentStudent } from '../../auth'
import { useSubmitGate } from '../../submitGate'
import SimHost from '../../components/sim/SimHost.vue'
import ObjectiveAnswer from '../../components/ObjectiveAnswer.vue'
import { useExamGuard } from '../../examGuard'
import { perQuestion } from '../../scoreNote'

const CN = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const route = useRoute()
const router = useRouter()
const examId = route.params.id

const me = currentStudent
const paper = ref(null)
const loadError = ref('')
const loading = ref(true)
const submitting = ref(false)
const result = ref(null)
const answers = reactive({})

// 临时保存（2.28.0）：作答存在这台电脑上，交卷前刷新原样回来；交卷成功就删掉。
// 学生平台的题序按「考试 + 学号」固定，刷新本来就不变，存的只是作答
const SAVE_KEY = `exam-save-${examId}-${currentStudent.value?.student_no || ''}`
const savedAt = ref('')
function tempSave() {
  if (!paper.value || result.value) return
  const now = new Date()
  const at = [now.getHours(), now.getMinutes(), now.getSeconds()].map(n => String(n).padStart(2, '0')).join(':')
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify({ answers: { ...answers }, at }))
    savedAt.value = at
    ElMessage.success('已临时保存：交卷前刷新页面，已选内容不变')
  } catch {
    ElMessage.error('这台电脑的浏览器存不了（可能开着无痕模式），请直接作答交卷')
  }
}
function restoreSave() {
  try {
    const saved = JSON.parse(localStorage.getItem(SAVE_KEY) || 'null')
    if (!saved) return
    const ids = new Set(paper.value.groups.flatMap(g => g.items.map(q => String(q.id))))
    Object.entries(saved.answers || {}).forEach(([k, v]) => ids.has(String(k)) && (answers[k] = v))
    savedAt.value = saved.at || ''
  } catch {
    /* 存的东西坏了就当没有 */
  }
}
function clearSave() {
  try {
    localStorage.removeItem(SAVE_KEY)
  } catch {
    /* 无痕模式 */
  }
}

// 防开发者工具、防脚本代答（examGuard.js）
const { tampered } = useExamGuard()

/** 交卷当场只算得出客观题那一段，标题就照实说，别让学生以为总分就这么多。 */
const resultTitle = computed(() => {
  const r = result.value
  if (!r || r.score === null || r.score === undefined) return '交卷成功'
  if (r.full_score && r.pending_manual) return `客观题得分 ${r.objective_score} / ${r.objective_total}`
  return r.full_score ? `得分 ${r.score} / ${r.full_score}` : `得分 ${r.score}`
})

const resultIcon = computed(() => {
  const r = result.value
  if (!r || r.score === null || r.score === undefined || r.pending_manual) return 'success'
  const full = r.full_score || 100
  return (r.score / full) * 100 >= 60 ? 'success' : 'info'
})

const numbering = computed(() => {
  const map = {}
  let n = 0
  ;(paper.value?.groups || []).forEach(g => g.items.forEach(q => (map[q.id] = ++n)))
  return map
})

const answered = computed(() => Object.values(answers).filter(v => String(v || '').trim()).length)
// 交卷门槛：考试时间过一半、且答完一半的题
const gate = useSubmitGate(`student-${examId}`, paper, answered, () => api.studentExamLive(examId))

/** 交卷后按题号取回判分明细（老师开了「显示答案」才有） */
const detailOf = computed(() => {
  const map = {}
  ;(result.value?.detail || []).forEach(d => (map[d.id] = d))
  return map
})

onMounted(async () => {
  try {
    // 选择判断题乱序：按「考试 + 学号」打乱，刷新、换台电脑登录都是同一套顺序
    paper.value = applyShuffle(await api.studentPaper(examId),
      `exam-${examId}-${me.value?.student_no || ''}`)
    restoreSave()
    gate.start()
  } catch (e) {
    loadError.value = e.response?.data?.detail || '打不开这场考试，回列表看看还在不在'
  } finally {
    loading.value = false
  }
})

const asking = ref(false)

async function submit() {
  // 学生紧张时容易连点，挡住重复弹窗和重复提交
  if (asking.value || submitting.value || result.value) return
  if (!gate.canSubmit.value) {
    // 被门槛拦住时当场再问一次：老师刚打开「允许提前交卷」，不用等下一个 60 秒
    await gate.sync()
  }
  if (!gate.canSubmit.value) {
    ElMessage.warning(gate.reason.value)
    return
  }

  if (tampered.value) {
    ElMessage.error('检测到开发者工具开着，关掉以后才能交卷')
    return
  }

  const blank = paper.value.total - answered.value
  if (blank > 0) {
    asking.value = true
    try {
      await ElMessageBox.confirm(
        `还有 ${blank} 道题没做，确定要交卷吗？交卷后不能再改。`,
        '确认交卷',
        { type: 'warning', confirmButtonText: '确定交卷', cancelButtonText: '再检查一下' }
      )
    } catch {
      return
    } finally {
      asking.value = false
    }
  }

  submitting.value = true
  try {
    result.value = await api.studentSubmit(examId, answers)
    clearSave()
    gate.done()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } finally {
    submitting.value = false
  }
}

function back() {
  if (!result.value && answered.value > 0) {
    return ElMessageBox.confirm('还没交卷，现在离开这些作答就没了。确定要走吗？', '提示', {
      type: 'warning',
      confirmButtonText: '离开',
      cancelButtonText: '继续答题'
    }).then(() => router.push('/exam'))
  }
  router.push('/exam')
}
</script>

<template>
  <div class="wrap" v-loading="loading">
    <!-- 开发者工具开着：盖住整页，不让交卷（examGuard.js） -->
    <!-- 剩余答题时间：左下角固定显示（2.29.0） -->
    <div v-if="paper && !result && gate.remainText.value" class="clock" :class="{ late: gate.remaining.value < 300 }">
      {{ gate.remainText.value }}
    </div>
    <div v-if="tampered && !result" class="guard">
      检测到开发者工具（F12）开着。<br />考试期间不能用，请关掉它，关掉后自动恢复答题。
    </div>
    <el-result v-if="loadError" icon="warning" title="无法进入考试" :sub-title="loadError">
      <template #extra>
        <el-button type="primary" @click="router.push('/exam')">返回考试列表</el-button>
      </template>
    </el-result>

    <template v-else-if="paper">
      <!-- 卷头 -->
      <div class="head">
        <h1>{{ paper.title }}</h1>
        <div class="meta">
          <span v-if="paper.school">{{ paper.school }}　·　</span>
          <span v-if="paper.duration">{{ paper.duration }} 分钟　·　</span>
          <span v-if="paper.full_score">满分 {{ paper.full_score }} 分　·　</span>
          <span>{{ paper.code }}</span>
        </div>
        <!-- 身份从账号来，学生改不了，所以只显示不给编辑 -->
        <div class="who">
          <span class="idcard">{{ me?.name }}</span>
          <span class="idcard">{{ me?.student_class || '未分班' }}</span>
          <span class="idcard">学号 {{ me?.student_no }}</span>
        </div>
      </div>

      <!-- 交卷结果 -->
      <el-result v-if="result" :icon="resultIcon" :title="resultTitle">
        <template #sub-title>
          <p class="rsub">{{ result.message }}</p>
          <p v-if="result.full_score" class="rsub">
            客观题 <b>{{ result.objective_score }}</b> / {{ result.objective_total }} 分
            （答对 {{ result.right_count }} / {{ result.objective_count }} 题）
            <template v-if="result.subjective_total">
              　·　操作题 {{ result.subjective_total }} 分待老师评阅
            </template>
          </p>
          <p v-else-if="result.score !== null && result.score !== undefined" class="rsub">
            客观题答对 {{ result.right_count }} / {{ result.objective_count }}
          </p>
          <!-- 在全部交卷同学里排第几（每人取最高分，2.28.0） -->
          <p v-if="result.rank" class="rsub rank">
            当前排名：第 <b>{{ result.rank }}</b> 名 / 共 {{ result.rank_total }} 人
            <span class="tbar">（每人取最高一次的分；后面还有同学交卷，名次会变）</span>
          </p>
        </template>
        <template #extra>
          <el-button type="primary" @click="router.push('/exam')">返回考试列表</el-button>
        </template>
      </el-result>

      <!-- 题目 -->
      <template v-for="(g, gi) in paper.groups" :key="gi">
        <div class="sect">
          {{ CN[gi] || gi + 1 }}、{{ g.name || g.type }}（共 {{ g.items.length }} 题<template
            v-if="g.score"
          >，{{ perQuestion(g.items) }}，共 {{ g.score }} 分</template>）
          <span v-if="g.items.some(q => q.type === '操作题')" class="sd">操作题由老师评阅</span>
        </div>

        <div v-for="q in g.items" :key="q.id" class="q">
          <div class="stem">
            <span class="no">{{ numbering[q.id] }}.</span>{{ q.stem }}
            <span v-if="q.score" class="pt">（{{ q.score }} 分）</span>
            <span
              v-if="detailOf[q.id] && detailOf[q.id].scored"
              class="badge"
              :class="detailOf[q.id].ok ? 'b-ok' : 'b-no'"
            >{{ detailOf[q.id].ok ? '✓' : '✕' }}</span>
          </div>

          <img v-if="q.image_url" :src="q.image_url" class="img" alt="配图" />

          <!-- 挂了仿真任务的操作题：在网页里真做一遍，交卷后按检查点自动判分 -->
          <div v-if="q.sim" class="body">
            <SimHost v-model="answers[q.id]" :sim="q.sim" :readonly="!!result" />
          </div>
          <div v-else-if="q.type === '操作题'" class="body">
            <el-input
              v-model="answers[q.id]"
              type="textarea"
              :rows="3"
              :disabled="!!result"
              placeholder="写下你的操作步骤"
            />
          </div>
          <div v-else class="body">
            <!-- 单选 / 多选（复选框）/ 判断 / 填空（每空一个输入框），见 ObjectiveAnswer.vue -->
            <ObjectiveAnswer v-model="answers[q.id]" :q="q" :disabled="!!result" guard />
          </div>

          <div v-if="detailOf[q.id] && detailOf[q.id].scored && !detailOf[q.id].ok" class="key">
            正确答案：{{ optionText(q.options, detailOf[q.id].answer) }}
          </div>
        </div>
      </template>

      <!-- 底部操作条 -->
      <div class="bar">
        <el-button link @click="back">← 返回列表</el-button>
        <span class="grow" />
        <template v-if="!result">
          <span class="prog">已作答 {{ answered }} / {{ paper.total }}</span>
          <span v-if="gate.reason.value" class="gate">{{ gate.reason.value }}</span>
          <el-button size="large" @click="tempSave">临时保存</el-button>
          <span v-if="savedAt" class="tbar">{{ savedAt }} 已临时保存</span>
          <el-button type="primary" size="large" :loading="submitting" @click="submit">
            交卷
          </el-button>
        </template>
        <span v-else class="prog">已交卷</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.gate {
  font-size: 12px;
  color: var(--el-color-warning);
  margin: 0 10px;
  max-width: 420px;
  line-height: 1.5;
}
.wrap {
  max-width: 880px;
  margin: 0 auto;
  padding: 24px 18px 110px;
  min-height: 100vh;
}
.head {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  padding: 22px;
  text-align: center;
}
.head h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-family: 'Heiti SC', 'SimHei', 'Microsoft YaHei', sans-serif;
  letter-spacing: 0.05em;
}
.meta {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.who {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 14px;
}
.pt {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
  white-space: nowrap;
}
.rank b {
  font-size: 18px;
  color: var(--el-color-primary);
}
.tbar {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.clock {
  position: fixed;
  left: 16px;
  bottom: 16px;
  z-index: 2000;
  padding: 8px 14px;
  border-radius: 8px;
  background: var(--el-bg-color-overlay, #fff);
  border: 1px solid var(--el-border-color);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-primary);
}
@media (max-width: 760px) {
  .clock {
    bottom: 84px;     /* 窄屏时交卷栏会占满底部，挪到它上面 */
  }
}
.clock.late {
  color: var(--el-color-danger);
  border-color: var(--el-color-danger-light-5);
}
.guard {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  font-size: 18px;
  text-align: center;
  line-height: 1.8;
  padding: 20px;
}
.rsub {
  margin: 4px 0;
  line-height: 1.8;
}
.sect {
  margin: 26px 0 8px;
  font-size: 17px;
  font-family: 'Heiti SC', 'SimHei', 'Microsoft YaHei', sans-serif;
}
.sd {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
  margin-left: 8px;
}
.q {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  padding: 15px 17px;
  margin-bottom: 10px;
}
.stem {
  white-space: pre-wrap;
  line-height: 1.8;
}
.no {
  font-weight: 600;
  margin-right: 5px;
}
.img {
  max-width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  margin-top: 9px;
}
.body {
  margin-top: 6px;
}
label.op {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  padding: 6px 9px;
  border-radius: 7px;
  border: 1px solid transparent;
  cursor: pointer;
}
label.op:hover {
  background: var(--el-fill-color-light);
}
label.op.picked {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
label.op.disabled {
  cursor: default;
}
.L {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  min-width: 18px;
}
.key {
  margin-top: 10px;
  background: var(--el-color-danger-light-9);
  border-left: 3px solid var(--el-color-danger);
  border-radius: 0 7px 7px 0;
  padding: 7px 11px;
  font-size: 13.5px;
  color: var(--el-color-danger);
}
.badge {
  font-size: 12px;
  font-weight: 600;
  border-radius: 5px;
  padding: 1px 8px;
  margin-left: 8px;
}
.b-ok {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.b-no {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--el-bg-color);
  border-top: 1px solid var(--el-border-color-light);
  padding: 12px 18px;
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: center;
}
.prog {
  font-family: ui-monospace, Consolas, monospace;
  color: var(--el-text-color-regular);
}
.tip {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 4px 0;
}

/* 学生平台特有的几条：身份是只读的，底部条多了返回按钮 */
.idcard {
  display: inline-block;
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
.bar .grow {
  flex: 1;
}
</style>

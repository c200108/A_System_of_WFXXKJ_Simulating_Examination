<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download, safeName } from '../api'

const CN = ['一', '二', '三', '四', '五', '六']

const scopes = ref([])
const types = ref([])
const plan = ref(null)
const paper = ref(null)
const history = ref([])
const loading = ref(false)

const mode = ref('paper') // paper 试卷 / key 答案卷 / quiz 在线自测
const resp = reactive({}) // 学生作答 {题目id: 选项或文本}
const graded = ref(false)
const score = reactive({ right: 0, obj: 0 })

const form = reactive({
  title: '2026年信息技术模拟测试（A卷）',
  school: '',
  duration: '40',
  counts: { 选择题: 20, 判断题: 10, 操作题: 3 },
  scopes: [],
  use_pinned: true,
  require_answer: true,
  shuffle_options: true,
  seed: '',
  save: false
})

function payload(overrides = {}) {
  return {
    ...form,
    scopes: form.scopes.length ? form.scopes : null,
    seed: form.seed || null,
    ...overrides
  }
}

/** 连续题号：第几大题的第几题在整卷里排第几 */
const numbering = computed(() => {
  const map = {}
  let n = 0
  ;(paper.value?.groups || []).forEach(g => g.items.forEach(q => (map[q.id] = ++n)))
  return map
})

/** 判断题的「正确/错误」在答题界面上对应 A / B */
function rightLetter(q) {
  const a = (q.answer || '').trim()
  if (q.type === '判断题') return a === '正确' ? 'A' : a === '错误' ? 'B' : a
  return a
}

async function refreshPlan() {
  plan.value = await api.previewPlan(payload())
}

onMounted(async () => {
  const dicts = await api.dicts()
  scopes.value = dicts.filter(d => d.category === 'scope').map(d => d.name)
  types.value = dicts.filter(d => d.category === 'qtype').map(d => d.name)
  for (const t of types.value) if (form.counts[t] === undefined) form.counts[t] = 0
  await refreshPlan()
  history.value = await api.papers()
})

watch(
  () => [JSON.stringify(form.counts), form.scopes, form.require_answer],
  refreshPlan,
  { deep: true }
)

function resetQuiz() {
  Object.keys(resp).forEach(k => delete resp[k])
  graded.value = false
  score.right = 0
  score.obj = 0
}

async function generate(fresh = false) {
  loading.value = true
  try {
    // 「换一批」总是换个新种子，所以不带 seed
    paper.value = await api.generate(payload(fresh ? { seed: null } : {}))
    resetQuiz()
    if (paper.value.warnings.length) ElMessage.warning(paper.value.warnings.join('；'))
    else ElMessage.success(`抽到 ${paper.value.total} 道题`)
    if (form.save) history.value = await api.papers()
  } finally {
    loading.value = false
  }
}

async function openPaper(id) {
  paper.value = await api.paper(id)
  resetQuiz()
  mode.value = 'paper'
}

async function removePaper(row) {
  await ElMessageBox.confirm(`确定删除《${row.title}》？`, '提示', { type: 'warning' })
  await api.deletePaper(row.id)
  history.value = await api.papers()
  ElMessage.success('已删除')
}

/** 操作题靠自评；原卷没给答案的题不计分，否则「没作答」会被当成答对 */
function scorable(q) {
  return q.type !== '操作题' && !!(q.answer || '').trim()
}

function submitQuiz() {
  let right = 0
  let obj = 0
  paper.value.groups.forEach(g =>
    g.items.forEach(q => {
      if (!scorable(q)) return
      obj++
      if (resp[q.id] === rightLetter(q)) right++
    })
  )
  score.right = right
  score.obj = obj
  graded.value = true
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function optionClass(q, label) {
  if (!graded.value || !scorable(q)) return ''
  const correct = rightLetter(q)
  if (label === correct) return 'op-ok'
  if (resp[q.id] === label) return 'op-no'
  return ''
}

// ---------- 导出 ----------
async function exportXlsx() {
  await download(api.exportPaperXlsx(paper.value), safeName(paper.value.title) + '.xlsx')
  ElMessage.success('已下载本卷 Excel')
}

async function exportStudent() {
  await download(
    api.exportStudentHtml(paper.value),
    safeName(paper.value.title) + '_学生答题.html'
  )
  ElMessage.success('已下载学生答题网页，可直接发给学生或传到网站上')
}

function printPaper() {
  window.print()
}
</script>

<template>
  <el-row :gutter="16">
    <!-- ============ 左：设置 ============ -->
    <el-col :span="8" class="no-print">
      <el-card shadow="never" class="page-card">
        <template #header>组卷设置</template>
        <el-form label-width="76px" size="default">
          <el-form-item label="试卷标题"><el-input v-model="form.title" /></el-form-item>
          <el-form-item label="学校">
            <el-input v-model="form.school" placeholder="印在卷头，可留空" />
          </el-form-item>
          <el-form-item label="考试时长">
            <el-input v-model="form.duration" style="width: 110px">
              <template #append>分钟</template>
            </el-input>
          </el-form-item>

          <el-divider content-position="left">题量</el-divider>
          <el-form-item v-for="t in types" :key="t" :label="t">
            <el-input-number v-model="form.counts[t]" :min="0" :max="300" size="small" />
          </el-form-item>

          <el-form-item label="知识范围">
            <el-select v-model="form.scopes" multiple collapse-tags placeholder="不选表示全部十类" style="width: 100%">
              <el-option v-for="s in scopes" :key="s" :label="s" :value="s" />
            </el-select>
          </el-form-item>
          <el-form-item label="随机种子">
            <el-input v-model="form.seed" placeholder="填了可复现同一套卷子" />
          </el-form-item>

          <el-form-item label="选项">
            <div class="checks">
              <el-checkbox v-model="form.shuffle_options">打乱选择题的选项顺序（答案自动跟随）</el-checkbox>
              <el-checkbox v-model="form.require_answer">跳过原卷未给答案的题目</el-checkbox>
              <el-checkbox v-model="form.use_pinned">优先放入题库里的必出题</el-checkbox>
              <el-checkbox v-model="form.save">把这套卷子存档</el-checkbox>
            </div>
          </el-form-item>

          <el-button type="primary" :loading="loading" style="width: 100%" @click="generate(false)">
            生成试卷
          </el-button>
        </el-form>
      </el-card>

      <el-card v-if="plan" shadow="never" class="page-card">
        <template #header>本次抽题的知识范围分布</template>
        <div class="chips">
          <span v-for="(v, k) in plan.tally" :key="k" class="chip" :class="{ hot: v > 0 }">
            {{ k }}<b>{{ v }}</b>
          </span>
        </div>
        <p class="note">
          {{ plan.total ? `共 ${plan.total} 题` : '把题型数量调大于 0' }}
          <template v-if="plan.shortfall.length">；题量已按可用上限收窄（{{ plan.shortfall.join('，') }}）</template>
        </p>
        <p class="note">抽题在各知识范围之间轮流分配名额，某个范围题目不够时名额自动让给其他范围。</p>
      </el-card>

      <el-card shadow="never">
        <template #header>历史试卷</template>
        <el-empty v-if="!history.length" description="勾选「把这套卷子存档」后会出现在这里" :image-size="60" />
        <el-table v-else :data="history" size="small" border>
          <el-table-column prop="title" label="标题" show-overflow-tooltip />
          <el-table-column prop="code" label="卷号" width="86" />
          <el-table-column prop="question_count" label="题数" width="60" />
          <el-table-column label="" width="88">
            <template #default="{ row }">
              <el-button link type="primary" @click="openPaper(row.id)">打开</el-button>
              <el-button link type="danger" @click="removePaper(row)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-col>

    <!-- ============ 右：试卷 ============ -->
    <el-col :span="16">
      <el-card shadow="never">
        <template #header>
          <div class="card-head no-print">
            <el-radio-group v-model="mode" size="small" :disabled="!paper">
              <el-radio-button value="paper">试卷</el-radio-button>
              <el-radio-button value="key">答案卷</el-radio-button>
              <el-radio-button value="quiz">在线自测</el-radio-button>
            </el-radio-group>
            <div class="acts">
              <el-button size="small" :disabled="!paper" @click="generate(true)">换一批</el-button>
              <el-button size="small" :disabled="!paper" @click="printPaper">打印 / 存 PDF</el-button>
              <el-button size="small" :disabled="!paper" @click="exportStudent">导出学生答题网页</el-button>
              <el-button size="small" :disabled="!paper" @click="exportXlsx">导出本卷 Excel</el-button>
            </div>
          </div>
        </template>

        <el-empty v-if="!paper" description="左边设好题量，点「生成试卷」" />

        <div v-else class="paper">
          <!-- 卷头 -->
          <div class="paper-head">
            <h1>{{ paper.title }}</h1>
            <div class="meta">
              <span v-if="paper.school">{{ paper.school }}　·　</span>
              <span v-if="paper.duration">考试时长 {{ paper.duration }} 分钟　·　</span>
              <span>{{ paper.code }}</span>
            </div>
          </div>
          <div v-if="mode !== 'quiz'" class="paper-fill">
            <span>班级：<u></u></span><span>姓名：<u></u></span>
            <span>学号：<u></u></span><span>得分：<u></u></span>
          </div>

          <!-- 自测计分条 -->
          <div v-if="mode === 'quiz'" class="scorebar no-print">
            <div v-if="!graded">
              <div class="sb-t">在线自测</div>
              <div class="note">选择题、判断题自动判分；操作题交卷后对照答案要点自评。</div>
            </div>
            <div v-else>
              <div class="sb-t">客观题得分 <b>{{ score.right }} / {{ score.obj }}</b></div>
              <div class="note">
                正确率 {{ score.obj ? Math.round((score.right / score.obj) * 100) : 0 }}%　·　操作题请对照答案要点自评
              </div>
            </div>
            <div class="flex-1" />
            <el-button v-if="!graded" type="primary" @click="submitQuiz">交卷判分</el-button>
            <el-button v-else @click="resetQuiz">重新作答</el-button>
          </div>

          <!-- ===== 答案卷 ===== -->
          <template v-if="mode === 'key'">
            <div class="sect"><h2>参考答案</h2><div class="sd">{{ paper.title }}　{{ paper.code }}</div></div>
            <template v-for="(g, gi) in paper.groups" :key="'k' + gi">
              <div class="sect"><h2>{{ CN[gi] }}、{{ g.type }}</h2></div>
              <div v-if="g.type === '操作题'" class="alist">
                <div v-for="q in g.items" :key="q.id" class="ai">
                  <div class="ah">第 {{ numbering[q.id] }} 题　{{ q.scope }}</div>
                  <div v-if="q.answer">{{ q.answer }}</div>
                  <div v-else class="na">原卷未给答案</div>
                </div>
              </div>
              <div v-else class="akey">
                <div v-for="q in g.items" :key="q.id">
                  <span>{{ numbering[q.id] }}</span>
                  <b v-if="q.answer">{{ q.answer }}</b><span v-else class="na">—</span>
                </div>
              </div>
            </template>
          </template>

          <!-- ===== 试卷 / 在线自测 ===== -->
          <template v-else>
            <template v-for="(g, gi) in paper.groups" :key="gi">
              <div class="sect">
                <h2>{{ CN[gi] }}、{{ g.type }}（共 {{ g.items.length }} 题）</h2>
                <div class="sd">
                  {{
                    mode === 'quiz'
                      ? g.type === '操作题'
                        ? '写下操作步骤，交卷后对照答案要点自评。'
                        : '直接在下面选择，交卷后自动判分。'
                      : g.type === '操作题'
                        ? '按题目要求在计算机上完成操作。'
                        : '把答案写在题号前的括号里。'
                  }}
                </div>
              </div>

              <div v-for="q in g.items" :key="q.id" class="q">
                <div class="q-stem">
                  <span class="q-no">{{ numbering[q.id] }}.</span>{{ q.stem }}
                  <span v-if="mode === 'quiz' && graded && !scorable(q)" class="mark na">
                    {{ q.type === '操作题' ? '自评' : '不计分' }}
                  </span>
                  <span
                    v-else-if="mode === 'quiz' && graded"
                    class="mark"
                    :class="resp[q.id] === rightLetter(q) ? 'ok' : 'no'"
                  >{{ resp[q.id] === rightLetter(q) ? '✓ 正确' : '✕ 错误' }}</span>
                </div>

                <el-image
                  v-if="q.image_url"
                  :src="q.image_url"
                  :preview-src-list="[q.image_url]"
                  fit="contain"
                  class="q-img"
                />

                <!-- 自测：可选 -->
                <div v-if="mode === 'quiz' && q.type !== '操作题'" class="opts">
                  <label
                    v-for="o in q.options"
                    :key="o.label"
                    class="op"
                    :class="optionClass(q, o.label)"
                  >
                    <input
                      type="radio"
                      :name="'q' + q.id"
                      :value="o.label"
                      :disabled="graded"
                      :checked="resp[q.id] === o.label"
                      @change="resp[q.id] = o.label"
                    />
                    <span class="L">{{ o.label }}</span><span>{{ o.content }}</span>
                  </label>
                </div>
                <div v-else-if="mode === 'quiz'" class="opts">
                  <el-input
                    v-model="resp[q.id]"
                    type="textarea"
                    :rows="3"
                    :disabled="graded"
                    placeholder="写下你的操作步骤，交卷后对照答案要点自评"
                  />
                </div>

                <!-- 试卷：纯展示 -->
                <div v-else-if="q.options.length" class="opts flat">
                  <span v-for="o in q.options" :key="o.label" class="op-flat">
                    <span class="L">{{ o.label }}</span>{{ o.content }}
                  </span>
                </div>

                <div v-if="mode === 'quiz' && graded" class="ans">
                  <template v-if="q.answer">答案：<b>{{ q.answer }}</b></template>
                  <template v-else>这道题原卷未给答案，不计分。</template>
                </div>
                <div class="q-tag no-print">
                  <span class="tag k">{{ q.scope }}</span>
                  <span class="tag">{{ q.source }}</span>
                  <span class="tag">{{ q.code }}</span>
                </div>
              </div>
            </template>
          </template>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<style scoped>
.checks {
  display: flex;
  flex-direction: column;
  line-height: 1.9;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  padding: 2px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.chip.hot {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.chip b {
  margin-left: 6px;
}
.note {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.7;
  margin: 10px 0 0;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.acts {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-left: auto;
}
.flex-1 {
  flex: 1;
}

/* 卷面 */
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
.meta {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.paper-fill {
  display: flex;
  gap: 24px;
  justify-content: center;
  flex-wrap: wrap;
  border-top: 1px dashed var(--el-border-color);
  border-bottom: 1px dashed var(--el-border-color);
  padding: 8px 0;
  margin-bottom: 16px;
  font-size: 13px;
}
.paper-fill u {
  display: inline-block;
  width: 68px;
}
.scorebar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 16px;
}
.sb-t {
  font-weight: 600;
}
.sb-t b {
  font-size: 18px;
  color: var(--el-color-primary);
}
.sect {
  margin: 22px 0 10px;
}
.sect h2 {
  margin: 0;
  font-size: 16px;
  font-family: 'Heiti SC', 'SimHei', 'Microsoft YaHei', sans-serif;
}
.sd {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
  margin-top: 3px;
}
.q {
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
  cursor: zoom-in;
}
.opts {
  margin: 4px 0 0 20px;
}
.opts.flat {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 24px;
}
.op-flat {
  min-width: 42%;
}
.L {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-right: 6px;
}
label.op {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 4px 8px;
  border-radius: 7px;
  border: 1px solid transparent;
  cursor: pointer;
}
label.op:hover {
  background: var(--el-fill-color-light);
}
.op-ok {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success);
}
.op-no {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger);
}
.ans {
  margin: 6px 0 0 20px;
  color: var(--el-color-danger);
  font-size: 13.5px;
}
.mark {
  font-size: 12px;
  border-radius: 5px;
  padding: 1px 8px;
  margin-left: 8px;
}
.mark.ok {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.mark.no {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.mark.na {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.q-tag {
  margin: 4px 0 0 20px;
  display: flex;
  gap: 6px;
}
.tag {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 0 6px;
}
.tag.k {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
}
/* 答案卷 */
.akey {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.akey > div {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 3px 10px;
  min-width: 62px;
  text-align: center;
}
.akey span {
  color: var(--el-text-color-secondary);
  margin-right: 6px;
}
.alist .ai {
  border-left: 3px solid var(--el-color-primary-light-5);
  padding: 4px 0 4px 10px;
  margin-bottom: 10px;
  white-space: pre-wrap;
}
.ah {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.na {
  color: var(--el-color-warning);
}

@media print {
  .no-print,
  .el-header,
  .el-card__header {
    display: none !important;
  }
  .el-card {
    border: none !important;
    box-shadow: none !important;
  }
  .el-col-8 {
    display: none !important;
  }
  .el-col-16 {
    max-width: 100% !important;
    flex: 0 0 100% !important;
  }
}
</style>

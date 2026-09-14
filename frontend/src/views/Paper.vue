<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { siteConfig } from '../siteConfig'
import { api, download, safeName } from '../api'

const CN = siteConfig.paper.section_numerals

/** 卷面结构（六个大题）来自 config.yaml，学校改了配置这里跟着变，不用改代码。 */
const sections = computed(() => siteConfig.paper.sections || [])
/** 改题量用的键：大题名 + 第几组。用名字而不是下标，配置调顺序也对得上。 */
const slotKey = (sec, i) => `${sec.name}/${i}`

const scopes = ref([])
const types = ref([])
const plan = ref(null)
const paper = ref(null)
const history = ref([])
const loading = ref(false)

const mode = ref('paper') // paper 试卷 / key 答案卷 / quiz 在线自测
const resp = reactive({}) // 学生作答 {题目id: 选项或文本}
const graded = ref(false)
// right/obj 是答对题数；got/full 是客观题得分与满分；manual 是等人工评阅的分
const score = reactive({ right: 0, obj: 0, got: 0, full: 0, manual: 0 })

// 卷头、题量、三个开关的默认值都来自 config.yaml，改配置这里就跟着变
const form = reactive({
  title: siteConfig.paper.default_title,
  school: siteConfig.school,
  duration: siteConfig.paper.default_duration,
  // true = 按卷面结构出六个大题并给每题赋分；false = 老的按题型自由组卷
  by_sections: true,
  section_counts: {},
  section_scores: {},
  counts: { ...siteConfig.paper.default_counts },
  scopes: [],
  use_pinned: siteConfig.paper.use_pinned,
  require_answer: siteConfig.paper.require_answer,
  shuffle_options: siteConfig.paper.shuffle_options,
  seed: '',
  save: false
})

/** 把配置里的题量和分值填进表单，「恢复默认」也走这里。 */
function resetBlueprint() {
  form.section_counts = {}
  form.section_scores = {}
  sections.value.forEach(sec => {
    form.section_scores[sec.name] = sec.score
    sec.slots.forEach((slot, i) => (form.section_counts[slotKey(sec, i)] = slot.count))
  })
}

/** 卷面总分：各大题分值之和。改了某个大题的分，这里立刻跟着变。 */
const plannedFull = computed(() =>
  sections.value.reduce((a, sec) => a + (Number(form.section_scores[sec.name]) || 0), 0)
)
const plannedCount = computed(() =>
  Object.values(form.section_counts).reduce((a, n) => a + (Number(n) || 0), 0)
)

function payload(overrides = {}) {
  return {
    ...form,
    scopes: form.scopes.length ? form.scopes : null,
    seed: form.seed || null,
    ...overrides
  }
}

/** 这个大题预览时凑齐了没有，用来在卡片上标红 */
function secPlan(name) {
  return (plan.value?.sections || []).find(s => s.name === name)
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
  resetBlueprint()
  await refreshPlan()
  history.value = await api.papers()
})

watch(
  () => [
    form.by_sections,
    JSON.stringify(form.counts),
    JSON.stringify(form.section_counts),
    JSON.stringify(form.section_scores),
    form.scopes,
    form.require_answer
  ],
  refreshPlan,
  { deep: true }
)

function resetQuiz() {
  Object.keys(resp).forEach(k => delete resp[k])
  graded.value = false
  Object.assign(score, { right: 0, obj: 0, got: 0, full: 0, manual: 0 })
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
  let got = 0
  let full = 0
  let manual = 0
  paper.value.groups.forEach(g =>
    g.items.forEach(q => {
      if (q.type === '操作题') return (manual += q.score || 0)
      if (!scorable(q)) return
      obj++
      full += q.score || 0
      if (resp[q.id] === rightLetter(q)) {
        right++
        got += q.score || 0
      }
    })
  )
  score.right = right
  score.obj = obj
  score.got = got
  score.full = full
  score.manual = manual
  graded.value = true
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/** 大题下面那行小字。一个大题里可能两种题型都有，按实际内容说，别写死。 */
function sectionHint(g) {
  const hasOp = g.items.some(q => q.type === '操作题')
  const hasPick = g.items.some(q => q.type !== '操作题')
  if (mode.value === 'quiz') {
    if (hasOp && hasPick) return '选择题自动判分；操作题写下步骤，交卷后对照答案要点自评。'
    return hasOp ? '写下操作步骤，交卷后对照答案要点自评。' : '直接在下面选择，交卷后自动判分。'
  }
  if (hasOp && hasPick) return '选择题把答案写在题号前的括号里；操作题在计算机上完成。'
  return hasOp ? '按题目要求在计算机上完成操作。' : '把答案写在题号前的括号里。'
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
    <el-col :xs="24" :sm="24" :md="10" :lg="8" class="no-print setting-col">
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

          <el-divider content-position="left">卷面结构</el-divider>
          <el-form-item label="组卷方式">
            <el-radio-group v-model="form.by_sections" size="small">
              <el-radio-button :value="true">六大题</el-radio-button>
              <el-radio-button :value="false">按题型</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <!-- ===== 六大题：每个大题一张卡，题量和分值都能临时改 ===== -->
          <template v-if="form.by_sections">
            <div v-for="(sec, si) in sections" :key="sec.name" class="sec-card">
              <div class="sec-head">
                <span class="sec-no">{{ CN[si] || si + 1 }}</span>
                <b class="sec-name">{{ sec.name }}</b>
                <el-input-number
                  v-model="form.section_scores[sec.name]"
                  :min="0"
                  :max="200"
                  size="small"
                  controls-position="right"
                  class="sec-score"
                />
                <span class="unit">分</span>
              </div>
              <div v-for="(slot, li) in sec.slots" :key="li" class="slot">
                <div class="slot-what">
                  <span class="tag t">{{ slot.type }}</span>
                  <span v-if="slot.scopes.length" class="tag k">{{ slot.scopes.join(' / ') }}</span>
                  <span v-if="slot.prefer === 'long_or_image'" class="tag p">长题干或带图</span>
                  <span v-if="slot.label" class="slot-label">{{ slot.label }}</span>
                </div>
                <el-input-number
                  v-model="form.section_counts[slotKey(sec, li)]"
                  :min="0"
                  :max="300"
                  size="small"
                  controls-position="right"
                  class="slot-n"
                />
              </div>
              <div v-if="secPlan(sec.name) && secPlan(sec.name).have < secPlan(sec.name).want" class="short">
                题库只凑得出 {{ secPlan(sec.name).have }} 道
              </div>
            </div>

            <div class="sec-total" :class="{ warn: plannedFull !== 100 }">
              全卷 <b>{{ plannedCount }}</b> 题 ·
              <b>{{ plannedFull }}</b> 分
              <span v-if="plannedFull !== 100" class="warn-text">（不是 100 分，确认一下）</span>
              <el-button link type="primary" size="small" @click="resetBlueprint">恢复默认</el-button>
            </div>
            <p class="note">
              每个大题的分按题目难度摊到题上，同一大题里<b>操作题的分最高</b>；
              操作题要老师在成绩页逐题给分，学生交卷先拿到客观题得分。
            </p>
          </template>

          <!-- ===== 按题型：老的自由组卷，不设分值 ===== -->
          <template v-else>
            <el-form-item v-for="t in types" :key="t" :label="t">
              <el-input-number v-model="form.counts[t]" :min="0" :max="300" size="small" />
            </el-form-item>
            <p class="note">这种方式不给题目赋分，判分仍按客观题正确率折成百分制。</p>
          </template>

          <el-form-item label="知识范围">
            <el-select v-model="form.scopes" multiple collapse-tags placeholder="不选表示全部十类" style="width: 100%">
              <el-option v-for="s in scopes" :key="s" :label="s" :value="s" />
            </el-select>
            <span v-if="form.by_sections" class="sub">
              只作用于上面没限定范围的那几组；限定了范围的组仍按各自的范围抽。
            </span>
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
          {{ plan.total ? `共 ${plan.total} 题` : '把题量调大于 0' }}
          <template v-if="plan.full_score">，满分 {{ plan.full_score }} 分</template>
        </p>
        <ul v-if="plan.shortfall.length" class="short-list">
          <li v-for="(w, i) in plan.shortfall" :key="i">{{ w }}</li>
        </ul>
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
    <el-col :xs="24" :sm="24" :md="14" :lg="16" class="paper-col">
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
              <span v-if="paper.full_score">满分 {{ paper.full_score }} 分　·　</span>
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
            <div v-else-if="score.full">
              <div class="sb-t">客观题得分 <b>{{ score.got }} / {{ score.full }}</b> 分</div>
              <div class="note">
                答对 {{ score.right }} / {{ score.obj }} 题　·　
                <template v-if="score.manual">还有 {{ score.manual }} 分的操作题，请对照答案要点自评</template>
                <template v-else>这份卷子没有操作题</template>
              </div>
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
              <div class="sect"><h2>{{ CN[gi] || gi + 1 }}、{{ g.name || g.type }}</h2></div>
              <div v-if="g.items.every(q => q.type === '操作题')" class="alist">
                <div v-for="q in g.items" :key="q.id" class="ai">
                  <div class="ah">第 {{ numbering[q.id] }} 题　{{ q.scope }}</div>
                  <div v-if="q.answer">{{ q.answer }}</div>
                  <div v-else class="na">原卷未给答案</div>
                </div>
              </div>
              <div v-else class="akey">
                <div v-for="q in g.items" :key="q.id">
                  <span>{{ numbering[q.id] }}</span>
                  <b v-if="q.type === '操作题'" class="na">人工阅</b>
                  <b v-else-if="q.answer">{{ q.answer }}</b><span v-else class="na">—</span>
                </div>
              </div>
            </template>
          </template>

          <!-- ===== 试卷 / 在线自测 ===== -->
          <template v-else>
            <template v-for="(g, gi) in paper.groups" :key="gi">
              <div class="sect">
                <h2>
                  {{ CN[gi] || gi + 1 }}、{{ g.name || g.type }}（共 {{ g.items.length }} 题<template
                    v-if="g.score"
                  >，共 {{ g.score }} 分</template>）
                </h2>
                <div class="sd">{{ sectionHint(g) }}</div>
              </div>

              <div v-for="q in g.items" :key="q.id" class="q">
                <div class="q-stem">
                  <span class="q-no">{{ numbering[q.id] }}.</span>{{ q.stem }}
                  <span v-if="q.score" class="pt">（{{ q.score }} 分）</span>
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
                  <span v-if="q.difficulty" class="tag">难度 {{ q.difficulty }}</span>
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
.sub {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  margin-top: 4px;
}
.short-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--el-color-warning);
  font-size: 12px;
  line-height: 1.7;
}

/* ---- 六大题的设置卡 ---- */
.sec-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: var(--el-fill-color-blank);
}
.sec-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.sec-no {
  width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 4px;
  font-size: 12px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  flex: none;
}
.sec-name {
  flex: 1;
  font-size: 13.5px;
  /* 大题名可能很长（「互联网原理与创新」），窄屏上让它换行而不是把输入框挤出去 */
  min-width: 0;
  word-break: break-all;
}
.sec-score {
  width: 78px;
  flex: none;
}
.unit {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  flex: none;
}
.slot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding-left: 24px;
}
.slot-what {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.slot-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.slot-n {
  width: 78px;
  flex: none;
}
.short {
  margin: 6px 0 0 24px;
  font-size: 12px;
  color: var(--el-color-warning);
}
.sec-total {
  display: flex;
  align-items: center;
  gap: 6px;
  border-top: 1px dashed var(--el-border-color);
  padding-top: 8px;
  font-size: 13px;
}
.sec-total.warn {
  color: var(--el-color-warning);
}
.warn-text {
  font-size: 12px;
}
.tag.t {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
}
.tag.p {
  color: var(--el-color-warning);
  border-color: var(--el-color-warning-light-7);
}
.pt {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
  white-space: nowrap;
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
  /* 打印时只留卷面。原来按 .el-col-8 / .el-col-16 选，改成响应式之后
     这两个类名就不一定在了（窄屏是 el-col-xs-24），所以改用自己的类名。 */
  .setting-col {
    display: none !important;
  }
  .paper-col {
    max-width: 100% !important;
    flex: 0 0 100% !important;
  }
}
</style>

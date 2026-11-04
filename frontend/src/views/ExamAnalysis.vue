<script setup>
/**
 * 成绩分析：从成绩页新开一个标签页，整页铺开看一场考试的各项指标和图。
 *
 * - 看谁：全体参考学生 / 某几个班 / 选几个学生对比，选择记在地址栏里，链接发给别的
 *   老师打开就是同一个视角；
 * - 数据每 20 秒重新拉一次（切到别的标签页时暂停）—— 老师在成绩页阅完卷、改了分，
 *   这边的图和结论自己就变了；
 * - 结论是服务端按数据写的（services/analysis.py），这里只负责画。
 *
 * 图的规矩（见 dataviz 那套）：一张图只有一个纵轴；颜色按系列固定顺序分配、不随
 * 排名变；两个以上系列一定有图例；每张图下面都能展开看原始数字。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import EChart from '../components/EChart.vue'

const route = useRoute()
const router = useRouter()
const examId = computed(() => route.params.id)

const data = ref(null)
const loading = ref(false)
const failed = ref('')
const auto = ref(true)
const tables = reactive({})          // 哪几张图展开了数据表

const mode = ref('all')              // all / classes / students
const pickClasses = ref([])
const pickStudents = ref([])
const MAX_STUDENTS = 8               // 分组柱最多 8 个系列：配色只验证到 8 个

// ---------------------------------------------------------------- 配色
// 分类色按固定顺序取，深浅色各一套（深色不是自动反色，是另选的一档）
const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']
}
const dark = ref(document.documentElement.classList.contains('dark'))
const palette = computed(() => SERIES[dark.value ? 'dark' : 'light'])
function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}
const ink = computed(() => {
  void dark.value
  return {
    text: cssVar('--el-text-color-regular', '#52514e'),
    muted: cssVar('--el-text-color-secondary', '#8a8a86'),
    line: cssVar('--el-border-color-lighter', '#ebeef5'),
    surface: cssVar('--el-bg-color', '#ffffff')
  }
})

// ---------------------------------------------------------------- 取数
async function load(quiet = false) {
  if (!quiet) loading.value = true
  failed.value = ''
  const params = {}
  if (mode.value === 'classes' && pickClasses.value.length) params.classes = pickClasses.value.join(',')
  if (mode.value === 'students' && pickStudents.value.length) params.students = pickStudents.value.join(',')
  try {
    data.value = await api.examAnalysis(examId.value, params)
    document.title = `成绩分析 · ${data.value.exam.title}`
  } catch (e) {
    failed.value = '数据没取到，稍后会自动再试'
  } finally {
    loading.value = false
  }
}

function syncQuery() {
  const query = {}
  if (mode.value === 'classes' && pickClasses.value.length) query.classes = pickClasses.value.join(',')
  if (mode.value === 'students' && pickStudents.value.length) query.students = pickStudents.value.join(',')
  router.replace({ query })
}

watch([mode, pickClasses, pickStudents], () => {
  // 选了"按班级"但还没挑班：先看全体，别给一页空白
  syncQuery()
  load()
})

let timer = null
function tick() {
  if (auto.value && !document.hidden) load(true)
}
onMounted(() => {
  // 地址栏里带着视角的（别的老师发来的链接）：照着选上，watch 会去取数；没带就直接取全体
  const q = route.query
  if (q.students) {
    mode.value = 'students'
    pickStudents.value = String(q.students).split(',').map(Number).filter(Boolean)
  } else if (q.classes) {
    mode.value = 'classes'
    pickClasses.value = String(q.classes).split(',').filter(Boolean)
  } else {
    load()
  }
  timer = setInterval(tick, 20000)
  document.addEventListener('visibilitychange', tick)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', tick)
})

const s = computed(() => data.value?.summary || {})
const updated = computed(() => (data.value?.updated_at || '').slice(11, 19))
const scopeText = computed(() => {
  if (!data.value) return ''
  const sc = data.value.scope || {}
  if (sc.kind === 'classes') return `班级：${(sc.classes || []).join('、')}`
  if (sc.kind === 'students') return `学生对比：${data.value.compare.map(c => c.name).join('、')}`
  return '全体参考学生'
})
function studentLabel(o) {
  return `${o.name}　${o.class || ''}　${o.no || ''}　${o.score} 分`
}

// ---------------------------------------------------------------- 图
function baseGrid(extra = {}) {
  return { left: 8, right: 16, top: 24, bottom: 8, containLabel: true, ...extra }
}
function axisStyle() {
  return {
    axisLine: { lineStyle: { color: ink.value.line } },
    axisTick: { show: false },
    axisLabel: { color: ink.value.muted },
    splitLine: { lineStyle: { color: ink.value.line } }
  }
}
function tooltip(extra = {}) {
  return {
    trigger: 'item',
    backgroundColor: ink.value.surface,
    borderColor: ink.value.line,
    textStyle: { color: ink.value.text },
    confine: true,
    ...extra
  }
}
function bar(color, extra = {}) {
  return {
    type: 'bar',
    barMaxWidth: 34,
    itemStyle: { color, borderRadius: [4, 4, 0, 0] },
    emphasis: { focus: 'self' },
    ...extra
  }
}
function passLine() {
  const line = data.value?.pass_line ?? 60
  return {
    symbol: 'none',
    silent: true,
    lineStyle: { color: ink.value.muted, type: 'dashed', width: 1 },
    label: { color: ink.value.muted, formatter: `及格线 ${line}%`, position: 'insideEndTop' },
    data: [{ yAxis: line }]
  }
}
const pctAxis = () => ({ type: 'value', min: 0, max: 100, axisLabel: { color: ink.value.muted, formatter: '{value}%' },
  splitLine: { lineStyle: { color: ink.value.line } } })

const bandsOpt = computed(() => {
  const b = data.value?.bands || []
  return {
    grid: baseGrid(),
    tooltip: tooltip({ formatter: p => `${p.name} 分：${p.value} 人` }),
    xAxis: { type: 'category', data: b.map(x => x.label), ...axisStyle(), splitLine: { show: false } },
    yAxis: { type: 'value', minInterval: 1, ...axisStyle(), axisLine: { show: false } },
    series: [bar(palette.value[0], {
      data: b.map(x => x.count),
      label: { show: true, position: 'top', color: ink.value.muted, formatter: p => (p.value ? p.value : '') }
    })]
  }
})

const classRateOpt = computed(() => {
  const c = data.value?.classes || []
  const names = ['平均得分率', '及格率', '优秀率']
  const keys = ['avg_rate', 'pass_rate', 'excellent_rate']
  return {
    grid: baseGrid({ top: 36 }),
    legend: { top: 0, textStyle: { color: ink.value.text }, itemWidth: 12, itemHeight: 12 },
    tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: v => `${v}%` }),
    xAxis: { type: 'category', data: c.map(x => x.name), ...axisStyle(), splitLine: { show: false } },
    yAxis: pctAxis(),
    series: keys.map((k, i) => bar(palette.value[i], { name: names[i], data: c.map(x => x[k]), barGap: '8%' }))
  }
})

const boxOpt = computed(() => {
  const c = data.value?.classes || []
  return {
    grid: baseGrid(),
    tooltip: tooltip({
      formatter: p => {
        // 箱线图的数据项是 [最低, 下四分位, 中位数, 上四分位, 最高]
        const v = p.data.length === 6 ? p.data.slice(1) : p.data
        const [lo, q1, med, q3, hi] = v
        return `${p.name}<br/>最高 ${hi}　上四分位 ${q3}<br/>中位数 ${med}<br/>下四分位 ${q1}　最低 ${lo}`
      }
    }),
    xAxis: { type: 'category', data: c.map(x => x.name), ...axisStyle(), splitLine: { show: false } },
    yAxis: { type: 'value', min: 0, max: s.value.full || undefined, ...axisStyle(), axisLine: { show: false } },
    series: [{
      type: 'boxplot',
      data: c.map(x => x.box),
      itemStyle: { color: dark.value ? '#184f95' : '#cde2fb', borderColor: palette.value[0], borderWidth: 2 },
      boxWidth: [12, 36]
    }]
  }
})

function hbar(rows, labelOf, valueOf, color) {
  return {
    grid: baseGrid({ right: 40 }),
    tooltip: tooltip({ formatter: p => `${p.name}：${p.value}%` }),
    xAxis: pctAxis(),
    yAxis: { type: 'category', inverse: true, data: rows.map(labelOf), ...axisStyle(), splitLine: { show: false },
      triggerEvent: true,
      axisLabel: { color: ink.value.text, width: 150, overflow: 'truncate' } },
    series: [{
      type: 'bar', data: rows.map(valueOf), barMaxWidth: 18,
      itemStyle: { color, borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: ink.value.muted, formatter: '{c}%' },
      markLine: { ...passLine(), data: [{ xAxis: data.value?.pass_line ?? 60 }] }
    }]
  }
}
const scopeOpt = computed(() => hbar((data.value?.scopes || []).filter(g => g.rate !== null),
  g => g.name, g => g.rate, palette.value[0]))
const sectionOpt = computed(() => hbar((data.value?.sections || []).filter(g => g.rate !== null),
  g => g.name, g => g.rate, palette.value[0]))
const opsRows = computed(() => (data.value?.operations || []).flatMap(o =>
  o.checks.map(c => ({
    label: `第${o.no}题 · ${c.desc}`, value: c.pass_rate, no: o.no, desc: c.desc, stem: o.stem,
    passed: c.passed, total: c.total
  }))))
const opsOpt = computed(() => hbar(opsRows.value, r => r.label, r => r.value, palette.value[0]))

/** 有几个人通过：老服务端不带人数，就不写 */
function passedText(r) {
  return r.total ? `${r.passed}/${r.total} 人通过` : ''
}
/** 左边被截断的那段文字：鼠标停上去看完整的小题、通过率和这道题的题干 */
function opsTip(label) {
  const r = opsRows.value.find(x => x.label === label)
  if (!r) return label
  const stem = String(r.stem || '').replace(/\s+/g, ' ').trim()
  const who = passedText(r)
  return `第 ${r.no} 题 · ${r.desc}\n通过率 ${r.value}%${who ? '（' + who + '）' : ''}` +
    (stem ? `\n题干：${stem.length > 300 ? stem.slice(0, 300) + '…（完整题干见下面排名表）' : stem}` : '')
}
const plainTip = label => label

// 每道操作题**单独**给小题排名：名次按通过率从高到低算，通过率一样的并列；
// 「从差到好」只是倒过来列，名次不变（第 1 名永远是最好的那一步）
const opsOrder = ref('good')
const opsRanks = computed(() => (data.value?.operations || []).map(o => {
  const rows = o.checks.map((c, i) => ({ ...c, step: i }))
    .sort((a, b) => b.pass_rate - a.pass_rate || a.step - b.step)
  let last = null
  let lastRank = 0
  rows.forEach((r, i) => {
    if (r.pass_rate !== last) {
      last = r.pass_rate
      lastRank = i + 1
    }
    r.rank = lastRank
  })
  return { id: o.id, no: o.no, stem: o.stem, rate: o.rate,
    rows: opsOrder.value === 'good' ? rows : [...rows].reverse() }
}))

const questionOpt = computed(() => {
  const q = (data.value?.questions || []).filter(x => x.rate !== null)
  return {
    grid: baseGrid({ bottom: 20 }),
    tooltip: tooltip({
      formatter: p => {
        const x = q[p.dataIndex]
        return `第 ${x.no} 题　${x.type}　${x.scope}<br/>得分率 ${x.rate}%（均分 ${x.avg}/${x.score}）` +
          `<br/><span style="opacity:.75">${x.stem}</span>`
      }
    }),
    xAxis: { type: 'category', data: q.map(x => x.no), name: '题号', nameLocation: 'middle', nameGap: 26,
      nameTextStyle: { color: ink.value.muted }, ...axisStyle(), splitLine: { show: false } },
    yAxis: pctAxis(),
    series: [bar(palette.value[0], { data: q.map(x => x.rate), barMaxWidth: 22, markLine: passLine() })]
  }
})

const discOpt = computed(() => {
  const q = (data.value?.questions || []).filter(x => x.rate !== null && x.discrimination !== null)
  return {
    grid: baseGrid({ bottom: 24, left: 16 }),
    tooltip: tooltip({
      formatter: p => {
        const x = q[p.dataIndex]
        return `第 ${x.no} 题　得分率 ${x.rate}%　区分度 ${x.discrimination}<br/><span style="opacity:.75">${x.stem}</span>`
      }
    }),
    xAxis: { type: 'value', min: 0, max: 100, name: '得分率', nameLocation: 'middle', nameGap: 24,
      nameTextStyle: { color: ink.value.muted }, axisLabel: { color: ink.value.muted, formatter: '{value}%' },
      splitLine: { lineStyle: { color: ink.value.line } } },
    yAxis: { type: 'value', min: -1, max: 1, name: '区分度', nameTextStyle: { color: ink.value.muted },
      axisLabel: { color: ink.value.muted }, splitLine: { lineStyle: { color: ink.value.line } } },
    series: [{
      type: 'scatter', symbolSize: 10,
      data: q.map(x => [x.rate, x.discrimination]),
      itemStyle: { color: palette.value[0], borderColor: ink.value.surface, borderWidth: 2 },
      // 只给值得回头看的题（区分度 < 0.2）标题号，其余靠悬停 —— 点一多，全标就糊成一团
      label: {
        show: true, position: 'right', color: ink.value.muted,
        formatter: p => (q[p.dataIndex].discrimination < 0.2 ? `第${q[p.dataIndex].no}题` : '')
      },
      markLine: {
        symbol: 'none', silent: true,
        lineStyle: { color: ink.value.muted, type: 'dashed', width: 1 },
        label: { color: ink.value.muted, formatter: '0.2 以下偏低', position: 'insideEndTop' },
        data: [{ yAxis: 0.2 }]
      }
    }]
  }
})

function compareOpt(key) {
  const c = data.value?.compare || []
  const cats = (c[0]?.[key] || []).map(g => g.name)
  return {
    grid: baseGrid({ top: 36 }),
    legend: { top: 0, textStyle: { color: ink.value.text }, itemWidth: 12, itemHeight: 12 },
    tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: v => `${v}%` }),
    xAxis: { type: 'category', data: cats, ...axisStyle(), splitLine: { show: false },
      axisLabel: { color: ink.value.muted, interval: 0, width: 90, overflow: 'truncate' } },
    yAxis: pctAxis(),
    series: c.map((st, i) => bar(palette.value[i % palette.value.length], {
      name: st.name, data: st[key].map(g => g.rate), barGap: '8%'
    }))
  }
}
const compareScopeOpt = computed(() => compareOpt('by_scope'))
const compareSectionOpt = computed(() => compareOpt('by_section'))

function rateClass(r) {
  if (r === null || r === undefined) return ''
  return r >= (data.value?.pass_line ?? 60) ? 'ok' : 'no'
}
function toggle(name) {
  tables[name] = !tables[name]
}
function printPage() {
  window.print()
}
</script>

<template>
  <div class="page">
    <header class="top">
      <div class="title">
        <h1>成绩分析</h1>
        <span v-if="data" class="exam">{{ data.exam.title }}</span>
      </div>
      <div class="tools no-print">
        <span v-if="updated" class="upd">数据更新于 {{ updated }}</span>
        <el-switch v-model="auto" size="small" active-text="自动刷新" />
        <el-button size="small" :loading="loading" @click="load()">刷新</el-button>
        <el-button size="small" @click="printPage">打印</el-button>
      </div>
    </header>

    <section class="filters no-print">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="all">全体参考学生</el-radio-button>
        <el-radio-button value="classes">按班级</el-radio-button>
        <el-radio-button value="students">学生对比</el-radio-button>
      </el-radio-group>
      <el-select
        v-if="mode === 'classes'"
        v-model="pickClasses"
        multiple
        collapse-tags
        collapse-tags-tooltip
        size="small"
        placeholder="选一个或几个班"
        style="width: 280px"
      >
        <el-option v-for="c in data?.options.classes || []" :key="c" :label="c" :value="c" />
      </el-select>
      <el-select
        v-if="mode === 'students'"
        v-model="pickStudents"
        multiple
        filterable
        collapse-tags
        collapse-tags-tooltip
        :multiple-limit="MAX_STUDENTS"
        size="small"
        placeholder="搜姓名、学号，最多选 8 人"
        style="width: 360px"
      >
        <el-option
          v-for="o in data?.options.students || []"
          :key="o.sub_id"
          :label="studentLabel(o)"
          :value="o.sub_id"
        />
      </el-select>
      <span class="scope">现在看的是：<b>{{ scopeText }}</b></span>
    </section>

    <el-alert v-if="failed" type="error" :closable="false" :title="failed" class="gap" />

    <template v-if="data">
      <el-empty v-if="!s.count" description="这个范围里还没有人交卷" />

      <template v-else>
        <!-- 结论 -->
        <section class="card conclusions">
          <h2>自动结论</h2>
          <ol>
            <li v-for="(t, i) in data.conclusions" :key="i">{{ t }}</li>
          </ol>
        </section>

        <!-- 指标 -->
        <section class="kpis">
          <div class="kpi"><span>参考人数</span><b>{{ s.count }}</b></div>
          <div class="kpi"><span>平均分</span><b>{{ s.avg }}</b><em>/ {{ s.full }}　得分率 {{ s.avg_rate }}%</em></div>
          <div class="kpi"><span>中位数</span><b>{{ s.median }}</b></div>
          <div class="kpi"><span>最高 / 最低</span><b>{{ s.max }} / {{ s.min }}</b></div>
          <div class="kpi"><span>标准差</span><b>{{ s.std }}</b></div>
          <div class="kpi"><span>及格率</span><b>{{ s.pass_rate }}%</b><em>及格线 {{ data.pass_line }}%</em></div>
          <div class="kpi"><span>优秀率</span><b>{{ s.excellent_rate }}%</b><em>≥85%</em></div>
          <div class="kpi"><span>低分率</span><b>{{ s.low_rate }}%</b><em>&lt;40%</em></div>
          <div class="kpi"><span>满分</span><b>{{ s.full_marks }}</b><em>人</em></div>
          <div class="kpi" :class="{ warn: s.pending }">
            <span>待老师复核</span><b>{{ s.pending }}</b><em>份</em>
          </div>
        </section>

        <!-- 学生对比 -->
        <template v-if="data.compare.length">
          <section class="grid2">
            <div class="card">
              <h2>知识范围得分率对比</h2>
              <EChart :option="compareScopeOpt" height="320px" label="所选学生在各知识范围的得分率" />
            </div>
            <div class="card">
              <h2>大题得分率对比</h2>
              <EChart :option="compareSectionOpt" height="320px" label="所选学生在各大题的得分率" />
            </div>
          </section>
          <section class="card">
            <h2>所选学生</h2>
            <el-table :data="data.compare" size="small" border>
              <el-table-column prop="name" label="姓名" width="100" />
              <el-table-column prop="class" label="班级" width="120" />
              <el-table-column prop="score" label="总分" width="80" sortable />
              <el-table-column label="得分率" width="90" sortable :sort-by="r => r.rate">
                <template #default="{ row }">{{ row.rate }}%</template>
              </el-table-column>
              <el-table-column label="全场名次" width="100">
                <template #default="{ row }">{{ row.rank }} / {{ row.of }}</template>
              </el-table-column>
              <el-table-column label="各知识范围得分率">
                <template #default="{ row }">
                  <span v-for="g in row.by_scope" :key="g.name" class="chip">
                    {{ g.name }} <b :class="rateClass(g.rate)">{{ g.rate ?? '—' }}%</b>
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </section>
        </template>

        <section class="grid2">
          <div class="card">
            <h2>分数段分布 <a class="tbl no-print" @click="toggle('bands')">{{ tables.bands ? '收起数据' : '看数据' }}</a></h2>
            <EChart :option="bandsOpt" label="各分数段的人数" />
            <el-table v-if="tables.bands" :data="data.bands" size="small" border>
              <el-table-column prop="label" label="分数段" />
              <el-table-column prop="count" label="人数" />
            </el-table>
          </div>
          <div class="card">
            <h2>知识范围掌握情况 <a class="tbl no-print" @click="toggle('scopes')">{{ tables.scopes ? '收起数据' : '看数据' }}</a></h2>
            <EChart :option="scopeOpt" :axis-tip="plainTip" label="各知识范围的得分率" />
            <el-table v-if="tables.scopes" :data="data.scopes" size="small" border>
              <el-table-column prop="name" label="知识范围" />
              <el-table-column prop="questions" label="题数" width="70" />
              <el-table-column label="满分 / 平均" width="120">
                <template #default="{ row }">{{ row.full }} / {{ row.avg }}</template>
              </el-table-column>
              <el-table-column label="得分率" width="90">
                <template #default="{ row }"><span :class="rateClass(row.rate)">{{ row.rate }}%</span></template>
              </el-table-column>
            </el-table>
          </div>
        </section>

        <section v-if="data.classes.length > 1" class="grid2">
          <div class="card">
            <h2>班级对比 <a class="tbl no-print" @click="toggle('classes')">{{ tables.classes ? '收起数据' : '看数据' }}</a></h2>
            <EChart :option="classRateOpt" height="320px" label="各班平均得分率、及格率、优秀率" />
          </div>
          <div class="card">
            <h2>各班分数分布（箱线图）</h2>
            <EChart :option="boxOpt" height="320px" label="各班分数的最高、四分位、中位数、最低" />
          </div>
          <div v-if="tables.classes" class="card span2">
            <el-table :data="data.classes" size="small" border>
              <el-table-column prop="name" label="班级" />
              <el-table-column prop="count" label="人数" width="70" />
              <el-table-column prop="avg" label="平均分" width="80" sortable />
              <el-table-column prop="median" label="中位数" width="80" />
              <el-table-column prop="max" label="最高" width="70" />
              <el-table-column prop="min" label="最低" width="70" />
              <el-table-column prop="std" label="标准差" width="80" />
              <el-table-column label="及格率" width="90" sortable :sort-by="r => r.pass_rate">
                <template #default="{ row }">{{ row.pass_rate }}%</template>
              </el-table-column>
              <el-table-column label="优秀率" width="90">
                <template #default="{ row }">{{ row.excellent_rate }}%</template>
              </el-table-column>
            </el-table>
          </div>
        </section>

        <section class="card">
          <h2>每题得分率 <a class="tbl no-print" @click="toggle('questions')">{{ tables.questions ? '收起数据' : '看数据' }}</a></h2>
          <EChart :option="questionOpt" height="300px" label="每道题的得分率" />
          <el-table v-if="tables.questions" :data="data.questions" size="small" border max-height="420">
            <el-table-column prop="no" label="题号" width="64" sortable />
            <el-table-column prop="type" label="题型" width="80" />
            <el-table-column prop="section" label="大题" width="130" show-overflow-tooltip />
            <el-table-column prop="scope" label="知识范围" width="130" show-overflow-tooltip />
            <el-table-column prop="stem" label="题干" min-width="200" show-overflow-tooltip />
            <el-table-column label="均分 / 满分" width="100">
              <template #default="{ row }">{{ row.avg }} / {{ row.score }}</template>
            </el-table-column>
            <el-table-column label="得分率" width="90" sortable :sort-by="r => r.rate ?? -1">
              <template #default="{ row }"><span :class="rateClass(row.rate)">{{ row.rate ?? '—' }}%</span></template>
            </el-table-column>
            <el-table-column prop="discrimination" label="区分度" width="84" sortable />
            <el-table-column prop="blank" label="未作答" width="76" />
          </el-table>
        </section>

        <section class="grid2">
          <div class="card">
            <h2>大题得分率</h2>
            <EChart :option="sectionOpt" :axis-tip="plainTip" label="各大题的得分率" />
          </div>
          <div class="card">
            <h2>难度与区分度</h2>
            <EChart :option="discOpt" label="每道题的得分率和区分度" />
            <p class="note">越往右越容易；越往上越能区分会的和不会的。落在虚线下面的题值得回头看看。</p>
          </div>
        </section>

        <section v-if="opsRows.length" class="card">
          <h2>操作题每一步的通过率</h2>
          <EChart :option="opsOpt" :height="Math.max(220, opsRows.length * 30 + 40) + 'px'"
            label="操作题各检查点的通过率" :axis-tip="opsTip" />
          <p class="note">左边的文字太长时会截短，鼠标停在上面能看到完整的小题、通过人数和这道题的题干。</p>

          <div class="ops-rank">
            <div class="ops-rank-head">
              <h3>每道操作题的得分小题排名</h3>
              <el-radio-group v-model="opsOrder" size="small" class="no-print">
                <el-radio-button value="good">从好到差</el-radio-button>
                <el-radio-button value="bad">从差到好</el-radio-button>
              </el-radio-group>
            </div>
            <p class="note">每道题单独排名，不和别的题混在一起比。名次按通过率从高到低算，通过率一样的并列；「从差到好」只是倒过来列，讲评时先看最上面几步。</p>
            <div class="ops-grid">
              <div v-for="o in opsRanks" :key="o.id" class="ops-q">
                <h4>第 {{ o.no }} 题
                  <span v-if="o.rate !== null && o.rate !== undefined" class="ops-rate">本题得分率
                    <span :class="rateClass(o.rate)">{{ o.rate }}%</span></span>
                </h4>
                <el-tooltip :content="o.stem" placement="top-start" :show-after="200"
                  :popper-style="{ maxWidth: '520px', whiteSpace: 'pre-line' }">
                  <p class="ops-stem">{{ o.stem }}</p>
                </el-tooltip>
                <el-table :data="o.rows" size="small" border>
                  <el-table-column prop="rank" label="名次" width="56" align="center" />
                  <el-table-column prop="desc" label="得分小题" min-width="140" />
                  <el-table-column label="通过率" width="74" align="right">
                    <template #default="{ row }"><span :class="rateClass(row.pass_rate)">{{ row.pass_rate }}%</span></template>
                  </el-table-column>
                  <el-table-column label="通过人数" width="78" align="right">
                    <template #default="{ row }">{{ row.total ? `${row.passed}/${row.total}` : '—' }}</template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </div>
        </section>

        <section class="card">
          <h2>名次</h2>
          <el-table :data="data.ranking" size="small" border max-height="520"
            :default-sort="{ prop: 'rank', order: 'ascending' }">
            <el-table-column prop="rank" label="名次" width="72" sortable />
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column prop="class" label="班级" width="130" show-overflow-tooltip />
            <el-table-column prop="no" label="学号" width="120" />
            <el-table-column prop="score" label="总分" width="84" sortable />
            <el-table-column label="得分率" width="90">
              <template #default="{ row }"><span :class="rateClass(row.rate)">{{ row.rate }}%</span></template>
            </el-table-column>
            <el-table-column prop="objective" label="客观题" width="84" />
            <el-table-column prop="subjective" label="操作题" width="84" />
          </el-table>
        </section>
      </template>
    </template>
    <div v-else-if="loading" class="loading" v-loading="true" />
  </div>
</template>

<style scoped>
.page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px 16px 40px;
  color: var(--el-text-color-primary);
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}
.title h1 {
  display: inline;
  font-size: 20px;
  margin: 0 12px 0 0;
}
.exam {
  color: var(--el-text-color-secondary);
}
.tools {
  display: flex;
  align-items: center;
  gap: 10px;
}
.upd {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.scope {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.gap {
  margin-bottom: 12px;
}
.card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 14px;
  min-width: 0;
}
.card h2 {
  font-size: 15px;
  margin: 0 0 8px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.tbl {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-color-primary);
  cursor: pointer;
}
.conclusions ol {
  margin: 0;
  padding-left: 22px;
  line-height: 1.9;
}
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.kpi {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}
.kpi span {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.kpi b {
  font-size: 22px;
  font-family: ui-monospace, Consolas, monospace;
}
.kpi em {
  font-style: normal;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 6px;
}
.kpi.warn b {
  color: var(--el-color-warning);
}
.grid2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 14px;
}
.grid2 > .card {
  margin-bottom: 14px;
}
.span2 {
  grid-column: 1 / -1;
}
.chip {
  display: inline-block;
  margin: 2px 10px 2px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ok {
  color: var(--el-color-success);
}
.no {
  color: var(--el-color-danger);
}
.ops-rank {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.ops-rank-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.ops-rank-head h3 {
  font-size: 14px;
  margin: 0;
}
.ops-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 14px;
  margin-top: 10px;
}
.ops-q {
  min-width: 0;
}
.ops-q h4 {
  font-size: 14px;
  margin: 0 0 4px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.ops-rate {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}
.ops-stem {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: help;
}
@media (max-width: 520px) {
  .ops-grid {
    grid-template-columns: 1fr;
  }
}
.note {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 6px 0 0;
}
.loading {
  height: 300px;
}
@media (max-width: 520px) {
  .grid2 {
    grid-template-columns: 1fr;
  }
}
@media print {
  .no-print {
    display: none !important;
  }
  .page {
    max-width: none;
    padding: 0;
  }
  .card {
    break-inside: avoid;
  }
}
</style>

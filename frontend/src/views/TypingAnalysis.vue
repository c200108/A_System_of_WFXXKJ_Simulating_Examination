<script setup>
/**
 * 打字学情分析：从「打字成绩」页新开一个标签页，整页看图（2.12.0）。
 *
 * - 看什么：模块（中文 / 英文 / 键盘 / 全部）× 时间（近 7 / 30 / 90 天 / 全部）；
 * - 看谁：全体 / 某几个班 / 选几个学生对比；选择记在地址栏里，链接发给别的老师打开就是同一个视角；
 * - 每 30 秒重新拉一次（切到别的标签页时暂停），学生在练，这边的图和结论自己会变；
 * - 结论是服务端按数据写的（services/typing_analysis.py），这里只负责画。
 *
 * 图的规矩和「成绩分析」一样：一张图一个纵轴；颜色按系列固定顺序、不随排名变；
 * 两个以上系列一定有图例；每张图下面都能展开看原始数字。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import EChart from '../components/EChart.vue'

const route = useRoute()
const router = useRouter()

const data = ref(null)
const loading = ref(false)
const failed = ref('')
const auto = ref(true)
const tables = reactive({})

const module = ref('中文')
const days = ref(30)
const mode = ref('all')              // all / classes / students
const pickClasses = ref([])
const pickStudents = ref([])
const MAX_STUDENTS = 8               // 折线最多 8 条：配色只验证到 8 个

// ---------------------------------------------------------------- 配色（与成绩分析同一套）
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
function params() {
  const p = { module: module.value === '全部' ? '' : module.value, days: days.value }
  if (mode.value === 'classes' && pickClasses.value.length) p.classes = pickClasses.value
  if (mode.value === 'students' && pickStudents.value.length) p.students = pickStudents.value
  return p
}
async function load(quiet = false) {
  if (!quiet) loading.value = true
  failed.value = ''
  try {
    data.value = await api.typingAnalysis(params())
  } catch {
    failed.value = '数据没取到，稍后会自动再试'
  } finally {
    loading.value = false
  }
}
function syncQuery() {
  const q = { module: module.value, days: String(days.value) }
  if (mode.value === 'classes' && pickClasses.value.length) q.classes = pickClasses.value.join(',')
  if (mode.value === 'students' && pickStudents.value.length) q.students = pickStudents.value.join(',')
  router.replace({ query: q })
}
watch([module, days, mode, pickClasses, pickStudents], () => {
  syncQuery()
  load()
})

let timer = null
function tick() {
  if (auto.value && !document.hidden) load(true)
}
onMounted(() => {
  document.title = '打字学情分析'
  const q = route.query
  // 地址栏带着视角的（成绩页跳过来的、别的老师发来的）：照着选上，watch 会去取数
  let changed = false
  if (q.module && ['中文', '英文', '键盘', '全部'].includes(q.module)) { module.value = q.module; changed = true }
  if (q.days !== undefined && !Number.isNaN(Number(q.days))) { days.value = Number(q.days); changed = true }
  if (q.students) {
    mode.value = 'students'
    pickStudents.value = String(q.students).split(',').filter(Boolean)
    changed = true
  } else if (q.classes) {
    mode.value = 'classes'
    pickClasses.value = String(q.classes).split(',').filter(Boolean)
    changed = true
  }
  if (!changed) load()
  timer = setInterval(tick, 30000)
  document.addEventListener('visibilitychange', tick)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', tick)
})

const s = computed(() => data.value?.summary || {})
const speedy = computed(() => !!data.value?.speedy)
const unit = computed(() => (module.value === '英文' ? '字母/分' : '字/分'))
const updated = computed(() => (data.value?.updated_at || '').slice(11, 19))
const scopeText = computed(() => {
  if (!data.value) return ''
  const sc = data.value.scope || {}
  if (sc.kind === 'classes') return `班级：${(sc.classes || []).join('、')}`
  if (sc.kind === 'students') return `学生对比：${data.value.compare.map(c => c.name).join('、')}`
  return '全体学生'
})
const fmt = sec => (sec === null || sec === undefined ? '—'
  : `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`)

// ---------------------------------------------------------------- 图
const grid = (extra = {}) => ({ left: 8, right: 16, top: 24, bottom: 8, containLabel: true, ...extra })
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
    trigger: 'item', backgroundColor: ink.value.surface, borderColor: ink.value.line,
    textStyle: { color: ink.value.text }, confine: true, ...extra
  }
}
function bar(color, extra = {}) {
  return { type: 'bar', barMaxWidth: 34, itemStyle: { color, borderRadius: [4, 4, 0, 0] }, ...extra }
}
function line(color, extra = {}) {
  return {
    type: 'line', lineStyle: { width: 2, color }, itemStyle: { color, borderColor: ink.value.surface, borderWidth: 2 },
    symbolSize: 8, connectNulls: false, ...extra
  }
}
const pctAxis = () => ({ type: 'value', min: 0, max: 100, axisLabel: { color: ink.value.muted, formatter: '{value}%' },
  splitLine: { lineStyle: { color: ink.value.line } } })
const valAxis = () => ({ type: 'value', minInterval: 1, ...axisStyle(), axisLine: { show: false } })
const catAxis = (names, extra = {}) => ({ type: 'category', data: names, ...axisStyle(), splitLine: { show: false }, ...extra })
const countLabel = () => ({ show: true, position: 'top', color: ink.value.muted, formatter: p => (p.value ? p.value : '') })

function bandsOpt(rows, what) {
  return {
    grid: grid(),
    tooltip: tooltip({ formatter: p => `${what} ${p.name}：${p.value} 次` }),
    xAxis: catAxis(rows.map(x => x.label)),
    yAxis: valAxis(),
    series: [bar(palette.value[0], { data: rows.map(x => x.count), label: countLabel() })]
  }
}
const speedBandsOpt = computed(() => bandsOpt(data.value?.speed_bands || [], '速度'))
const accBandsOpt = computed(() => bandsOpt(data.value?.accuracy_bands || [], '正确率'))
const starsOpt = computed(() => bandsOpt(data.value?.stars || [], ''))

const points = computed(() => data.value?.trend?.points || [])
const countTrendOpt = computed(() => ({
  grid: grid(),
  tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow' },
    formatter: ps => `${ps[0].name}<br/>练习 ${ps[0].value} 次，${points.value[ps[0].dataIndex].students} 人` }),
  xAxis: catAxis(points.value.map(p => p.label)),
  yAxis: valAxis(),
  series: [bar(palette.value[0], { data: points.value.map(p => p.count), barMaxWidth: 22 })]
}))
function metricTrend(key, pct) {
  return {
    grid: grid(),
    tooltip: tooltip({ trigger: 'axis', valueFormatter: v => (v === null || v === undefined ? '没人练' : pct ? `${v}%` : `${v} ${unit.value}`) }),
    xAxis: catAxis(points.value.map(p => p.label), { boundaryGap: false }),
    yAxis: pct ? pctAxis() : valAxis(),
    series: [line(palette.value[0], { name: pct ? '平均正确率' : '平均速度', data: points.value.map(p => p[key]) })]
  }
}
const speedTrendOpt = computed(() => metricTrend('avg_speed', false))
const accTrendOpt = computed(() => metricTrend('avg_accuracy', true))

const cls = computed(() => data.value?.classes || [])
const classSpeedOpt = computed(() => ({
  grid: grid(),
  tooltip: tooltip({ formatter: p => `${p.name}：平均 ${p.value} ${unit.value}` }),
  xAxis: catAxis(cls.value.map(c => c.name)),
  yAxis: valAxis(),
  series: [bar(palette.value[0], { data: cls.value.map(c => c.avg_speed), label: countLabel() })]
}))
const classRateOpt = computed(() => {
  const names = ['平均正确率', '达标率']
  const keys = ['avg_accuracy', 'reach_rate']
  return {
    grid: grid({ top: 36 }),
    legend: { top: 0, textStyle: { color: ink.value.text }, itemWidth: 12, itemHeight: 12 },
    tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: v => `${v}%` }),
    xAxis: catAxis(cls.value.map(c => c.name)),
    yAxis: pctAxis(),
    series: keys.map((k, i) => bar(palette.value[i], { name: names[i], data: cls.value.map(c => c[k]), barGap: '8%' }))
  }
})
const boxOpt = computed(() => ({
  grid: grid(),
  tooltip: tooltip({
    formatter: p => {
      const v = p.data.length === 6 ? p.data.slice(1) : p.data
      return `${p.name}（每个学生的平均速度）<br/>最快 ${v[4]}　上四分位 ${v[3]}<br/>中位数 ${v[2]}<br/>下四分位 ${v[1]}　最慢 ${v[0]}`
    }
  }),
  xAxis: catAxis(cls.value.map(c => c.name)),
  yAxis: valAxis(),
  series: [{
    type: 'boxplot', data: cls.value.map(c => c.box), boxWidth: [12, 36],
    itemStyle: { color: dark.value ? '#184f95' : '#cde2fb', borderColor: palette.value[0], borderWidth: 2 }
  }]
}))

function compareOpt(key, pct) {
  const c = data.value?.compare || []
  const longest = Math.max(0, ...c.map(x => x.points.length))
  return {
    grid: grid({ top: 36, bottom: 20 }),
    legend: { top: 0, textStyle: { color: ink.value.text }, itemWidth: 12, itemHeight: 12 },
    tooltip: tooltip({ trigger: 'axis', valueFormatter: v => (v === null || v === undefined ? '—' : pct ? `${v}%` : `${v} ${unit.value}`) }),
    xAxis: catAxis(Array.from({ length: longest }, (_, i) => `第${i + 1}次`), { boundaryGap: false }),
    yAxis: pct ? pctAxis() : valAxis(),
    series: c.map((st, i) => line(palette.value[i % palette.value.length], {
      name: st.name, data: st.points.map(p => p[key])
    }))
  }
}
const compareSpeedOpt = computed(() => compareOpt('speed', false))
const compareAccOpt = computed(() => compareOpt('accuracy', true))

function studentLabel(o) {
  return `${o.name}　${o.class}　（${o.count} 次）`
}
function printPage() {
  window.print()
}
function toggle(name) {
  tables[name] = !tables[name]
}
function signed(v) {
  return v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v}`
}
</script>

<template>
  <div class="page">
    <header class="top">
      <div class="title"><h1>打字学情分析</h1></div>
      <div class="tools no-print">
        <span v-if="updated" class="upd">数据更新于 {{ updated }}</span>
        <el-switch v-model="auto" size="small" active-text="自动刷新" />
        <el-button size="small" :loading="loading" @click="load()">刷新</el-button>
        <el-button size="small" @click="printPage">打印</el-button>
      </div>
    </header>

    <section class="filters no-print">
      <el-radio-group v-model="module" size="small">
        <el-radio-button v-for="m in ['中文', '英文', '键盘', '全部']" :key="m" :value="m">{{ m }}</el-radio-button>
      </el-radio-group>
      <el-select v-model="days" size="small" style="width: 110px">
        <el-option :value="7" label="近 7 天" />
        <el-option :value="30" label="近 30 天" />
        <el-option :value="90" label="近 90 天" />
        <el-option :value="0" label="全部时间" />
      </el-select>
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="all">全体</el-radio-button>
        <el-radio-button value="classes">按班级</el-radio-button>
        <el-radio-button value="students">学生对比</el-radio-button>
      </el-radio-group>
      <el-select v-if="mode === 'classes'" v-model="pickClasses" multiple collapse-tags collapse-tags-tooltip
        size="small" placeholder="选一个或几个班" style="width: 260px">
        <el-option v-for="c in data?.options.classes || []" :key="c" :label="c" :value="c" />
      </el-select>
      <el-select v-if="mode === 'students'" v-model="pickStudents" multiple filterable collapse-tags
        collapse-tags-tooltip :multiple-limit="MAX_STUDENTS" size="small" placeholder="搜姓名，最多选 8 人"
        style="width: 320px">
        <el-option v-for="o in data?.options.students || []" :key="o.key" :label="studentLabel(o)" :value="o.key" />
      </el-select>
      <span class="scope">现在看的是：<b>{{ scopeText }}</b></span>
    </section>

    <el-alert v-if="failed" type="error" :closable="false" :title="failed" class="gap" />

    <template v-if="data">
      <el-empty v-if="!s.count" description="这个范围里还没有练习记录" />
      <template v-else>
        <section class="card conclusions">
          <h2>自动结论</h2>
          <ol><li v-for="(t, i) in data.conclusions" :key="i">{{ t }}</li></ol>
        </section>

        <section class="kpis">
          <div class="kpi"><span>练习人次</span><b>{{ s.count }}</b></div>
          <div class="kpi"><span>参与人数</span><b>{{ s.students }}</b><em>人均 {{ s.per_student }} 次</em></div>
          <template v-if="speedy">
            <div class="kpi"><span>平均速度</span><b>{{ s.avg_speed }}</b><em>{{ unit }}</em></div>
            <div class="kpi"><span>中位数 / 最快</span><b>{{ s.median_speed }} / {{ s.max_speed }}</b></div>
          </template>
          <div class="kpi"><span>平均正确率</span><b>{{ s.avg_accuracy }}%</b></div>
          <div class="kpi"><span>达标率</span><b>{{ s.reach_rate }}%</b><em>两星及以上</em></div>
          <div class="kpi"><span>三星</span><b>{{ s.three_star_rate }}%</b></div>
          <div class="kpi"><span>平均用时</span><b>{{ fmt(s.avg_duration) }}</b></div>
          <div class="kpi"><span>累计练习</span><b>{{ s.minutes }}</b><em>分钟</em></div>
          <div class="kpi" :class="{ warn: s.once_only }"><span>只练过一次</span><b>{{ s.once_only }}</b><em>人</em></div>
        </section>

        <template v-if="data.compare.length">
          <section class="grid2">
            <div v-if="speedy" class="card">
              <h2>每次练习的速度</h2>
              <EChart :option="compareSpeedOpt" height="300px" label="所选学生每次练习的速度" />
            </div>
            <div class="card">
              <h2>每次练习的正确率</h2>
              <EChart :option="compareAccOpt" height="300px" label="所选学生每次练习的正确率" />
            </div>
          </section>
        </template>

        <section class="grid2">
          <div class="card">
            <h2>每天练习人次 <a class="tbl no-print" @click="toggle('trend')">{{ tables.trend ? '收起数据' : '看数据' }}</a></h2>
            <EChart :option="countTrendOpt" label="每天（或每周）的练习人次" />
            <el-table v-if="tables.trend" :data="points" size="small" border max-height="300">
              <el-table-column prop="label" label="日期" />
              <el-table-column prop="count" label="人次" width="70" />
              <el-table-column prop="students" label="人数" width="70" />
              <el-table-column v-if="speedy" prop="avg_speed" label="平均速度" width="90" />
              <el-table-column prop="avg_accuracy" label="平均正确率" width="100" />
            </el-table>
          </div>
          <div v-if="speedy" class="card">
            <h2>平均速度走势</h2>
            <EChart :option="speedTrendOpt" label="每天（或每周）的平均速度" />
          </div>
          <div class="card">
            <h2>平均正确率走势</h2>
            <EChart :option="accTrendOpt" label="每天（或每周）的平均正确率" />
          </div>
        </section>

        <section class="grid2">
          <div v-if="speedy" class="card">
            <h2>速度分布（{{ unit }}） <a class="tbl no-print" @click="toggle('speed')">{{ tables.speed ? '收起数据' : '看数据' }}</a></h2>
            <EChart :option="speedBandsOpt" label="各速度段的练习次数" />
            <el-table v-if="tables.speed" :data="data.speed_bands" size="small" border>
              <el-table-column prop="label" label="速度段" />
              <el-table-column prop="count" label="次数" />
            </el-table>
          </div>
          <div class="card">
            <h2>正确率分布 <a class="tbl no-print" @click="toggle('acc')">{{ tables.acc ? '收起数据' : '看数据' }}</a></h2>
            <EChart :option="accBandsOpt" label="各正确率段的练习次数" />
            <el-table v-if="tables.acc" :data="data.accuracy_bands" size="small" border>
              <el-table-column prop="label" label="正确率" />
              <el-table-column prop="count" label="次数" />
            </el-table>
          </div>
          <div class="card">
            <h2>星级构成</h2>
            <EChart :option="starsOpt" label="各星级的练习次数" />
          </div>
          <div class="card">
            <h2>难度</h2>
            <el-table :data="data.difficulties" size="small" border>
              <el-table-column prop="name" label="难度" width="80" />
              <el-table-column prop="count" label="次数" width="70" />
              <el-table-column label="占比" width="80"><template #default="{ row }">{{ row.share }}%</template></el-table-column>
              <el-table-column v-if="speedy" prop="avg_speed" label="平均速度" />
              <el-table-column label="正确率"><template #default="{ row }">{{ row.avg_accuracy }}%</template></el-table-column>
              <el-table-column label="达标率"><template #default="{ row }">{{ row.reach_rate }}%</template></el-table-column>
            </el-table>
            <el-table v-if="module === '全部'" :data="data.by_module" size="small" border class="gap-top">
              <el-table-column prop="name" label="模块" width="80" />
              <el-table-column prop="count" label="次数" width="70" />
              <el-table-column prop="students" label="人数" width="70" />
              <el-table-column label="平均速度"><template #default="{ row }">{{ row.avg_speed ?? '—' }}</template></el-table-column>
              <el-table-column label="正确率"><template #default="{ row }">{{ row.avg_accuracy }}%</template></el-table-column>
            </el-table>
          </div>
        </section>

        <!-- 学生对比时不看班级：两三个人谈不上班与班之间 -->
        <section v-if="!data.compare.length" class="grid2">
          <div v-if="speedy" class="card">
            <h2>各班平均速度 <a class="tbl no-print" @click="toggle('classes')">{{ tables.classes ? '收起数据' : '看数据' }}</a></h2>
            <EChart :option="classSpeedOpt" label="各班学生平均速度" />
          </div>
          <div class="card">
            <h2>各班正确率与达标率</h2>
            <EChart :option="classRateOpt" height="300px" label="各班平均正确率和达标率" />
          </div>
          <div v-if="speedy && cls.length > 1" class="card">
            <h2>各班速度分布（箱线图）</h2>
            <EChart :option="boxOpt" label="各班学生平均速度的最快、四分位、中位数、最慢" />
          </div>
          <div v-if="tables.classes || !speedy" class="card span2">
            <el-table :data="cls" size="small" border>
              <el-table-column prop="name" label="班级" />
              <el-table-column label="练过 / 名单" width="110">
                <template #default="{ row }">{{ row.students }} / {{ row.roster ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="参与率" width="90" sortable :sort-by="r => r.participation ?? -1">
                <template #default="{ row }">{{ row.participation === null ? '—' : row.participation + '%' }}</template>
              </el-table-column>
              <el-table-column prop="count" label="人次" width="70" sortable />
              <el-table-column prop="per_student" label="人均" width="70" />
              <el-table-column v-if="speedy" prop="avg_speed" label="平均速度" width="90" sortable />
              <el-table-column label="正确率" width="90"><template #default="{ row }">{{ row.avg_accuracy }}%</template></el-table-column>
              <el-table-column label="达标率" width="90"><template #default="{ row }">{{ row.reach_rate }}%</template></el-table-column>
            </el-table>
          </div>
        </section>

        <section class="card">
          <h2>学生名单</h2>
          <el-table :data="data.ranking" size="small" border max-height="520">
            <el-table-column prop="rank" label="名次" width="70" sortable />
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column prop="class" label="班级" min-width="110" show-overflow-tooltip />
            <el-table-column prop="count" label="练习次数" width="96" sortable />
            <el-table-column v-if="speedy" prop="best_speed" label="最快" width="80" sortable />
            <el-table-column v-if="speedy" prop="avg_speed" label="平均速度" width="96" sortable />
            <el-table-column prop="avg_accuracy" label="正确率" width="90" sortable>
              <template #default="{ row }">{{ row.avg_accuracy }}%</template>
            </el-table-column>
            <el-table-column prop="reach_rate" label="达标率" width="90" sortable>
              <template #default="{ row }">{{ row.reach_rate }}%</template>
            </el-table-column>
            <el-table-column prop="progress" label="进步" width="84" sortable :sort-by="r => r.progress ?? -9999">
              <template #default="{ row }">
                <span :class="row.progress > 0 ? 'ok' : row.progress < 0 ? 'no' : ''">{{ signed(row.progress) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="last_at" label="最近一次" width="140" sortable />
          </el-table>
          <p class="note">进步：这段时间里最后 3 次的平均{{ speedy ? '速度' : '正确率' }}减最初 3 次的，练满 4 次才算。</p>
        </section>
      </template>
    </template>
    <div v-else-if="loading" v-loading="true" class="loading" />
  </div>
</template>

<style scoped>
.page { max-width: 1280px; margin: 0 auto; padding: 16px 16px 40px; color: var(--el-text-color-primary); }
.top { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.title h1 { display: inline; font-size: 20px; margin: 0; }
.tools { display: flex; align-items: center; gap: 10px; }
.upd { color: var(--el-text-color-secondary); font-size: 12px; }
.filters { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.scope { color: var(--el-text-color-secondary); font-size: 13px; }
.gap { margin-bottom: 12px; }
.gap-top { margin-top: 10px; }
.card {
  background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 8px;
  padding: 12px 14px; margin-bottom: 14px; min-width: 0;
}
.card h2 { font-size: 15px; margin: 0 0 8px; display: flex; align-items: baseline; gap: 10px; }
.tbl { font-size: 12px; font-weight: normal; color: var(--el-color-primary); cursor: pointer; }
.conclusions ol { margin: 0; padding-left: 22px; line-height: 1.9; }
.kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px; }
.kpi { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 10px 12px; }
.kpi span { display: block; color: var(--el-text-color-secondary); font-size: 12px; }
.kpi b { font-size: 22px; font-family: ui-monospace, Consolas, monospace; }
.kpi em { font-style: normal; color: var(--el-text-color-secondary); font-size: 12px; margin-left: 6px; }
.kpi.warn b { color: var(--el-color-warning); }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 14px; }
.grid2 > .card { margin-bottom: 14px; }
.span2 { grid-column: 1 / -1; }
.ok { color: var(--el-color-success); }
.no { color: var(--el-color-danger); }
.note { color: var(--el-text-color-secondary); font-size: 12px; margin: 6px 0 0; }
.loading { height: 300px; }
@media (max-width: 520px) { .grid2 { grid-template-columns: 1fr; } }
@media print {
  .no-print { display: none !important; }
  .page { max-width: none; padding: 0; }
  .card { break-inside: avoid; }
}
</style>

<script setup>
/**
 * 某个 API 的数据大图（2.16.0）。「API → 数据大图」标签页和投屏页（/js/api-board/:id）共用。
 *
 * 每 10 秒重新取一次（切到别的标签页时暂停），学生在交，图自己会动。
 * 没有数据的图不画：答题类才有逐题正确率，评价类才有雷达图和互评矩阵。
 * 投屏时可以一键隐去学生姓名。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import EChart from './EChart.vue'

const props = defineProps({
  apiId: { type: Number, required: true },
  big: { type: Boolean, default: false }
})

const data = ref(null)
const failed = ref('')
const auto = ref(true)
const hideNames = ref(props.big)
const f = reactive({ activity: '', class_name: '', page_url: '', type: '', minutes: 0 })

async function load(quiet = false) {
  try {
    const p = {}
    Object.entries(f).forEach(([k, v]) => { if (v) p[k] = v })
    data.value = await api.dataApiStats(props.apiId, p, quiet)
    failed.value = ''
  } catch {
    failed.value = '数据没取到，稍后会自动再试'
  }
}
let timer = null
function tick() {
  if (auto.value && !document.hidden) load(true)
}
onMounted(() => {
  load()
  timer = setInterval(tick, 10000)
})
onBeforeUnmount(() => clearInterval(timer))
watch(f, () => load())

// ---------------------------------------------------------------- 配色（与成绩分析同一套）
const dark = ref(props.big || document.documentElement.classList.contains('dark'))
const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']
}
const pal = computed(() => SERIES[dark.value ? 'dark' : 'light'])
const ink = computed(() => dark.value
  ? { text: '#d6d6d2', muted: '#8f8f8a', line: '#33363b' }
  : { text: '#52514e', muted: '#8a8a86', line: '#ebeef5' })
const fs = computed(() => (props.big ? 15 : 12))

function axisBase() {
  return {
    axisLabel: { color: ink.value.muted, fontSize: fs.value },
    axisLine: { lineStyle: { color: ink.value.line } },
    splitLine: { lineStyle: { color: ink.value.line } }
  }
}
function name(n) {
  if (!hideNames.value || !n) return n
  return n.length <= 1 ? '＊' : n[0] + '＊'.repeat(Math.min(2, n.length - 1))
}

const d = computed(() => data.value || {})
const hasScore = computed(() => d.value.avg_score != null)

const timelineOpt = computed(() => ({
  color: [pal.value[0]],
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 16, bottom: 30 },
  xAxis: { type: 'category', data: (d.value.timeline || []).map(x => x.t), ...axisBase() },
  yAxis: { type: 'value', minInterval: 1, ...axisBase() },
  series: [{ type: 'line', smooth: true, areaStyle: { opacity: 0.15 }, data: (d.value.timeline || []).map(x => x.n) }]
}))
const distOpt = computed(() => ({
  color: [pal.value[2]],
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 16, bottom: 40 },
  xAxis: { type: 'category', data: d.value.distribution?.labels || [], ...axisBase(), axisLabel: { ...axisBase().axisLabel, rotate: 30 } },
  yAxis: { type: 'value', minInterval: 1, name: '人次', nameTextStyle: { color: ink.value.muted }, ...axisBase() },
  series: [{ type: 'bar', barMaxWidth: 36, data: d.value.distribution?.values || [] }]
}))
const questionsJudged = computed(() => (d.value.questions || []).filter(q => q.rate != null))
const qOpt = computed(() => {
  const qs = [...questionsJudged.value].sort((a, b) => a.rate - b.rate).slice(0, 40)
  return {
    tooltip: {
      trigger: 'axis',
      formatter: ps => {
        const q = qs[ps[0].dataIndex]
        const ch = q.choices.map(([a, n]) => `${a}：${n}`).join('　')
        const wrong = q.wrong.length ? `<br>答错：${q.wrong.slice(0, 10).map(name).join('、')}${q.wrong.length > 10 ? '…' : ''}` : ''
        return `第 ${q.q} 题　正确率 ${q.rate}%（${q.n} 人次）<br>${ch}${wrong}`
      }
    },
    grid: { left: 60, right: 48, top: 10, bottom: 30 },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', color: ink.value.muted, fontSize: fs.value }, splitLine: { lineStyle: { color: ink.value.line } } },
    yAxis: { type: 'category', data: qs.map(q => `第${q.q}题`), ...axisBase() },
    series: [{
      type: 'bar', barMaxWidth: 22,
      data: qs.map(q => ({ value: q.rate, itemStyle: { color: q.rate < 60 ? pal.value[7] : q.rate < 85 ? pal.value[3] : pal.value[2] } })),
      label: { show: true, position: 'right', formatter: '{c}%', color: ink.value.text, fontSize: fs.value }
    }]
  }
})
const radar = computed(() => d.value.radar || [])
const radarOpt = computed(() => {
  const rs = radar.value
  const vals = rs.flatMap(r => [r.self, r.peer, r.other]).filter(v => v != null)
  const max = vals.some(v => v > 10) ? 100 : Math.max(5, Math.ceil(Math.max(...vals, 0)))
  const series = []
  const legend = []
  for (const [k, label, i] of [['self', '自评', 0], ['peer', '互评', 1], ['other', '评分', 2]]) {
    if (rs.some(r => r[k] != null)) {
      legend.push(label)
      series.push({ name: label, value: rs.map(r => r[k] ?? 0), lineStyle: { color: pal.value[i] }, itemStyle: { color: pal.value[i] }, areaStyle: { opacity: 0.12 } })
    }
  }
  return {
    tooltip: {},
    legend: { data: legend, bottom: 0, textStyle: { color: ink.value.text, fontSize: fs.value } },
    radar: { center: ['50%', '46%'], radius: '60%', indicator: rs.map(r => ({ name: r.item, max })), axisName: { color: ink.value.text, fontSize: fs.value }, splitLine: { lineStyle: { color: ink.value.line } }, splitArea: { show: false } },
    series: [{ type: 'radar', data: series }]
  }
})
const matrix = computed(() => d.value.peer_matrix || { raters: [], targets: [], cells: [] })
const heatOpt = computed(() => {
  const m = matrix.value
  const vals = m.cells.map(c => c[2])
  return {
    tooltip: { formatter: p => `${name(m.raters[p.value[1]])} → ${name(m.targets[p.value[0]])}：${p.value[2]}` },
    grid: { left: 80, right: 20, top: 10, bottom: 70 },
    xAxis: { type: 'category', data: m.targets.map(name), name: '被评人', ...axisBase(), axisLabel: { ...axisBase().axisLabel, rotate: 45 } },
    yAxis: { type: 'category', data: m.raters.map(name), name: '评价人', ...axisBase() },
    visualMap: { min: Math.min(...vals, 0), max: Math.max(...vals, 1), calculable: true, orient: 'horizontal', left: 'center', bottom: 0, itemHeight: 120, textStyle: { color: ink.value.muted }, inRange: { color: dark.value ? ['#1d2b3a', '#3987e5'] : ['#e8f1fb', '#2a78d6'] } },
    series: [{ type: 'heatmap', data: m.cells.map(c => [c[1], c[0], c[2]]), label: { show: m.cells.length <= 150, color: ink.value.text, fontSize: 11 } }]
  }
})
const classesOpt = computed(() => {
  const cs = d.value.classes || []
  const useRate = cs.some(c => c.avg_rate != null)
  return {
    color: [pal.value[0], pal.value[1]],
    tooltip: { trigger: 'axis' },
    legend: { data: ['人数', useRate ? '平均得分率' : '平均分'], bottom: 0, textStyle: { color: ink.value.text } },
    grid: { left: 44, right: 44, top: 16, bottom: 50 },
    xAxis: { type: 'category', data: cs.map(c => c.class), ...axisBase() },
    yAxis: [{ type: 'value', minInterval: 1, ...axisBase() }, { type: 'value', ...axisBase(), splitLine: { show: false } }],
    series: [
      { name: '人数', type: 'bar', barMaxWidth: 30, data: cs.map(c => c.people) },
      { name: useRate ? '平均得分率' : '平均分', type: 'line', yAxisIndex: 1, data: cs.map(c => (useRate ? c.avg_rate : c.avg)) }
    ]
  }
})
const kwOpt = computed(() => {
  const ks = (d.value.keywords || []).slice(0, 15).reverse()
  return {
    color: [pal.value[6]],
    tooltip: {},
    grid: { left: 60, right: 30, top: 10, bottom: 20 },
    xAxis: { type: 'value', minInterval: 1, ...axisBase() },
    yAxis: { type: 'category', data: ks.map(k => k[0]), ...axisBase(), axisLabel: { ...axisBase().axisLabel, interval: 0 } },
    series: [{ type: 'bar', barMaxWidth: 18, data: ks.map(k => k[1]) }]
  }
})
const typeOpt = computed(() => ({
  color: pal.value,
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, textStyle: { color: ink.value.text } },
  series: [{ type: 'pie', radius: ['40%', '68%'], top: -20, label: { color: ink.value.text }, data: (d.value.types || []).map(t => ({ name: t.name, value: t.n })) }]
}))
const completion = computed(() => {
  if (!d.value.expected) return null
  return Math.round((d.value.submitted_roster / d.value.expected) * 100)
})
function fmtTime(t) {
  return t ? String(t).slice(11, 19) : ''
}
</script>

<template>
  <div :class="['board', { big, dark }]">
    <div class="filters">
      <slot name="title" />
      <el-select v-model="f.activity" clearable filterable placeholder="全部活动" size="small" style="width: 150px">
        <el-option v-for="a in d.activities || []" :key="a.activity" :label="`${a.activity}（${a.n}）`" :value="a.activity" />
      </el-select>
      <el-select v-model="f.class_name" clearable placeholder="全部班级" size="small" style="width: 120px">
        <el-option v-for="c in (d.classes || []).filter(c => c.class !== '未填班级')" :key="c.class" :label="c.class" :value="c.class" />
      </el-select>
      <el-select v-model="f.page_url" clearable filterable placeholder="全部来源网页" size="small" style="width: 180px">
        <el-option v-for="p in d.pages || []" :key="p.page" :label="`${p.page}（${p.n}）`" :value="p.page" />
      </el-select>
      <el-select v-model="f.minutes" size="small" style="width: 110px">
        <el-option label="全部时间" :value="0" />
        <el-option label="最近 45 分钟" :value="45" />
        <el-option label="最近 2 小时" :value="120" />
        <el-option label="最近一天" :value="1440" />
        <el-option label="最近一周" :value="10080" />
      </el-select>
      <el-checkbox v-model="hideNames" size="small">隐去姓名</el-checkbox>
      <el-checkbox v-model="auto" size="small">每 10 秒刷新</el-checkbox>
      <span v-if="failed" class="warn">{{ failed }}</span>
    </div>

    <div v-if="data && !data.records" class="empty">还没有数据。把接收地址放进教学网页，学生提交后这里就会动起来。</div>

    <template v-if="data && data.records">
      <div class="kpis">
        <div class="kpi"><b>{{ d.people }}</b><span>提交人数</span></div>
        <div class="kpi" v-if="d.expected != null"><b>{{ d.submitted_roster }}/{{ d.expected }}</b><span>名单完成 {{ completion }}%</span></div>
        <div class="kpi"><b>{{ d.records }}</b><span>提交条数</span></div>
        <div class="kpi" v-if="hasScore"><b>{{ d.avg_rate != null ? d.avg_rate + '%' : d.avg_score }}</b><span>{{ d.avg_rate != null ? '平均得分率' : '平均分' }}</span></div>
        <div class="kpi" v-if="hasScore"><b>{{ d.max_score }} / {{ d.min_score }}</b><span>最高 / 最低分</span></div>
        <div class="kpi"><b>{{ d.last5min }}</b><span>最近 5 分钟</span></div>
        <div class="kpi"><b>{{ d.matched_people }}</b><span>对上名单的学生</span></div>
      </div>

      <div class="grid">
        <section class="panel">
          <h4>提交时间线</h4>
          <EChart :option="timelineOpt" :height="big ? '280px' : '220px'" label="每个时间段的提交数" />
        </section>
        <section class="panel" v-if="hasScore">
          <h4>成绩分布</h4>
          <EChart :option="distOpt" :height="big ? '280px' : '220px'" label="得分分布" />
        </section>
        <section class="panel" v-if="(d.types || []).length > 1">
          <h4>数据类型</h4>
          <EChart :option="typeOpt" :height="big ? '280px' : '220px'" label="各类型条数" />
        </section>
        <section class="panel wide" v-if="questionsJudged.length">
          <h4>逐题正确率 <small>从低到高，鼠标移上去看选项分布和答错的学生</small></h4>
          <EChart :option="qOpt" :height="Math.max(200, Math.min(40, questionsJudged.length) * (big ? 30 : 24) + 40) + 'px'" label="每道题的正确率" />
        </section>
        <section class="panel" v-if="radar.length >= 3">
          <h4>评价维度 <small>自评与互评对比</small></h4>
          <EChart :option="radarOpt" :height="big ? '340px' : '280px'" label="各评价维度平均分" />
        </section>
        <section class="panel" v-else-if="radar.length">
          <h4>评价维度</h4>
          <el-table :data="radar" size="small" border>
            <el-table-column prop="item" label="维度" />
            <el-table-column prop="self" label="自评" />
            <el-table-column prop="peer" label="互评" />
            <el-table-column prop="other" label="评分" />
          </el-table>
        </section>
        <section class="panel wide" v-if="matrix.cells.length">
          <h4>互评矩阵 <small>每格是评价人给被评人的平均分，一行全空就是这个人没评</small></h4>
          <EChart :option="heatOpt" :height="Math.max(260, matrix.raters.length * 22 + 110) + 'px'" label="互评矩阵" />
        </section>
        <section class="panel" v-if="(d.classes || []).length > 1">
          <h4>班级对比</h4>
          <EChart :option="classesOpt" :height="big ? '280px' : '240px'" label="各班人数和平均分" />
        </section>
        <section class="panel" v-if="(d.keywords || []).length">
          <h4>评语高频词</h4>
          <EChart :option="kwOpt" :height="big ? '300px' : '260px'" label="评语里出现最多的词" />
        </section>
        <section class="panel feed">
          <h4>最新提交</h4>
          <ul>
            <li v-for="x in d.latest" :key="x.id">
              <span class="t">{{ fmtTime(x.at) }}</span>
              <span class="n">{{ name(x.student) }}</span>
              <span class="c">{{ x.class }}</span>
              <span class="s" v-if="x.score != null">{{ x.score }}<template v-if="x.max_score != null">/{{ x.max_score }}</template></span>
            </li>
          </ul>
        </section>
        <section class="panel feed" v-if="d.missing && d.missing.length">
          <h4>名单里还没交的（{{ d.expected - d.submitted_roster }}）</h4>
          <div class="missing">
            <span v-for="m in d.missing" :key="m.no">{{ name(m.name) }}</span>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.board { min-height: 200px; }
.board.big { background: #15171a; color: #e6e6e3; padding: 18px 22px; min-height: 100vh; box-sizing: border-box; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.warn { color: var(--el-color-danger); font-size: 12px; }
.empty { padding: 60px 0; text-align: center; color: var(--el-text-color-secondary); }
.kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-bottom: 12px; }
.kpi { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 10px 14px; display: flex; flex-direction: column; }
.kpi b { font-size: 22px; }
.kpi span { font-size: 12px; color: var(--el-text-color-secondary); }
.big .kpi { border-color: #33363b; background: #1c1f23; }
.big .kpi b { font-size: 34px; }
.big .kpi span { font-size: 15px; color: #9a9a95; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; }
.panel { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 10px 12px; min-width: 0; }
.big .panel { border-color: #33363b; background: #1c1f23; }
.panel.wide { grid-column: 1 / -1; }
.panel h4 { margin: 0 0 6px; font-size: 14px; }
.big .panel h4 { font-size: 18px; }
.panel h4 small { font-weight: normal; color: var(--el-text-color-secondary); margin-left: 6px; font-size: 12px; }
.feed ul { list-style: none; margin: 0; padding: 0; max-height: 260px; overflow: auto; }
.feed li { display: flex; gap: 10px; padding: 3px 0; border-bottom: 1px dashed var(--el-border-color-lighter); font-size: 13px; }
.big .feed li { font-size: 16px; border-color: #2a2d31; }
.feed .t { color: var(--el-text-color-secondary); width: 64px; }
.feed .n { flex: 1; }
.feed .c { color: var(--el-text-color-secondary); }
.feed .s { font-weight: 600; }
.missing { display: flex; flex-wrap: wrap; gap: 6px 12px; max-height: 260px; overflow: auto; font-size: 13px; }
.big .missing { font-size: 16px; }
</style>

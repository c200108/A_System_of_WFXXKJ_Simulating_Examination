<script setup>
/**
 * 学生学情（2.16.0）：学生名单「学情」一列点进来。
 *
 * 一页四块：概况、考试（每场成绩、全体名次、班内名次、得分率走势）、打字（各模块、速度走势）、
 * 第三方教学网页（API 收到的这个学生的数据、自评与同伴评价）。
 * API 数据只算你自己建的 API（管理员看全部），各老师的 API 数据不互通。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import EChart from '../components/EChart.vue'

const route = useRoute()
const router = useRouter()
const data = ref(null)
const loading = ref(false)
const tab = ref('exams')
const detail = ref(null)

onMounted(async () => {
  loading.value = true
  try {
    data.value = await api.studentInsight(route.params.id)
  } finally {
    loading.value = false
  }
})

const dark = document.documentElement.classList.contains('dark')
const C = dark ? ['#3987e5', '#d95926', '#199e70', '#c98500'] : ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']
const ink = dark ? { muted: '#8f8f8a', line: '#33363b', text: '#d6d6d2' } : { muted: '#8a8a86', line: '#ebeef5', text: '#52514e' }
const axis = { axisLabel: { color: ink.muted }, axisLine: { lineStyle: { color: ink.line } }, splitLine: { lineStyle: { color: ink.line } } }

const stu = computed(() => data.value?.student || {})
const ex = computed(() => data.value?.exams || { items: [] })
const ty = computed(() => data.value?.typing || { modules: [], recent: [], trend: [] })
const web = computed(() => data.value?.web || { apis: [], recent: [], dimensions: [], peer_received: [] })

const examOpt = computed(() => {
  const xs = ex.value.items.filter(i => i.rate != null)
  return {
    color: [C[0], C[3]],
    tooltip: { trigger: 'axis' },
    legend: { data: ['得分率', '全体平均得分率'], bottom: 0, textStyle: { color: ink.text } },
    grid: { left: 44, right: 20, top: 16, bottom: 56 },
    xAxis: { type: 'category', data: xs.map(i => i.title), ...axis, axisLabel: { color: ink.muted, rotate: 20, width: 90, overflow: 'truncate' } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', color: ink.muted }, splitLine: { lineStyle: { color: ink.line } } },
    series: [
      { name: '得分率', type: 'line', data: xs.map(i => i.rate), label: { show: true, formatter: '{c}%', color: ink.text } },
      { name: '全体平均得分率', type: 'line', lineStyle: { type: 'dashed' }, data: xs.map(i => (i.avg != null && i.full ? Math.round(i.avg / i.full * 1000) / 10 : null)) }
    ]
  }
})
const typingOpt = computed(() => {
  const mods = [...new Set(ty.value.trend.map(t => t.module))].filter(m => m !== '键盘')
  return {
    color: C,
    tooltip: { trigger: 'axis' },
    legend: { data: mods, bottom: 0, textStyle: { color: ink.text } },
    grid: { left: 44, right: 20, top: 16, bottom: 40 },
    xAxis: { type: 'category', data: ty.value.trend.map(t => String(t.at).slice(5, 16).replace('T', ' ')), ...axis },
    yAxis: { type: 'value', name: '字/分', nameTextStyle: { color: ink.muted }, ...axis },
    series: mods.map(m => ({ name: m, type: 'line', connectNulls: true, data: ty.value.trend.map(t => (t.module === m ? t.speed : null)) }))
  }
})
const dimOpt = computed(() => {
  const ds = web.value.dimensions
  const vals = ds.flatMap(d => [d.self, d.peer]).filter(v => v != null)
  const max = vals.some(v => v > 10) ? 100 : Math.max(5, Math.ceil(Math.max(...vals, 0)))
  const series = []
  if (ds.some(d => d.self != null)) series.push({ name: '自评', value: ds.map(d => d.self ?? 0), itemStyle: { color: C[0] }, lineStyle: { color: C[0] }, areaStyle: { opacity: 0.12 } })
  if (ds.some(d => d.peer != null)) series.push({ name: '同伴评价', value: ds.map(d => d.peer ?? 0), itemStyle: { color: C[1] }, lineStyle: { color: C[1] }, areaStyle: { opacity: 0.12 } })
  return {
    tooltip: {},
    legend: { data: series.map(s => s.name), bottom: 0, textStyle: { color: ink.text } },
    radar: { center: ['50%', '46%'], radius: '60%', indicator: ds.map(d => ({ name: d.item, max })), axisName: { color: ink.text }, splitLine: { lineStyle: { color: ink.line } }, splitArea: { show: false } },
    series: [{ type: 'radar', data: series }]
  }
})
function fmt(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : ''
}
function score(r) {
  if (r.score == null) return ''
  return r.max_score != null ? `${r.score}/${r.max_score}` : r.score
}
function brief(p) {
  if (!p || typeof p !== 'object') return ''
  const skip = new Set(['student', 'activity', 'type', 'client_id', 'page', 'submitted_at', 'score', 'max_score', 'comment', 'answers', 'ratings', 'target'])
  return Object.entries(p).filter(([k]) => !skip.has(k)).slice(0, 4)
    .map(([k, v]) => `${k}：${typeof v === 'object' ? JSON.stringify(v) : v}`).join('；').slice(0, 120)
}
</script>

<template>
  <div class="page" v-loading="loading">
    <el-button link @click="router.back()">← 返回</el-button>
    <template v-if="data">
      <div class="head">
        <h2>{{ stu.name }} <small>{{ stu.student_no }} · {{ stu.student_class || '未分班' }}
          <template v-if="stu.class_role"> · {{ stu.class_role }}</template></small></h2>
        <el-tag v-if="!stu.is_active" type="info">已停用</el-tag>
      </div>

      <div class="kpis">
        <div class="kpi"><b>{{ ex.count }}</b><span>参加考试</span></div>
        <div class="kpi"><b>{{ ex.avg_rate != null ? ex.avg_rate + '%' : '—' }}</b><span>平均得分率</span></div>
        <div class="kpi"><b>{{ ex.class_rank ? `${ex.class_rank}/${ex.class_size}` : '—' }}</b><span>班内综合名次</span></div>
        <div class="kpi"><b>{{ ty.count }}</b><span>打字练习次数</span></div>
        <div class="kpi"><b>{{ ty.best_speed || '—' }}</b><span>最快打字（字/分）</span></div>
        <div class="kpi"><b>{{ ty.avg_accuracy != null ? ty.avg_accuracy + '%' : '—' }}</b><span>打字平均正确率</span></div>
        <div class="kpi"><b>{{ web.count }}</b><span>教学网页数据</span></div>
      </div>

      <el-tabs v-model="tab">
        <el-tab-pane :label="`考试（${ex.count}）`" name="exams">
          <el-empty v-if="!ex.items.length" description="还没有参加过你看得到的考试" />
          <template v-else>
            <EChart v-if="ex.items.length > 1" :option="examOpt" height="260px" label="每场考试的得分率" />
            <el-table :data="[...ex.items].reverse()" border size="small">
              <el-table-column prop="title" label="考试" min-width="160" show-overflow-tooltip />
              <el-table-column label="交卷时间" width="140"><template #default="{ row }">{{ fmt(row.submitted_at) }}</template></el-table-column>
              <el-table-column label="成绩" width="110" align="center">
                <template #default="{ row }">{{ row.score }} / {{ row.full }}
                  <el-tag v-if="row.pending" size="small" type="warning">待批</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="得分率" width="80" align="center"><template #default="{ row }">{{ row.rate != null ? row.rate + '%' : '' }}</template></el-table-column>
              <el-table-column label="全体名次" width="100" align="center"><template #default="{ row }">{{ row.rank }} / {{ row.takers }}</template></el-table-column>
              <el-table-column label="班内名次" width="100" align="center"><template #default="{ row }">{{ row.class_rank }} / {{ row.class_takers }}</template></el-table-column>
              <el-table-column label="全体平均" width="90" align="center" prop="avg" />
              <el-table-column label="班级平均" width="90" align="center" prop="class_avg" />
              <el-table-column label="客观题对" width="90" align="center"><template #default="{ row }">{{ row.right_count }}/{{ row.objective_count }}</template></el-table-column>
              <el-table-column label="作答次数" width="80" align="center" prop="attempts" />
              <el-table-column width="80">
                <template #default="{ row }"><el-button link type="primary" @click="router.push(`/js/analysis/${row.exam_id}`)">成绩分析</el-button></template>
              </el-table-column>
            </el-table>
            <p class="muted">名次按每场考试里各学生最新一次交卷的分数算，同分同名次。</p>
          </template>
        </el-tab-pane>

        <el-tab-pane :label="`打字（${ty.count}）`" name="typing">
          <el-empty v-if="!ty.count" description="还没有打字练习记录" />
          <template v-else>
            <div class="mods">
              <el-card v-for="m in ty.modules" :key="m.module" shadow="never" class="mod">
                <b>{{ m.module }}</b>
                <div>练习 {{ m.count }} 次 · {{ m.minutes }} 分钟</div>
                <div v-if="m.module !== '键盘'">最快 {{ m.best_speed }} · 平均 {{ m.avg_speed }} 字/分</div>
                <div>平均正确率 {{ m.avg_accuracy }}%</div>
              </el-card>
            </div>
            <EChart v-if="ty.trend.length > 1" :option="typingOpt" height="260px" label="打字速度走势" />
            <el-table :data="ty.recent" border size="small" max-height="400">
              <el-table-column label="时间" width="140"><template #default="{ row }">{{ fmt(row.at) }}</template></el-table-column>
              <el-table-column prop="module" label="模块" width="70" />
              <el-table-column prop="difficulty" label="难度" width="70" />
              <el-table-column prop="speed" label="速度" width="70" />
              <el-table-column label="正确率" width="80"><template #default="{ row }">{{ row.accuracy }}%</template></el-table-column>
              <el-table-column label="用时" width="80"><template #default="{ row }">{{ Math.round(row.duration / 60 * 10) / 10 }} 分</template></el-table-column>
              <el-table-column label="星级"><template #default="{ row }">{{ '★'.repeat(row.stars) }}</template></el-table-column>
            </el-table>
          </template>
        </el-tab-pane>

        <el-tab-pane :label="`教学网页数据（${web.count}）`" name="web">
          <p class="muted">第三方教学网页通过「API」送来的、学号对得上这个学生的数据。只显示你自己建的 API（管理员看全部）。</p>
          <el-empty v-if="!web.count && !web.peer_received.length" description="还没有这个学生的教学网页数据" />
          <template v-else>
            <div class="mods">
              <el-card v-for="a in web.apis" :key="a.api_id" shadow="hover" class="mod clickable" @click="router.push(`/js/api/${a.api_id}`)">
                <b>{{ a.name }}</b>
                <div>{{ a.count }} 条 · 最近 {{ fmt(a.last_at) }}</div>
                <div v-if="a.avg_rate != null">平均得分率 {{ a.avg_rate }}%</div>
                <div class="muted small" v-if="a.activities.length">{{ a.activities.slice(0, 4).join('、') }}</div>
                <div class="muted small" v-if="a.pages.length">{{ a.pages.length }} 个网页</div>
              </el-card>
            </div>
            <section v-if="web.dimensions.length >= 3" class="panel">
              <h4>自评与同伴评价</h4>
              <EChart :option="dimOpt" height="300px" label="各评价维度的自评和同伴评价" />
            </section>
            <el-table v-else-if="web.dimensions.length" :data="web.dimensions" size="small" border class="panel">
              <el-table-column prop="item" label="评价维度" />
              <el-table-column prop="self" label="自评" />
              <el-table-column prop="peer" label="同伴评价" />
            </el-table>
            <h4>他提交的数据</h4>
            <el-table :data="web.recent" border size="small" max-height="420" @row-click="r => (detail = r)" class="clickable">
              <el-table-column label="时间" width="140"><template #default="{ row }">{{ fmt(row.at) }}</template></el-table-column>
              <el-table-column prop="api_name" label="API" width="140" show-overflow-tooltip />
              <el-table-column prop="type_name" label="类型" width="70" />
              <el-table-column prop="activity" label="活动" width="140" show-overflow-tooltip />
              <el-table-column label="得分" width="80"><template #default="{ row }">{{ score(row) }}</template></el-table-column>
              <el-table-column label="内容" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">{{ row.comment || brief(row.payload) }}</template>
              </el-table-column>
              <el-table-column prop="page" label="来源网页" min-width="160" show-overflow-tooltip />
            </el-table>
            <template v-if="web.peer_received.length">
              <h4>同伴给他的评价（{{ web.peer_received.length }}）</h4>
              <el-table :data="web.peer_received" border size="small" max-height="320">
                <el-table-column label="时间" width="140"><template #default="{ row }">{{ fmt(row.at) }}</template></el-table-column>
                <el-table-column prop="student" label="评价人" width="100" />
                <el-table-column prop="activity" label="活动" width="140" show-overflow-tooltip />
                <el-table-column label="得分" width="80"><template #default="{ row }">{{ score(row) }}</template></el-table-column>
                <el-table-column prop="comment" label="评语" min-width="200" show-overflow-tooltip />
              </el-table>
            </template>
          </template>
        </el-tab-pane>
      </el-tabs>
    </template>

    <el-drawer :model-value="!!detail" title="数据详情" size="480px" @update:model-value="v => { if (!v) detail = null }">
      <pre v-if="detail" class="raw">{{ JSON.stringify(detail.payload, null, 2) }}</pre>
    </el-drawer>
  </div>
</template>

<style scoped>
.page { max-width: 1280px; margin: 0 auto; }
.head { display: flex; align-items: center; gap: 10px; }
.head h2 { margin: 6px 0; }
.head small { font-size: 14px; font-weight: normal; color: var(--el-text-color-secondary); margin-left: 8px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin: 10px 0 6px; }
.kpi { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 10px 14px; display: flex; flex-direction: column; }
.kpi b { font-size: 22px; }
.kpi span { font-size: 12px; color: var(--el-text-color-secondary); }
.mods { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; margin-bottom: 12px; }
.mod { font-size: 13px; line-height: 1.8; }
.mod b { font-size: 15px; }
.clickable { cursor: pointer; }
.clickable :deep(tr) { cursor: pointer; }
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
.small { font-size: 12px; }
.panel { margin-bottom: 12px; }
.raw { background: var(--el-fill-color-light); padding: 12px; border-radius: 6px; overflow: auto; font-size: 13px; }
</style>

<script setup>
/**
 * 打字成绩（教师端）。
 *
 * - 筛选：班级、模块、难度、姓名、日期；排序点表头（在服务端排，翻页也不乱）；
 * - 批量：勾选删除，或者「删除筛选出的全部」—— 删掉的正是表里看到的那些；
 * - 导出 Excel 也按当前筛选；
 * - 图表和结论在「学情分析」页（新标签页打开），这里只管看数和管数据。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download } from '../api'
import { loadPublicBase, studentLink } from '../publicUrl'

const router = useRouter()
const rows = ref([])
const total = ref(0)
const stats = ref(null)
const classes = ref([])
const loading = ref(false)
const picked = ref([])
const table = ref(null)

const query = reactive({
  student_class: '', module: '', difficulty: '', keyword: '', dates: [],
  sort: 'time', order: 'desc', page: 1, page_size: 50
})

/** 发给后端的筛选条件（不含分页排序）。导出、按条件删除都用它 */
function filters() {
  const f = {}
  for (const k of ['student_class', 'module', 'difficulty', 'keyword']) {
    if (query[k]) f[k] = query[k]
  }
  if (query.dates?.length === 2) {
    f.date_from = query.dates[0]
    f.date_to = query.dates[1]
  }
  return f
}
const filtered = computed(() => Object.keys(filters()).length > 0)

async function load() {
  loading.value = true
  try {
    const got = await api.typingSearch({
      ...filters(), sort: query.sort, order: query.order, page: query.page, page_size: query.page_size
    })
    rows.value = got.items
    total.value = got.total
  } finally {
    loading.value = false
  }
}
async function loadSide() {
  stats.value = await api.typingStats()
  classes.value = await api.typingClasses()
}
function search() {
  query.page = 1
  load()
}
function reset() {
  Object.assign(query, { student_class: '', module: '', difficulty: '', keyword: '', dates: [], page: 1 })
  load()
}
async function refresh() {
  await Promise.all([load(), loadSide()])
}

onMounted(async () => {
  await loadPublicBase()
  studentUrl.value = studentLink('/dazi')
  await refresh()
})

// 表头排序：交给服务端排，翻页才不会只排了这一页
const SORT_KEY = { speed: 'speed', accuracy: 'accuracy', duration: 'duration', stars: 'stars',
  created_at: 'time', student_name: 'name', student_class: 'class' }
function onSort({ prop, order }) {
  query.sort = order ? SORT_KEY[prop] || 'time' : 'time'
  query.order = order === 'ascending' ? 'asc' : 'desc'
  query.page = 1
  load()
}

// ---------------------------------------------------------------- 删除
async function afterDelete(n) {
  ElMessage.success(`已删除 ${n} 条`)
  table.value?.clearSelection()
  if (query.page > 1 && rows.value.length === picked.value.length) query.page -= 1
  await refresh()
}
async function removeOne(row) {
  await ElMessageBox.confirm(`删除「${row.student_name}」这条 ${row.module} 成绩？`, '提示', { type: 'warning' })
  await api.typingDelete(row.id)
  await afterDelete(1)
}
async function removePicked() {
  const n = picked.value.length
  await ElMessageBox.confirm(`删除勾选的 ${n} 条成绩？删除后无法恢复。`, '批量删除', {
    type: 'warning', confirmButtonText: `删除 ${n} 条`
  })
  const res = await api.typingDeleteMany(picked.value.map(r => r.id))
  await afterDelete(res.deleted)
}
async function removeFiltered() {
  const scope = filtered.value ? `筛选出的全部 ${total.value} 条` : `全部 ${total.value} 条`
  await ElMessageBox.confirm(`将删除${scope}打字成绩（不只是这一页），且无法恢复。确定吗？`, '删除确认', {
    type: 'warning', confirmButtonText: '确认删除'
  })
  const res = await api.typingClear(filters())
  await afterDelete(res.deleted)
}

async function exportXlsx() {
  await download(api.typingExport(filters()), '打字训练成绩.xlsx')
  ElMessage.success('已下载')
}

function openAnalysis() {
  const q = {}
  if (query.module) q.module = query.module
  if (query.student_class) q.classes = query.student_class
  window.open(router.resolve({ path: '/js/typing-analysis', query: q }).href, '_blank')
}

// 学生练习页地址。默认跟着浏览器当前地址走；后端配了 PUBLIC_BASE_URL 就以它为准
const studentUrl = ref(studentLink('/dazi'))
async function copyUrl() {
  try {
    await navigator.clipboard.writeText(studentUrl.value)
    ElMessage.success('已复制：' + studentUrl.value)
  } catch {
    // 非 https 时浏览器不给用剪贴板，退回手动复制
    ElMessageBox.alert(studentUrl.value, '手动复制这个链接', { confirmButtonText: '知道了' })
  }
}

const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
const when = t => String(t || '').replace('T', ' ').slice(0, 16)
</script>

<template>
  <el-card shadow="never" class="page-card">
    <template #header>
      <div class="head">
        <span>打字训练成绩</span>
        <div>
          <el-button size="small" type="primary" @click="openAnalysis">学情分析</el-button>
          <el-button size="small" @click="exportXlsx">导出 Excel</el-button>
          <el-button size="small" @click="refresh">刷新</el-button>
        </div>
      </div>
    </template>

    <el-alert type="info" :closable="false" class="hint">
      学生打开 <b>{{ studentUrl }}</b> 即可练习（班级姓名要和学生名单一致），完成后成绩自动进入这里。
      <el-button link type="primary" @click="copyUrl">复制链接</el-button>
    </el-alert>

    <div v-if="stats && stats.total" class="kpi">
      <div class="k"><span>练习人次</span><b>{{ stats.total }}</b></div>
      <div class="k"><span>参与人数</span><b>{{ stats.students }}</b></div>
      <div class="k"><span>平均正确率</span><b>{{ stats.avg_accuracy }}%</b></div>
      <div class="k"><span>平均用时</span><b>{{ fmt(stats.avg_duration) }}</b></div>
      <div v-for="(n, m) in stats.by_module" :key="m" class="k"><span>{{ m }}</span><b>{{ n }}</b><i>次</i></div>
    </div>

    <div class="bar">
      <el-select v-model="query.student_class" placeholder="全部班级" clearable filterable style="width: 150px" @change="search">
        <el-option v-for="c in classes" :key="c" :label="c" :value="c" />
      </el-select>
      <el-select v-model="query.module" placeholder="全部模块" clearable style="width: 120px" @change="search">
        <el-option v-for="m in ['中文', '英文', '键盘']" :key="m" :label="m" :value="m" />
      </el-select>
      <el-select v-model="query.difficulty" placeholder="全部难度" clearable style="width: 120px" @change="search">
        <el-option v-for="d in ['简单', '中等', '困难']" :key="d" :label="d" :value="d" />
      </el-select>
      <el-input v-model="query.keyword" placeholder="搜姓名" clearable style="width: 140px" @keyup.enter="search" @clear="search" />
      <el-date-picker
        v-model="query.dates"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 250px"
        @change="search"
      />
      <el-button type="primary" @click="search">查询</el-button>
      <el-button @click="reset">重置</el-button>
    </div>
  </el-card>

  <el-card shadow="never">
    <div class="tools">
      <span class="count">共 <b>{{ total }}</b> 条{{ filtered ? '（已筛选）' : '' }}</span>
      <span v-if="picked.length" class="count">已勾选 <b>{{ picked.length }}</b> 条</span>
      <div class="grow" />
      <el-button size="small" type="danger" plain :disabled="!picked.length" @click="removePicked">
        删除勾选{{ picked.length ? `（${picked.length}）` : '' }}
      </el-button>
      <el-button size="small" type="danger" plain :disabled="!total" @click="removeFiltered">
        {{ filtered ? `删除筛选出的全部（${total}）` : `清空全部（${total}）` }}
      </el-button>
    </div>

    <el-empty v-if="!rows.length && !loading" description="没有符合条件的成绩" :image-size="70" />
    <el-table v-mtable
      v-else
      ref="table"
      :data="rows"
      v-loading="loading"
      border
      size="small"
      row-key="id"
      :default-sort="{ prop: 'created_at', order: 'descending' }"
      @selection-change="v => (picked = v)"
      @sort-change="onSort"
    >
      <el-table-column type="selection" width="42" />
      <el-table-column prop="student_name" label="姓名" width="100" sortable="custom" />
      <el-table-column prop="student_class" label="班级" min-width="110" sortable="custom" show-overflow-tooltip />
      <el-table-column prop="module" label="模块" width="70" />
      <el-table-column prop="difficulty" label="难度" width="70" />
      <el-table-column prop="speed" label="速度" width="84" sortable="custom">
        <template #default="{ row }">{{ row.module === '键盘' ? '—' : row.speed }}</template>
      </el-table-column>
      <el-table-column prop="accuracy" label="正确率" width="90" sortable="custom">
        <template #default="{ row }">
          <b :class="row.accuracy >= 80 ? 'ok' : row.accuracy >= 60 ? '' : 'no'">{{ row.accuracy }}%</b>
        </template>
      </el-table-column>
      <el-table-column prop="duration" label="用时" width="80" sortable="custom">
        <template #default="{ row }">{{ fmt(row.duration) }}</template>
      </el-table-column>
      <el-table-column prop="stars" label="评价" width="84" sortable="custom">
        <template #default="{ row }"><span class="stars">{{ '★'.repeat(row.stars) || '—' }}</span></template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="140" sortable="custom">
        <template #default="{ row }">{{ when(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" @click="removeOne(row)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > query.page_size"
      v-model:current-page="query.page"
      v-model:page-size="query.page_size"
      class="pager"
      :total="total"
      :page-sizes="[20, 50, 100, 200]"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="load"
      @size-change="search"
    />
  </el-card>
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
  gap: 30px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.k span {
  display: block;
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
}
.k b {
  font-size: 22px;
  font-family: ui-monospace, Consolas, monospace;
}
.k i {
  font-style: normal;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-left: 3px;
}
.bar,
.tools {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.tools {
  margin-bottom: 10px;
}
.grow {
  flex: 1;
}
.count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.ok {
  color: var(--el-color-success);
}
.no {
  color: var(--el-color-danger);
}
.stars {
  color: #e6a23c;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download } from '../api'
import { loadPublicBase, studentLink } from '../publicUrl'

const rows = ref([])
const stats = ref(null)
const classes = ref([])
const loading = ref(false)

const query = reactive({ student_class: '', module: '', keyword: '', order: 'speed' })

async function load() {
  loading.value = true
  try {
    const params = { ...query }
    Object.keys(params).forEach(k => params[k] === '' && delete params[k])
    rows.value = await api.typingRecords(params)
    stats.value = await api.typingStats()
    classes.value = await api.typingClasses()
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  await loadPublicBase()
  studentUrl.value = studentLink('/dazi')
  await load()
})

/** 正确率分布：四档柱状图，高度按最大值归一 */
const buckets = computed(() => {
  const b = stats.value?.accuracy_buckets || {}
  const max = Math.max(1, ...Object.values(b))
  const colors = {
    '≥90': 'var(--el-color-success)',
    '80-89': 'var(--el-color-primary)',
    '70-79': 'var(--el-color-warning)',
    '<70': 'var(--el-color-danger)'
  }
  return Object.entries(b).map(([label, n]) => ({
    label,
    n,
    h: Math.max(3, Math.round((n / max) * 80)),
    color: colors[label]
  }))
})

async function exportXlsx() {
  await download(api.typingExport(), '打字训练成绩.xlsx')
  ElMessage.success('已下载')
}

async function removeOne(row) {
  await ElMessageBox.confirm(`删除「${row.student_name}」这条 ${row.module} 成绩？`, '提示', {
    type: 'warning'
  })
  await api.typingDelete(row.id)
  await load()
  ElMessage.success('已删除')
}

async function clearClass() {
  const scope = query.student_class || '全部班级'
  await ElMessageBox.confirm(
    `将清空 ${scope} 的打字成绩，且无法恢复。确定吗？`,
    '清空确认',
    { type: 'warning', confirmButtonText: '确认清空' }
  )
  const res = await api.typingClear(query.student_class || undefined)
  await load()
  ElMessage.success(`已删除 ${res.deleted} 条`)
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

const medal = i => (i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1)
const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
</script>

<template>
  <el-card shadow="never" class="page-card">
    <template #header>
      <div class="head">
        <span>打字训练学情</span>
        <div>
          <el-button size="small" @click="load">刷新</el-button>
          <el-button size="small" type="primary" @click="exportXlsx">导出 Excel</el-button>
          <el-button size="small" type="danger" plain @click="clearClass">清空</el-button>
        </div>
      </div>
    </template>

    <el-alert type="info" :closable="false" class="hint">
      学生打开 <b>{{ studentUrl }}</b> 即可练习，<b>不需要账号</b>，完成后成绩自动进入这里。
      <el-button link type="primary" @click="copyUrl">复制链接</el-button>
    </el-alert>

    <div v-if="stats && stats.total" class="kpi">
      <div class="k"><span>练习人次</span><b>{{ stats.total }}</b></div>
      <div class="k"><span>参与人数</span><b>{{ stats.students }}</b></div>
      <div class="k"><span>平均正确率</span><b>{{ stats.avg_accuracy }}%</b></div>
      <div class="k"><span>平均速度</span><b>{{ stats.avg_speed }}</b><i>字/分</i></div>
      <div class="k"><span>平均用时</span><b>{{ fmt(stats.avg_duration) }}</b></div>
    </div>

    <div class="bar">
      <el-select v-model="query.student_class" placeholder="全部班级" clearable style="width: 150px">
        <el-option v-for="c in classes" :key="c" :label="c" :value="c" />
      </el-select>
      <el-select v-model="query.module" placeholder="全部模块" clearable style="width: 130px">
        <el-option label="键盘" value="键盘" />
        <el-option label="英文" value="英文" />
        <el-option label="中文" value="中文" />
      </el-select>
      <el-input v-model="query.keyword" placeholder="搜姓名" clearable style="width: 150px" />
      <el-select v-model="query.order" style="width: 130px">
        <el-option label="按速度 ↓" value="speed" />
        <el-option label="按正确率 ↓" value="accuracy" />
        <el-option label="按时间 ↓" value="time" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
    </div>
  </el-card>

  <el-row :gutter="16">
    <el-col :span="15">
      <el-card shadow="never">
        <template #header>成绩排名</template>
        <el-empty v-if="!rows.length && !loading" description="还没有学生练习" :image-size="70" />
        <el-table v-else :data="rows" v-loading="loading" border size="small" max-height="560">
          <el-table-column label="名次" width="62">
            <template #default="{ $index }">{{ medal($index) }}</template>
          </el-table-column>
          <el-table-column prop="student_name" label="姓名" width="90" />
          <el-table-column prop="student_class" label="班级" width="110" show-overflow-tooltip />
          <el-table-column prop="module" label="模块" width="66" />
          <el-table-column prop="difficulty" label="难度" width="66" />
          <el-table-column label="速度" width="76">
            <template #default="{ row }">{{ row.speed || '—' }}</template>
          </el-table-column>
          <el-table-column label="正确率" width="80">
            <template #default="{ row }">
              <b :class="row.accuracy >= 80 ? 'ok' : row.accuracy >= 60 ? '' : 'no'">
                {{ row.accuracy }}%
              </b>
            </template>
          </el-table-column>
          <el-table-column label="评价" width="76">
            <template #default="{ row }">
              <span class="stars">{{ '★'.repeat(row.stars) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="时间" min-width="120">
            <template #default="{ row }">
              {{ String(row.created_at).replace('T', ' ').slice(5, 16) }}
            </template>
          </el-table-column>
          <el-table-column label="" width="56" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeOne(row)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-col>

    <el-col :span="9">
      <el-card shadow="never" class="page-card">
        <template #header>正确率分布</template>
        <el-empty v-if="!stats || !stats.total" description="暂无数据" :image-size="50" />
        <div v-else class="dist">
          <div v-for="b in buckets" :key="b.label" class="col">
            <div class="n">{{ b.n }}</div>
            <div class="pillar" :style="{ height: b.h + 'px', background: b.color }" />
            <div class="lb">{{ b.label }}</div>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="page-card">
        <template #header>各模块练习量</template>
        <el-empty v-if="!stats || !stats.total" description="暂无数据" :image-size="50" />
        <div v-else class="mods">
          <div v-for="(n, m) in stats.by_module" :key="m" class="mod">
            <span>{{ m }}</span><b>{{ n }}</b>
          </div>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>各班平均</template>
        <el-empty v-if="!stats || !stats.by_class.length" description="暂无数据" :image-size="50" />
        <el-table v-else :data="stats.by_class" border size="small">
          <el-table-column prop="student_class" label="班级" show-overflow-tooltip />
          <el-table-column prop="count" label="人次" width="62" />
          <el-table-column label="正确率" width="76">
            <template #default="{ row }">{{ row.avg_accuracy }}%</template>
          </el-table-column>
          <el-table-column prop="avg_speed" label="速度" width="62" />
        </el-table>
      </el-card>
    </el-col>
  </el-row>
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
.bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
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
.dist {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 130px;
  padding: 6px 4px;
}
.col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  justify-content: flex-end;
}
.n {
  font-size: 12px;
  font-weight: 600;
}
.pillar {
  width: 62%;
  border-radius: 5px 5px 0 0;
}
.lb {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.mods {
  display: flex;
  gap: 24px;
}
.mod span {
  display: block;
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
}
.mod b {
  font-size: 20px;
  font-family: ui-monospace, Consolas, monospace;
}
</style>

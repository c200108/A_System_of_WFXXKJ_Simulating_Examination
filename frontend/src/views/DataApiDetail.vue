<script setup>
/**
 * 某个 API 里面（2.16.0）：数据表单 / 来源网页 / 数据大图 / 接入说明 / 设置。
 *
 * 数据表单的固定列是学生、班级、类型、活动、得分、时间，其余列按收到的数据自动长出来
 * （后端 records 接口给 columns）。老师可以在设置里给这些字段起中文名、隐藏。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download, safeName } from '../api'
import { currentUser } from '../auth'
import DataApiBoard from '../components/DataApiBoard.vue'
import { loadPublicBase, studentLink } from '../publicUrl'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const info = ref(null)
const tab = ref(route.query.tab || 'records')
const isAdmin = computed(() => currentUser.value?.role === 'admin')
watch(tab, t => router.replace({ query: { ...route.query, tab: t } }))

function openBoard() {
  window.open(router.resolve(`/js/api-board/${id.value}`).href, '_blank')
}

// 接收地址按学生（第三方网页）能访问的地址拼，和学生考试链接同一套规则（见 publicUrl.js）：
// 后端在 nginx 后面看到的 Host 没有端口，拿它拼会少了 :3315
let baseReady = null
function withPublicBase(i) {
  i.endpoint = studentLink(`/api/hook/${i.key}`)
  i.sdk_url = studentLink('/api/hook/sdk.js')
  return i
}
async function loadInfo() {
  baseReady = baseReady || loadPublicBase()
  const [i] = await Promise.all([api.dataApi(id.value), baseReady])
  info.value = withPublicBase(i)
  fillSettings()
}

// ---------------------------------------------------------------- 数据表单
const rec = reactive({ total: 0, items: [], columns: [], options: {}, typeNames: {} })
const recLoading = ref(false)
const page = ref(1)
const size = ref(50)
const f = reactive({ type: '', activity: '', page_url: '', class_name: '', keyword: '', matched: '', flag: '', range: null })
const picked = ref([])
function filterParams() {
  const p = { ...f }
  delete p.range
  if (f.range && f.range.length === 2) {
    p.since = f.range[0]
    p.until = f.range[1]
  }
  Object.keys(p).forEach(k => (p[k] === '' || p[k] == null) && delete p[k])
  return p
}
async function loadRecords() {
  recLoading.value = true
  try {
    const res = await api.dataApiRecords(id.value, { ...filterParams(), page: page.value, size: size.value })
    rec.total = res.total
    rec.items = res.items
    rec.columns = res.columns
    rec.options = res.options
    rec.typeNames = res.type_names
  } finally {
    recLoading.value = false
  }
}
function search() {
  page.value = 1
  loadRecords()
}
function resetFilter() {
  Object.assign(f, { type: '', activity: '', page_url: '', class_name: '', keyword: '', matched: '', flag: '', range: null })
  search()
}
const visibleCols = computed(() => rec.columns.filter(c => !c.hidden))
const typeName = t => rec.typeNames[t] || t || '—'
function cell(v) {
  if (v == null) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  if (typeof v === 'boolean') return v ? '是' : '否'
  return String(v)
}
function fmt(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : ''
}
function scoreText(r) {
  if (r.score == null) return ''
  return r.max_score != null ? `${r.score} / ${r.max_score}` : String(r.score)
}

const detail = ref(null)
async function flag(flagTo) {
  const ids = picked.value.map(r => r.id)
  if (!ids.length) return
  await api.dataApiFlag(id.value, ids, flagTo)
  ElMessage.success(flagTo === 'invalid' ? `已把 ${ids.length} 条标成无效，不再计入统计` : `已恢复 ${ids.length} 条`)
  loadRecords()
}
async function removePicked() {
  const ids = picked.value.map(r => r.id)
  if (!ids.length) return
  await ElMessageBox.confirm(`删除选中的 ${ids.length} 条数据？删掉的在回收站放 7 天，可以还原。`, '删除数据', { type: 'warning' })
  await api.dataApiDeleteRecords(id.value, { ids })
  ElMessage.success('已删除')
  loadRecords()
  loadInfo()
}
async function removeAll() {
  await ElMessageBox.confirm(`清空这个 API 的全部 ${info.value.record_count} 条数据？会放进回收站 7 天，可以还原。`,
    '清空数据', { type: 'warning', confirmButtonText: '清空' })
  await api.dataApiDeleteRecords(id.value, { all: true })
  ElMessage.success('已清空')
  loadRecords()
  loadInfo()
}
async function exportAs(format) {
  await download(api.dataApiExport(id.value, { ...filterParams(), format }),
    `${safeName(info.value.name)}-数据.${format}`)
}

// ---------------------------------------------------------------- 来源网页
const sources = ref([])
async function loadSources() {
  sources.value = (await api.dataApiSources(id.value)).items
}
function openSource(p) {
  f.page_url = p || '-'
  tab.value = 'records'
  search()
}

// ---------------------------------------------------------------- 接入说明
const sampleBody = computed(() => {
  const t = info.value?.template
  const base = {
    student: { no: '20250101', name: '张三', class: '七年级1班' },
    activity: { id: 'L3-T1', name: '第3课 任务1' }
  }
  if (t === 'self_eval') {
    return { type: 'self_eval', ...base, ratings: [{ item: '参与度', score: 4, max: 5 }, { item: '合作交流', score: 5, max: 5 }], comment: '这节课我学会了……' }
  }
  if (t === 'peer_eval') {
    return { type: 'peer_eval', ...base, target: { no: '20250102', name: '李四' }, ratings: [{ item: '合作交流', score: 4, max: 5 }], comment: '分工很清楚' }
  }
  if (t === 'survey') {
    return { type: 'survey', ...base, answers: [{ q: '你喜欢这节课吗', answer: '喜欢' }, { q: '最难的部分', answer: '循环' }] }
  }
  return {
    type: 'answer', ...base, score: 8, max_score: 10,
    answers: [{ q: '1', answer: 'B', correct: true, score: 5, max: 5 }, { q: '2', answer: 'A', correct: false, score: 3, max: 5 }]
  }
})
const codes = computed(() => {
  if (!info.value) return []
  const ep = info.value.endpoint
  const tok = info.value.write_token
  const body = JSON.stringify(sampleBody.value, null, 2)
  return [
    {
      key: 'sdk', label: '网页（推荐）', lang: 'html',
      text: `<script src="${info.value.sdk_url}"><\/script>
<script>
  const api = WFXX.api('${info.value.key}', '${tok}');
  // 学生点「提交」时：
  api.send(${body.replace(/\n/g, '\n  ')}).then(r => {
    if (r.ok) alert('提交成功');
  });
<\/script>`
    },
    {
      key: 'fetch', label: '网页 fetch', lang: 'js',
      text: `fetch('${ep}', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-Api-Key': '${tok}' },
  body: JSON.stringify(${body.replace(/\n/g, '\n  ')})
}).then(r => r.json()).then(console.log);`
    },
    {
      key: 'form', label: 'HTML 表单', lang: 'html',
      text: `<!-- 不用写 JS：表单直接提交，交完跳回你的页面 -->
<form action="${ep}" method="post">
  <input type="hidden" name="_token" value="${tok}">
  <input type="hidden" name="_redirect" value="https://你的网页/谢谢.html">
  学号 <input name="学号"> 姓名 <input name="姓名"> 班级 <input name="班级">
  你的答案 <input name="答案">
  <button>提交</button>
</form>`
    },
    {
      key: 'python', label: 'Python', lang: 'python',
      text: `import requests
r = requests.post('${ep}',
                  headers={'Authorization': 'Bearer ${tok}'},
                  json=${body.replace(/\n/g, '\n                  ').replace(/true/g, 'True').replace(/false/g, 'False')})
print(r.json())`
    },
    {
      key: 'curl', label: 'curl', lang: 'bash',
      text: `curl -X POST '${ep}' -H 'X-Api-Key: ${tok}' -H 'Content-Type: application/json' \\
  -d '${JSON.stringify(sampleBody.value)}'`
    }
  ]
})
const codeTab = ref('sdk')
async function copy(text, what = '已复制') {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const t = document.createElement('textarea')
    t.value = text
    document.body.appendChild(t)
    t.select()
    document.execCommand('copy')
    t.remove()
  }
  ElMessage.success(what)
}
async function rotate(which, enable = true) {
  if (which === 'write') {
    await ElMessageBox.confirm('重新生成后旧密钥立刻失效，已经写进网页里的要换成新的。确定？', '重新生成写入密钥', { type: 'warning' })
  }
  info.value = withPublicBase(await api.dataApiRotate(id.value, which, enable))
  ElMessage.success('已更新')
}
async function sendTest() {
  await api.dataApiTest(id.value)
  ElMessage.success('已发一条测试数据，去「数据表单」看看')
  loadInfo()
  loadRecords()
}

// ---------------------------------------------------------------- 设置
const s = reactive({})
const classes = ref([])
const teachers = ref([])
function fillSettings() {
  const i = info.value
  Object.assign(s, {
    name: i.name, description: i.description, template: i.template, status: i.status,
    window: i.accept_from || i.accept_until ? [i.accept_from, i.accept_until] : null,
    allowed_origins: i.allowed_origins, dedupe: i.dedupe, allow_get: i.allow_get,
    public_summary: i.public_summary, class_ids: [...i.class_ids],
    field_meta: JSON.parse(JSON.stringify(i.field_meta || {}))
  })
}
const fieldRows = computed(() => {
  const keys = new Set([...rec.columns.map(c => c.key), ...Object.keys(s.field_meta || {})])
  return [...keys].map(k => {
    if (!s.field_meta[k]) s.field_meta[k] = { label: '', kind: '', hidden: false }
    return { key: k, meta: s.field_meta[k] }
  })
})
const saving = ref(false)
async function saveSettings() {
  saving.value = true
  try {
    const body = {
      name: s.name, description: s.description, template: s.template, status: s.status,
      allowed_origins: s.allowed_origins, dedupe: s.dedupe, allow_get: s.allow_get,
      public_summary: s.public_summary, class_ids: s.class_ids, field_meta: s.field_meta
    }
    if (s.window && s.window.length === 2) {
      body.accept_from = s.window[0]
      body.accept_until = s.window[1]
    } else {
      body.clear_window = true
    }
    info.value = withPublicBase(await api.dataApiUpdate(id.value, body))
    fillSettings()
    ElMessage.success('已保存')
    loadRecords()
  } finally {
    saving.value = false
  }
}
async function togglePause() {
  info.value = withPublicBase(await api.dataApiUpdate(id.value, { status: info.value.status === 'active' ? 'paused' : 'active' }))
  fillSettings()
}
async function removeApi() {
  await ElMessageBox.confirm(`删除 API「${info.value.name}」和它的 ${info.value.record_count} 条数据？会放进回收站 7 天，可以还原。`,
    '删除 API', { type: 'warning', confirmButtonText: '删除' })
  await api.dataApiDelete(id.value)
  ElMessage.success('已删除')
  router.push('/js/api')
}
const transferTo = ref(null)
async function transfer() {
  if (!transferTo.value) return
  info.value = withPublicBase(await api.dataApiTransfer(id.value, transferTo.value))
  ElMessage.success(`已转给 ${info.value.owner_name}`)
}

onMounted(async () => {
  await loadInfo()
  loadRecords()
  loadSources()
  try {
    classes.value = await api.classes()
  } catch { /* 没权限就不显示 */ }
  if (isAdmin.value) {
    try {
      teachers.value = (await api.dataApis()).teachers || []
    } catch { /* 忽略 */ }
  }
})
watch(tab, t => {
  if (t === 'sources') loadSources()
})
</script>

<template>
  <div v-if="info" class="page">
    <div class="head">
      <div class="title">
        <el-button link @click="router.push('/js/api')">← API</el-button>
        <h2>{{ info.name }}</h2>
        <el-tag :type="info.status === 'active' ? 'success' : 'info'">{{ info.status === 'active' ? '接收中' : '已暂停' }}</el-tag>
        <el-tag effect="plain">{{ info.template_name }}</el-tag>
        <span v-if="isAdmin" class="muted">所属：{{ info.owner_name }}</span>
      </div>
      <div class="tools">
        <el-button @click="togglePause">{{ info.status === 'active' ? '暂停接收' : '恢复接收' }}</el-button>
        <el-button type="primary" plain @click="openBoard">投屏大图</el-button>
      </div>
    </div>
    <p v-if="info.description" class="desc">{{ info.description }}</p>

    <el-tabs v-model="tab">
      <!-- ============================== 数据表单 -->
      <el-tab-pane :label="`数据表单（${info.record_count}）`" name="records">
        <div class="filters">
          <el-select v-model="f.type" clearable placeholder="类型" style="width: 110px" @change="search">
            <el-option v-for="t in rec.options.types" :key="t" :label="typeName(t)" :value="t" />
          </el-select>
          <el-select v-model="f.activity" clearable filterable placeholder="活动" style="width: 150px" @change="search">
            <el-option v-for="t in rec.options.activities" :key="t" :label="t" :value="t" />
          </el-select>
          <el-select v-model="f.page_url" clearable filterable placeholder="来源网页" style="width: 200px" @change="search">
            <el-option label="（未注明来源）" value="-" />
            <el-option v-for="t in rec.options.pages" :key="t" :label="t" :value="t" />
          </el-select>
          <el-select v-model="f.class_name" clearable filterable placeholder="班级" style="width: 120px" @change="search">
            <el-option v-for="t in rec.options.classes" :key="t" :label="t" :value="t" />
          </el-select>
          <el-select v-model="f.matched" clearable placeholder="名单" style="width: 110px" @change="search">
            <el-option label="对上名单" value="yes" />
            <el-option label="不在名单" value="no" />
          </el-select>
          <el-select v-model="f.flag" clearable placeholder="状态" style="width: 100px" @change="search">
            <el-option label="有效" value="normal" />
            <el-option label="无效" value="invalid" />
          </el-select>
          <el-date-picker v-model="f.range" type="datetimerange" start-placeholder="开始" end-placeholder="结束"
                          value-format="YYYY-MM-DDTHH:mm:ss" style="width: 320px" @change="search" />
          <el-input v-model="f.keyword" clearable placeholder="姓名、学号、内容" style="width: 160px" @keyup.enter="search" @clear="search" />
          <el-button @click="search">查询</el-button>
          <el-button link @click="resetFilter">重置</el-button>
        </div>
        <div class="bar">
          <span class="muted">共 {{ rec.total }} 条<template v-if="picked.length">，选了 {{ picked.length }} 条</template></span>
          <div class="tools">
            <el-button size="small" :disabled="!picked.length" @click="flag('invalid')">标为无效</el-button>
            <el-button size="small" :disabled="!picked.length" @click="flag('normal')">恢复有效</el-button>
            <el-button size="small" type="danger" plain :disabled="!picked.length" @click="removePicked">删除</el-button>
            <el-dropdown @command="exportAs">
              <el-button size="small">导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="xlsx">Excel（按当前筛选）</el-dropdown-item>
                  <el-dropdown-item command="csv">CSV（按当前筛选）</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" link type="danger" :disabled="!info.record_count" @click="removeAll">清空全部</el-button>
          </div>
        </div>
        <el-table :data="rec.items" v-loading="recLoading" border size="small" max-height="620"
                  @selection-change="picked = $event" @row-dblclick="detail = $event"
                  :row-class-name="({ row }) => row.flag === 'invalid' ? 'row-invalid' : row.superseded ? 'row-old' : ''">
          <el-table-column type="selection" width="40" fixed />
          <el-table-column label="收到时间" width="150" fixed>
            <template #default="{ row }">{{ fmt(row.received_at) }}</template>
          </el-table-column>
          <el-table-column label="学生" width="130" fixed>
            <template #default="{ row }">
              <span>{{ row.student.name || row.student.no || '匿名' }}</span>
              <el-tag v-if="row.student_matched" size="small" type="success" class="mini" title="对上了平台名单，已汇总进学情">名单</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="学号" width="110" prop="student.no" />
          <el-table-column label="班级" width="110" prop="student.class" />
          <el-table-column label="类型" width="70">
            <template #default="{ row }">{{ typeName(row.type) }}</template>
          </el-table-column>
          <el-table-column label="活动" width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.activity.name || row.activity.id }}</template>
          </el-table-column>
          <el-table-column label="被评人" width="90">
            <template #default="{ row }">{{ row.target ? (row.target.name || row.target.no) : '' }}</template>
          </el-table-column>
          <el-table-column label="得分" width="80" align="center">
            <template #default="{ row }">{{ scoreText(row) }}</template>
          </el-table-column>
          <el-table-column label="评语" min-width="160" show-overflow-tooltip prop="comment" />
          <el-table-column v-for="c in visibleCols" :key="c.key" :label="c.label" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ cell(row.fields[c.key]) }}</template>
          </el-table-column>
          <el-table-column label="来源网页" min-width="160" show-overflow-tooltip prop="page" />
          <el-table-column label="" width="60" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="detail = row">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination class="pager" background layout="total, sizes, prev, pager, next" :total="rec.total"
                       v-model:current-page="page" v-model:page-size="size" :page-sizes="[20, 50, 100, 200]"
                       @current-change="loadRecords" @size-change="search" />
        <p class="muted small">灰色划线的是标成无效的，浅色的是被同一学生后来的提交替代的（设置里选了「只算最新一条」），都不计入统计。</p>
      </el-tab-pane>

      <!-- ============================== 来源网页 -->
      <el-tab-pane label="来源网页" name="sources">
        <p class="muted">同一个 API 可以给好几个网页用。这里按网页分开看各收了多少，点一行看那个网页的数据。</p>
        <el-table :data="sources" border size="small" @row-click="r => openSource(r.page)" class="clickable">
          <el-table-column label="网页" min-width="280" show-overflow-tooltip>
            <template #default="{ row }">{{ row.page || '（未注明来源网页）' }}</template>
          </el-table-column>
          <el-table-column label="条数" prop="records" width="80" align="center" />
          <el-table-column label="人数" prop="people" width="80" align="center" />
          <el-table-column label="对上名单" prop="matched" width="90" align="center" />
          <el-table-column label="平均分" width="90" align="center">
            <template #default="{ row }">{{ row.avg_score ?? '' }}</template>
          </el-table-column>
          <el-table-column label="最早" width="150"><template #default="{ row }">{{ fmt(row.first_at) }}</template></el-table-column>
          <el-table-column label="最近" width="150"><template #default="{ row }">{{ fmt(row.last_at) }}</template></el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ============================== 数据大图 -->
      <el-tab-pane label="数据大图" name="board" lazy>
        <DataApiBoard :api-id="id" />
      </el-tab-pane>

      <!-- ============================== 接入说明 -->
      <el-tab-pane label="接入说明" name="connect">
        <el-descriptions :column="1" border class="keys">
          <el-descriptions-item label="接收地址">
            <code>{{ info.endpoint }}</code>
            <el-button link type="primary" @click="copy(info.endpoint, '已复制接收地址')">复制</el-button>
          </el-descriptions-item>
          <el-descriptions-item label="写入密钥">
            <code>{{ info.write_token }}</code>
            <el-button link type="primary" @click="copy(info.write_token, '已复制写入密钥')">复制</el-button>
            <el-button link type="danger" @click="rotate('write')">重新生成</el-button>
            <div class="muted small">写在学生网页里，只能往这个 API 里写数据，看不到任何数据。泄露了就重新生成。</div>
          </el-descriptions-item>
          <el-descriptions-item label="读取密钥">
            <template v-if="info.read_token">
              <code>{{ info.read_token }}</code>
              <el-button link type="primary" @click="copy(info.read_token, '已复制读取密钥')">复制</el-button>
              <el-button link type="danger" @click="rotate('read', false)">关闭读取</el-button>
            </template>
            <el-button v-else link type="primary" @click="rotate('read')">开启读取接口</el-button>
            <div class="muted small">给你自己的服务器端程序取回数据用（GET {{ info.endpoint }}/records），不要写进网页。</div>
          </el-descriptions-item>
        </el-descriptions>

        <div class="bar">
          <h3>示例代码</h3>
          <el-button @click="sendTest">发一条测试数据</el-button>
        </div>
        <el-tabs v-model="codeTab" type="card">
          <el-tab-pane v-for="c in codes" :key="c.key" :label="c.label" :name="c.key">
            <div class="code">
              <el-button size="small" class="copy" @click="copy(c.text)">复制</el-button>
              <pre>{{ c.text }}</pre>
            </div>
          </el-tab-pane>
        </el-tabs>

        <h3>数据怎么写</h3>
        <ul class="spec">
          <li>推荐按上面的格式送：<code>student</code> 学生（学号 no、姓名 name、班级 class），<code>type</code> 类型
            （answer 答题 / self_eval 自评 / peer_eval 互评 / survey 问卷 / 自定义），<code>activity</code> 哪节课哪个任务，
            <code>score</code>/<code>max_score</code> 得分满分，<code>answers</code> 逐题作答，<code>ratings</code> 评价维度，
            <code>target</code> 互评对象，<code>comment</code> 评语，<code>data</code> 其他任意内容。<b>每一项都可以不填。</b></li>
          <li>不按这个格式也能收：任意 JSON、HTML 表单都原样存下，学号叫 <code>学号</code>、<code>xh</code>、<code>student_no</code> 都认。</li>
          <li>一次可以送一个数组批量提交（最多 500 条）；带上 <code>client_id</code> 的，重发不会重复入库。</li>
          <li>学号对上平台名单的，数据会汇总进学生的「学情」；对不上的只在这里显示。</li>
          <li>回执：成功 <code>{"ok": true, "id": 123}</code>；失败 <code>{"ok": false, "code": "…", "message": "…"}</code>。
            完整说明见项目文档「API 数据接入规范」。</li>
        </ul>
      </el-tab-pane>

      <!-- ============================== 设置 -->
      <el-tab-pane label="设置" name="settings">
        <el-form label-width="130px" class="settings" @submit.prevent>
          <el-form-item label="名称"><el-input v-model="s.name" maxlength="64" show-word-limit /></el-form-item>
          <el-form-item label="描述"><el-input v-model="s.description" type="textarea" :rows="3" maxlength="2000" /></el-form-item>
          <el-form-item label="用途">
            <el-select v-model="s.template" style="width: 160px">
              <el-option v-for="(l, k) in info.templates" :key="k" :label="l" :value="k" />
            </el-select>
          </el-form-item>
          <el-form-item label="接收">
            <el-radio-group v-model="s.status">
              <el-radio value="active">接收中</el-radio>
              <el-radio value="paused">暂停</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="接收时间段">
            <el-date-picker v-model="s.window" type="datetimerange" start-placeholder="开始" end-placeholder="截止"
                            value-format="YYYY-MM-DDTHH:mm:ss" clearable />
            <div class="muted small">留空就是一直收。只在课上收的话填上课时间。</div>
          </el-form-item>
          <el-form-item label="重复提交">
            <el-radio-group v-model="s.dedupe">
              <el-radio value="all">全部保留、都计入统计</el-radio>
              <el-radio value="latest">同一学生同一活动只算最新一条</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="关联班级">
            <el-select v-model="s.class_ids" multiple filterable placeholder="用来算应交人数、完成率、谁还没交" style="width: 420px">
              <el-option v-for="c in classes" :key="c.id" :label="c.display" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="允许的来源网站">
            <el-input v-model="s.allowed_origins" type="textarea" :rows="3"
                      placeholder="一行一个，如 https://teach.example.com 。留空表示不限" style="width: 420px" />
            <div class="muted small">只限制从浏览器里提交；服务器端程序不受影响，靠密钥。</div>
          </el-form-item>
          <el-form-item label="其他">
            <el-checkbox v-model="s.allow_get">允许 GET 提交（给只能拼链接的工具用）</el-checkbox>
            <el-checkbox v-model="s.public_summary">学生网页可以用写入密钥读全班汇总（不含个人信息）</el-checkbox>
          </el-form-item>
          <el-form-item v-if="fieldRows.length" label="字段名称">
            <el-table :data="fieldRows" size="small" border style="width: 620px">
              <el-table-column label="收到的字段" prop="key" min-width="160" show-overflow-tooltip />
              <el-table-column label="显示成" width="160">
                <template #default="{ row }"><el-input v-model="row.meta.label" size="small" maxlength="40" placeholder="中文名" /></template>
              </el-table-column>
              <el-table-column label="类型" width="110">
                <template #default="{ row }">
                  <el-select v-model="row.meta.kind" size="small" placeholder="自动">
                    <el-option label="自动" value="" /><el-option label="数值" value="number" />
                    <el-option label="文本" value="text" /><el-option label="选项" value="choice" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="隐藏" width="70" align="center">
                <template #default="{ row }"><el-checkbox v-model="row.meta.hidden" /></template>
              </el-table-column>
            </el-table>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="saveSettings">保存</el-button>
          </el-form-item>
          <el-divider />
          <el-form-item v-if="isAdmin" label="转给其他老师">
            <el-select v-model="transferTo" placeholder="选老师" style="width: 160px">
              <el-option v-for="t in teachers" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <el-button :disabled="!transferTo" @click="transfer">转过去</el-button>
          </el-form-item>
          <el-form-item label="删除">
            <el-button type="danger" plain @click="removeApi">删除这个 API</el-button>
            <span class="muted small" style="margin-left: 8px">连同数据进回收站，7 天内能还原。最多存 {{ info.max_records }} 条。</span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <el-drawer :model-value="!!detail" :title="detail ? `数据 #${detail.id}` : ''" size="520px"
               @update:model-value="v => { if (!v) detail = null }">
      <template v-if="detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="学生">{{ detail.student.name }} {{ detail.student.no }} {{ detail.student.class }}
            <el-button v-if="detail.student_id" link type="primary" @click="router.push(`/js/students/${detail.student_id}/insight`)">看学情</el-button>
          </el-descriptions-item>
          <el-descriptions-item label="类型">{{ typeName(detail.type) }}</el-descriptions-item>
          <el-descriptions-item label="活动">{{ detail.activity.name || detail.activity.id }}</el-descriptions-item>
          <el-descriptions-item label="得分">{{ scoreText(detail) }}</el-descriptions-item>
          <el-descriptions-item label="来源网页">{{ detail.page }}</el-descriptions-item>
          <el-descriptions-item label="收到时间">{{ fmt(detail.received_at) }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ fmt(detail.submitted_at) }}</el-descriptions-item>
          <el-descriptions-item label="来源 IP">{{ detail.source_ip }} {{ detail.origin }}</el-descriptions-item>
        </el-descriptions>
        <h4>原始数据</h4>
        <pre class="raw">{{ JSON.stringify(detail.payload, null, 2) }}</pre>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.title h2 { margin: 0; }
.desc { color: var(--el-text-color-secondary); margin: 6px 0 0; white-space: pre-wrap; }
.tools { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.bar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; gap: 8px; flex-wrap: wrap; }
.bar h3 { margin: 0; }
.muted { color: var(--el-text-color-secondary); }
.small { font-size: 12px; line-height: 1.6; }
.mini { margin-left: 4px; transform: scale(0.85); }
.pager { margin-top: 10px; justify-content: flex-end; }
:deep(.row-invalid) { color: var(--el-text-color-placeholder); text-decoration: line-through; }
:deep(.row-old) { color: var(--el-text-color-secondary); background: var(--el-fill-color-lighter); }
.clickable :deep(tr) { cursor: pointer; }
.keys code, .spec code { background: var(--el-fill-color); padding: 1px 6px; border-radius: 4px; font-size: 13px; word-break: break-all; }
.keys { margin-bottom: 16px; }
.code { position: relative; }
.code pre, .raw { background: var(--el-fill-color-light); padding: 12px; border-radius: 6px; overflow: auto; font-size: 13px; line-height: 1.5; max-height: 460px; }
.copy { position: absolute; right: 8px; top: 8px; }
.spec { line-height: 1.9; font-size: 14px; }
.settings { max-width: 900px; }
.settings .el-checkbox { display: flex; }
</style>

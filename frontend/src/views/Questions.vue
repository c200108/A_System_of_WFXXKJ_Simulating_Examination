<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download } from '../api'
import { ArrowDown } from '@element-plus/icons-vue'
import ClampText from '../components/ClampText.vue'

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const scopes = ref([])
const types = ref([])
// 可挂的仿真任务（只有操作题用得上）
const sims = ref([])
const SIM_KINDS = { win: 'Windows 操作', wps: 'WPS 文字', html: '网页编程' }
const sources = ref([])
const stats = ref(null)
const onlyPinned = ref(false)

const query = reactive({
  keyword: '',
  type: '',
  scope: '',
  source: '',
  difficulty: '',
  // 题目有无答案：'' 全部、true 有答案、false 没答案（没答案的题组卷时默认会被跳过）
  has_answer: '',
  // 在用 / 已停用（2.27.0）；'' 全部
  status: '',
  page: 1,
  page_size: 20
})

// 难度只用数字 1~5，后面那句话只是给老师看的说明，存的还是数字
const LEVELS = [
  { value: 1, text: '1　很容易' },
  { value: 2, text: '2　容易' },
  { value: 3, text: '3　中等' },
  { value: 4, text: '4　较难' },
  { value: 5, text: '5　很难' }
]

const dialog = reactive({ visible: false, editing: null })
const blank = () => ({
  type: '选择题',
  stem: '',
  answer: '',
  scope: '',
  source: '自定义',
  image_url: '',
  // null = 不填，由后端按题型和题干估一个，省得为加一道题先纠结难度
  difficulty: null,
  is_pinned: false,
  // 操作题可以挂一个仿真任务：挂上之后学生在网页里真做一遍，交卷自动判分
  sim_task_id: null,
  // 第五个选项 E 留空就不用（测评题里有五个选项的多选题）
  options: [
    { label: 'A', content: '' },
    { label: 'B', content: '' },
    { label: 'C', content: '' },
    { label: 'D', content: '' },
    { label: 'E', content: '' }
  ]
})
const form = reactive(blank())

/** 选择题的答案勾几个就是几选：勾一个是单选，勾两个以上是多选（答案存成 ABD） */
const answerLetters = computed({
  get: () => String(form.answer || '').toUpperCase().replace(/[^A-Z]/g, '').split('').filter(Boolean),
  set: v => (form.answer = [...new Set(v)].sort().join(''))
})

// ---------- 勾选、批量操作（2.27.0） ----------
const picked = ref([])
const table = ref(null)
const bulkScope = ref('')
const bulkLevel = ref(null)
const BULK_TEXT = {
  disable: '停用',
  enable: '启用',
  delete: '删除',
  pin: '设为必出',
  unpin: '取消必出',
  scope: '改知识范围',
  difficulty: '改难度'
}
async function bulk(action, value = null) {
  const ids = picked.value.map(r => r.id)
  if (!ids.length) return ElMessage.warning('先在表格左边勾选题目')
  if (action === 'scope' && !value) return ElMessage.warning('先选要改成的知识范围')
  if (action === 'difficulty' && !value) return ElMessage.warning('先选要改成的难度')
  const tip = {
    delete: `删除选中的 ${ids.length} 道题？删掉的在回收站里，7 天内可以还原。`,
    disable: `停用选中的 ${ids.length} 道题？停用的题还在题库里，组卷时不会被抽到，随时能再启用。`
  }[action]
  if (tip) {
    await ElMessageBox.confirm(tip, BULK_TEXT[action], {
      type: 'warning',
      confirmButtonText: `${BULK_TEXT[action]} ${ids.length} 道`,
      confirmButtonClass: action === 'delete' ? 'el-button--danger' : ''
    })
  }
  const res = await api.bulkQuestions(ids, action, value)
  ElMessage.success(`已${BULK_TEXT[action]} ${res.done} 道` + (res.skipped ? `，${res.skipped} 道已经不在了` : ''))
  picked.value = []
  table.value?.clearSelection()
  load()
}

function activeFilters() {
  const params = { ...query }
  delete params.page
  delete params.page_size
  // 下拉框点了清空是 undefined / null，也当没选
  Object.keys(params).forEach(k => (params[k] === '' || params[k] == null) && delete params[k])
  if (onlyPinned.value) params.pinned = true
  return params
}

/** 停用的题整行变灰 */
const rowClass = ({ row }) => (row.is_disabled ? 'row-disabled' : '')
/** 选择题答案不止一个字母就是多选题 */
const isMulti = row => row.type === '选择题' && String(row.answer || '').replace(/[^A-Za-z]/g, '').length > 1

/** 选项拼成一行，给 ClampText 当「内容变了没」的依据（显示走插槽） */
function optionsLine(row) {
  return (row.options || []).map(o => `${o.label}.${o.content}`).join(' ')
}

async function load() {
  loading.value = true
  try {
    const res = await api.questions({ ...activeFilters(), page: query.page, page_size: query.page_size })
    rows.value = res.items
    total.value = res.total
    stats.value = await api.stats()
    sources.value = stats.value.sources
  } finally {
    loading.value = false
  }
}

async function exportBank(command) {
  const preset = {
    all: [{}, '信息技术题库_全部'],
    custom: [{ source: '自定义' }, '信息技术题库_我补充的题'],
    filtered: [activeFilters(), '信息技术题库_筛选结果']
  }[command]
  const [params, name] = preset
  await download(api.exportBank({ ...params, filename: name }), name + '.xlsx')
  ElMessage.success('已下载 ' + name + '.xlsx')
}

onMounted(async () => {
  const dicts = await api.dicts()
  scopes.value = dicts.filter(d => d.category === 'scope').map(d => d.name)
  types.value = dicts.filter(d => d.category === 'qtype').map(d => d.name)
  // 拿不到不影响出题，只是操作题那个下拉会是空的
  sims.value = await api.sims().catch(() => [])
  await load()
})

function search() {
  query.page = 1
  load()
}

function openCreate() {
  dialog.editing = null
  Object.assign(form, blank())
  dialog.visible = true
}

function openEdit(row) {
  dialog.editing = row.id
  Object.assign(form, {
    type: row.type,
    stem: row.stem,
    answer: row.answer,
    scope: row.scope,
    source: row.source,
    image_url: row.image_url || '',
    difficulty: row.difficulty || null,
    is_pinned: row.is_pinned,
    sim_task_id: row.sim_task_id || null,
    // 老题只有 A~D 四项：补上空的 E，编辑框里照样能加第五项
    options: row.options.length
      ? [...row.options.map(o => ({ ...o })), ...blank().options.slice(row.options.length)]
      : blank().options
  })
  dialog.visible = true
}

async function save() {
  if (!form.stem.trim()) return ElMessage.warning('题干不能为空')
  if (!form.scope) return ElMessage.warning('请选择知识范围')
  if (form.type === '选择题') {
    const have = new Set(form.options.filter(o => o.content.trim()).map(o => o.label))
    const bad = answerLetters.value.filter(l => !have.has(l))
    if (bad.length) return ElMessage.warning(`答案里的 ${bad.join('、')} 这一项是空的`)
  }

  const payload = {
    ...form,
    image_url: form.image_url || null,
    options:
      form.type === '选择题'
        ? form.options.filter(o => o.content.trim())
        : form.type === '判断题'
          ? [
              { label: 'A', content: '正确' },
              { label: 'B', content: '错误' }
            ]
          : []
  }
  if (dialog.editing) await api.updateQuestion(dialog.editing, payload)
  else await api.createQuestion(payload)
  ElMessage.success('已保存')
  dialog.visible = false
  load()
}

async function remove(row) {
  await ElMessageBox.confirm('删除后可以在数据库里恢复，确定删除？', '提示', { type: 'warning' })
  await api.deleteQuestion(row.id)
  ElMessage.success('已删除')
  load()
}

async function togglePin(row) {
  await api.updateQuestion(row.id, { is_pinned: !row.is_pinned })
  load()
}

async function uploadImage(options) {
  const fd = new FormData()
  fd.append('file', options.file)
  const res = await fetch('/api/questions/upload-image', {
    method: 'POST',
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    body: fd
  }).then(r => r.json())
  if (res.image_url) {
    form.image_url = res.image_url
    ElMessage.success('图片已上传')
  } else {
    ElMessage.error(res.detail || '上传失败')
  }
}
</script>

<template>
  <el-card class="page-card" shadow="never">
    <div class="bar">
      <el-input v-model="query.keyword" placeholder="搜题干关键字" clearable style="width: 210px" @keyup.enter="search" />
      <el-select v-model="query.type" placeholder="全部题型" clearable style="width: 128px">
        <el-option v-for="t in types" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="query.scope" placeholder="全部知识范围" clearable style="width: 176px">
        <el-option v-for="s in scopes" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="query.source" placeholder="全部来源" clearable style="width: 118px">
        <el-option v-for="s in sources" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="query.difficulty" placeholder="全部难度" clearable style="width: 128px">
        <el-option v-for="l in LEVELS" :key="l.value" :label="l.text" :value="l.value" />
      </el-select>
      <el-select v-model="query.has_answer" placeholder="有无答案" clearable style="width: 118px">
        <el-option label="有答案" :value="true" />
        <el-option label="无答案" :value="false" />
      </el-select>
      <el-select v-model="query.status" placeholder="在用 / 停用" clearable style="width: 118px">
        <el-option label="在用的" value="active" />
        <el-option label="已停用" value="disabled" />
      </el-select>
      <el-checkbox v-model="onlyPinned" @change="search">只看必出</el-checkbox>
      <el-button type="primary" @click="search">查询</el-button>
      <div class="flex-1" />
      <el-dropdown @command="exportBank">
        <el-button>导出 Excel<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="all">导出完整题库</el-dropdown-item>
            <el-dropdown-item command="custom">导出我补充的题（来源=自定义）</el-dropdown-item>
            <el-dropdown-item command="filtered" divided>按当前筛选条件导出</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button type="success" @click="openCreate">新增题目</el-button>
    </div>

    <div v-if="stats" class="stats">
      共 <b>{{ stats.total }}</b> 题
      <span v-for="(v, k) in stats.by_type" :key="k"> ｜ {{ k }} {{ v }}</span>
      ｜ 带图 {{ stats.with_image }} ｜ 必出 {{ stats.pinned }}
      <template v-if="stats.disabled"> ｜ <span class="dis-n">已停用 {{ stats.disabled }}</span></template>
      <template v-if="stats.by_difficulty">
        <br />难度分布：<span v-for="l in LEVELS" :key="l.value" class="lv">
          {{ l.value }} 级 <b>{{ stats.by_difficulty[l.value] || 0 }}</b>
        </span>
        <span class="hint">（组卷时按难度给每道题分配分值）</span>
      </template>
    </div>
  </el-card>

  <el-card shadow="never">
    <!-- 勾了题才出现：批量停用 / 启用 / 删除 / 必出 / 改知识范围 / 改难度 -->
    <div v-if="picked.length" class="bulkbar">
      <span>已勾选 <b>{{ picked.length }}</b> 道</span>
      <el-button size="small" @click="bulk('disable')">停用</el-button>
      <el-button size="small" @click="bulk('enable')">启用</el-button>
      <el-button size="small" @click="bulk('pin')">设为必出</el-button>
      <el-button size="small" @click="bulk('unpin')">取消必出</el-button>
      <el-select v-model="bulkScope" size="small" placeholder="改成知识范围…" style="width: 200px">
        <el-option v-for="s in scopes" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button size="small" :disabled="!bulkScope" @click="bulk('scope', bulkScope)">改范围</el-button>
      <el-select v-model="bulkLevel" size="small" placeholder="改成难度…" style="width: 120px">
        <el-option v-for="l in LEVELS" :key="l.value" :label="l.text" :value="l.value" />
      </el-select>
      <el-button size="small" :disabled="!bulkLevel" @click="bulk('difficulty', bulkLevel)">改难度</el-button>
      <el-button size="small" type="danger" plain @click="bulk('delete')">删除</el-button>
      <el-button size="small" link @click="table?.clearSelection()">取消勾选</el-button>
    </div>
    <el-table
      ref="table"
      :data="rows"
      v-loading="loading"
      border
      stripe
      size="small"
      row-key="id"
      :row-class-name="rowClass"
      @selection-change="picked = $event"
    >
      <el-table-column type="selection" width="40" reserve-selection />
      <el-table-column label="编号" width="86">
        <template #default="{ row }">
          {{ row.code }}
          <el-tag v-if="row.is_disabled" size="small" type="info" effect="plain">已停用</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="题型" width="86">
        <template #default="{ row }">
          {{ row.type }}
          <el-tag v-if="isMulti(row)" size="small" type="warning" effect="plain">多选</el-tag>
        </template>
      </el-table-column>
      <!-- 长内容只露两行，末尾「展开」看全文（ClampText） -->
      <el-table-column label="题干" min-width="280">
        <template #default="{ row }"><ClampText :text="row.stem" /></template>
      </el-table-column>
      <el-table-column label="可选项" min-width="200">
        <template #default="{ row }">
          <ClampText v-if="row.options && row.options.length" :text="optionsLine(row)">
            <span v-for="o in row.options" :key="o.label" class="opt">{{ o.label }}.{{ o.content }}</span>
          </ClampText>
          <el-tag v-if="row.sim_task" size="small" type="success" effect="plain" class="simtag">
            🖥 {{ SIM_KINDS[row.sim_task.kind] || row.sim_task.kind }}自动判分
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="答案" width="110">
        <template #default="{ row }">
          <ClampText v-if="(row.answer || '').trim()" :text="row.answer" />
          <span v-else class="no-ans">无答案</span>
        </template>
      </el-table-column>
      <el-table-column prop="scope" label="知识范围" width="150" />
      <el-table-column prop="difficulty" label="难度" width="70" align="center" sortable>
        <template #default="{ row }">
          <span class="lv-dot" :class="'lv' + row.difficulty">{{ row.difficulty }}</span>
        </template>
      </el-table-column>
      <el-table-column label="图片" width="80">
        <template #default="{ row }">
          <el-image v-if="row.image_url" :src="row.image_url" :preview-src-list="[row.image_url]" style="width: 40px" />
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="必出" width="70">
        <template #default="{ row }">
          <el-switch :model-value="row.is_pinned" @change="togglePin(row)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager"
      background
      layout="total, sizes, prev, pager, next"
      :total="total"
      v-model:current-page="query.page"
      v-model:page-size="query.page_size"
      :page-sizes="[20, 50, 100]"
      @current-change="load"
      @size-change="search"
    />
  </el-card>

  <el-dialog v-model="dialog.visible" :title="dialog.editing ? '编辑题目' : '新增题目'" width="640px">
    <el-form label-width="90px">
      <el-form-item label="题型">
        <el-select v-model="form.type" style="width: 160px">
          <el-option v-for="t in types" :key="t" :label="t" :value="t" />
        </el-select>
        <el-checkbox v-model="form.is_pinned" style="margin-left: 16px">设为必出题</el-checkbox>
      </el-form-item>
      <el-form-item label="题干">
        <el-input v-model="form.stem" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item v-if="form.type === '选择题'" label="可选项">
        <div v-for="o in form.options" :key="o.label" class="opt-row">
          <span class="opt-label">{{ o.label }}</span>
          <el-input v-model="o.content" placeholder="留空表示不用这一项" />
        </div>
      </el-form-item>
      <el-form-item label="答案">
        <el-select v-if="form.type === '判断题'" v-model="form.answer" style="width: 160px">
          <el-option label="正确" value="正确" />
          <el-option label="错误" value="错误" />
        </el-select>
        <template v-else-if="form.type === '选择题'">
          <el-checkbox-group v-model="answerLetters">
            <el-checkbox v-for="o in form.options" :key="o.label" :value="o.label" :disabled="!o.content.trim()">
              {{ o.label }}
            </el-checkbox>
          </el-checkbox-group>
          <span class="hint">勾一个是单选；勾两个以上就是多选题（学生作答时出复选框，全对才得分）</span>
        </template>
        <template v-else-if="form.type === '填空题'">
          <el-input
            v-model="form.answer"
            type="textarea"
            :rows="2"
            placeholder="第一空：数据（特征数据）；第二空：特征库"
          />
          <span class="hint">
            几个空用「；」隔开，可以写「第一空：」；括号里写也算对的说法，如「专业（或领域专属）」。学生每空一个输入框，按空给分。
          </span>
        </template>
        <el-input v-else v-model="form.answer" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="知识范围">
        <el-select v-model="form.scope" style="width: 220px">
          <el-option v-for="s in scopes" :key="s" :label="s" :value="s" />
        </el-select>
      </el-form-item>
      <el-form-item label="难度">
        <el-select v-model="form.difficulty" style="width: 160px" placeholder="自动判断">
          <el-option v-for="l in LEVELS" :key="l.value" :label="l.text" :value="l.value" />
        </el-select>
        <span class="hint">
          只用数字 1~5。不选就按题型和题干长度自动估一个，之后随时能改。组卷时按它分配分值。
        </span>
      </el-form-item>
      <el-form-item v-if="form.type === '操作题'" label="仿真任务">
        <el-select v-model="form.sim_task_id" clearable placeholder="不挂（老师人工评阅）" style="width: 300px">
          <el-option
            v-for="t in sims"
            :key="t.id"
            :label="`${SIM_KINDS[t.kind] || t.kind} · ${t.title}`"
            :value="t.id"
          />
        </el-select>
        <span class="hint">
          挂上之后，学生在网页里把操作真做一遍，交卷按检查点自动判分，分数预填到成绩页、老师能改。
          去「题库 → 仿真操作题」里建。
        </span>
      </el-form-item>
      <el-form-item label="配图">
        <el-upload :http-request="uploadImage" :show-file-list="false" accept="image/*">
          <el-button>上传图片</el-button>
        </el-upload>
        <el-image v-if="form.image_url" :src="form.image_url" style="width: 90px; margin-left: 12px" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialog.visible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.bar {
  display: flex;
  flex-wrap: wrap;    /* 筛选项多了，窄屏换行，别把下拉框挤成「全部…」 */
  gap: 10px;
  align-items: center;
}
.bar :deep(.el-select) {
  flex: none;
}
.flex-1 {
  flex: 1;
}
.stats {
  margin-top: 12px;
  color: #606266;
  font-size: 13px;
}
.no-ans {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.opt {
  margin-right: 10px;
  color: #606266;
  font-size: 12px;
}
.hint {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.lv {
  margin-right: 10px;
}
/* 难度用一个小圆点，数字一眼可读，颜色从浅到深 */
.lv-dot {
  display: inline-block;
  width: 22px;
  height: 22px;
  line-height: 22px;
  border-radius: 50%;
  font-size: 12px;
  font-family: ui-monospace, Consolas, monospace;
}
.lv1 { background: var(--el-color-success-light-9); color: var(--el-color-success); }
.lv2 { background: var(--el-color-success-light-8, #e1f3d8); color: var(--el-color-success); }
.lv3 { background: var(--el-fill-color); color: var(--el-text-color-regular); }
.lv4 { background: var(--el-color-warning-light-9); color: var(--el-color-warning); }
.lv5 { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }
.opt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  width: 100%;
}
.opt-label {
  width: 18px;
  color: #909399;
}
.bulkbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  font-size: 13px;
}
.bulkbar :deep(.el-button + .el-button) {
  margin-left: 0;
}
.dis-n {
  color: var(--el-color-warning);
}
:deep(.row-disabled) td {
  color: var(--el-text-color-placeholder);
}
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>

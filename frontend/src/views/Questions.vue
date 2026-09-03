<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download } from '../api'

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const scopes = ref([])
const types = ref([])
const sources = ref([])
const stats = ref(null)
const onlyPinned = ref(false)

const query = reactive({
  keyword: '',
  type: '',
  scope: '',
  source: '',
  page: 1,
  page_size: 20
})

const dialog = reactive({ visible: false, editing: null })
const blank = () => ({
  type: '选择题',
  stem: '',
  answer: '',
  scope: '',
  source: '自定义',
  image_url: '',
  is_pinned: false,
  options: [
    { label: 'A', content: '' },
    { label: 'B', content: '' },
    { label: 'C', content: '' },
    { label: 'D', content: '' }
  ]
})
const form = reactive(blank())

function activeFilters() {
  const params = { ...query }
  delete params.page
  delete params.page_size
  Object.keys(params).forEach(k => params[k] === '' && delete params[k])
  if (onlyPinned.value) params.pinned = true
  return params
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
    is_pinned: row.is_pinned,
    options: row.options.length
      ? row.options.map(o => ({ ...o }))
      : blank().options
  })
  dialog.visible = true
}

async function save() {
  if (!form.stem.trim()) return ElMessage.warning('题干不能为空')
  if (!form.scope) return ElMessage.warning('请选择知识范围')

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
    </div>
  </el-card>

  <el-card shadow="never">
    <el-table :data="rows" v-loading="loading" border stripe size="small">
      <el-table-column prop="code" label="编号" width="80" />
      <el-table-column prop="type" label="题型" width="80" />
      <el-table-column prop="stem" label="题干" min-width="280" show-overflow-tooltip />
      <el-table-column label="可选项" min-width="200">
        <template #default="{ row }">
          <span v-for="o in row.options" :key="o.label" class="opt">{{ o.label }}.{{ o.content }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="answer" label="答案" width="90" />
      <el-table-column prop="scope" label="知识范围" width="150" />
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
        <el-select v-else-if="form.type === '选择题'" v-model="form.answer" style="width: 160px">
          <el-option v-for="o in form.options" :key="o.label" :label="o.label" :value="o.label" />
        </el-select>
        <el-input v-else v-model="form.answer" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="知识范围">
        <el-select v-model="form.scope" style="width: 220px">
          <el-option v-for="s in scopes" :key="s" :label="s" :value="s" />
        </el-select>
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
  gap: 10px;
  align-items: center;
}
.flex-1 {
  flex: 1;
}
.stats {
  margin-top: 12px;
  color: #606266;
  font-size: 13px;
}
.opt {
  margin-right: 10px;
  color: #606266;
  font-size: 12px;
}
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
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>

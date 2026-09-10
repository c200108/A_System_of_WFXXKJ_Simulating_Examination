<script setup>
/** 打字练习文本库管理：逐条增删改 + 上传 txt 批量导入。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const MODES = [
  { value: 'chinese', label: '中文' },
  { value: 'english', label: '英文' }
]

const rows = ref([])
const stats = ref({ english: {}, chinese: {} })
const difficulties = ref(['简单', '中等', '困难'])
const loading = ref(false)

const query = reactive({ mode: 'chinese', difficulty: '', keyword: '' })

const dialog = ref(false)
const editing = ref(null)
const form = reactive({ mode: 'chinese', difficulty: '简单', content: '' })

const importDlg = ref(false)
const imp = reactive({ mode: 'chinese', difficulty: '简单', split: 'line' })
const importing = ref(false)

async function load() {
  loading.value = true
  try {
    const params = { ...query }
    Object.keys(params).forEach(k => params[k] === '' && delete params[k])
    rows.value = await api.typingTexts(params)
    stats.value = await api.typingTextStats()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const cfg = await api.typingConfig()
    if (cfg.difficulties?.length) difficulties.value = cfg.difficulties
  } catch {
    /* 取不到就用默认三档 */
  }
  await load()
})

/** 每档有多少段，一眼看出哪档缺文本 */
const summary = computed(() =>
  MODES.map(m => ({
    ...m,
    counts: difficulties.value.map(d => ({ d, n: stats.value[m.value]?.[d] || 0 }))
  }))
)

function openCreate() {
  editing.value = null
  Object.assign(form, { mode: query.mode, difficulty: query.difficulty || '简单', content: '' })
  dialog.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, { mode: row.mode, difficulty: row.difficulty, content: row.content })
  dialog.value = true
}

async function save() {
  if (form.content.trim().length < 5) return ElMessage.warning('文本太短，至少 5 个字符')
  if (editing.value) {
    await api.typingTextUpdate(editing.value.id, {
      difficulty: form.difficulty,
      content: form.content
    })
  } else {
    await api.typingTextCreate({ ...form })
  }
  dialog.value = false
  await load()
  ElMessage.success('已保存')
}

async function toggleActive(row) {
  await api.typingTextUpdate(row.id, { is_active: !row.is_active })
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm('删除这段练习文本？', '提示', { type: 'warning' })
  await api.typingTextDelete(row.id)
  await load()
  ElMessage.success('已删除')
}

async function doImport(opt) {
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', opt.file)
    const qs = new URLSearchParams({
      mode: imp.mode,
      difficulty: imp.difficulty,
      split: imp.split
    })
    const res = await fetch(`/api/typing/texts/import?${qs}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      body: fd
    }).then(r => r.json())

    if (res.added === undefined) {
      ElMessage.error(res.detail || '导入失败')
    } else {
      importDlg.value = false
      await load()
      ElMessageBox.alert(
        `扫描 ${res.total} 段：成功导入 ${res.added} 段，` +
          `重复跳过 ${res.skipped} 段，太短忽略 ${res.too_short} 段。`,
        '导入完成',
        { confirmButtonText: '知道了' }
      )
    }
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="page-card">
    <template #header>
      <div class="head">
        <span>练习文本库</span>
        <div>
          <el-button size="small" @click="importDlg = true">上传 txt 批量导入</el-button>
          <el-button size="small" type="primary" @click="openCreate">添加一段</el-button>
        </div>
      </div>
    </template>

    <el-alert type="info" :closable="false" class="hint">
      学生每次练习会从对应难度里<b>随机抽几段拼成长文</b>，所以每档的段数越多，重复感越低。
      建议每档至少 10 段。
    </el-alert>

    <div class="summary">
      <div v-for="m in summary" :key="m.value" class="sgroup">
        <span class="sname">{{ m.label }}</span>
        <span
          v-for="c in m.counts"
          :key="c.d"
          class="spill"
          :class="{ low: c.n < 10 }"
        >{{ c.d }} <b>{{ c.n }}</b></span>
      </div>
    </div>

    <div class="bar">
      <el-select v-model="query.mode" style="width: 110px" @change="load">
        <el-option v-for="m in MODES" :key="m.value" :label="m.label" :value="m.value" />
      </el-select>
      <el-select v-model="query.difficulty" placeholder="全部难度" clearable style="width: 130px" @change="load">
        <el-option v-for="d in difficulties" :key="d" :label="d" :value="d" />
      </el-select>
      <el-input v-model="query.keyword" placeholder="搜内容" clearable style="width: 200px" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
    </div>
  </el-card>

  <el-card shadow="never">
    <el-empty v-if="!rows.length && !loading" description="这个筛选条件下还没有文本" :image-size="70" />
    <el-table v-else :data="rows" v-loading="loading" border size="small" max-height="560">
      <el-table-column prop="difficulty" label="难度" width="76" />
      <el-table-column prop="content" label="内容" min-width="380" show-overflow-tooltip />
      <el-table-column label="字数" width="70">
        <template #default="{ row }">{{ row.content.length }}</template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="76" />
      <el-table-column label="启用" width="70">
        <template #default="{ row }">
          <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="106" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <!-- 增改 -->
  <el-dialog v-model="dialog" :title="editing ? '编辑文本' : '添加文本'" width="620px">
    <el-form label-width="70px">
      <el-form-item label="语言">
        <el-select v-model="form.mode" :disabled="!!editing" style="width: 120px">
          <el-option v-for="m in MODES" :key="m.value" :label="m.label" :value="m.value" />
        </el-select>
        <span v-if="editing" class="hint-inline">语言不能改，需要换请删了重建</span>
      </el-form-item>
      <el-form-item label="难度">
        <el-select v-model="form.difficulty" style="width: 120px">
          <el-option v-for="d in difficulties" :key="d" :label="d" :value="d" />
        </el-select>
      </el-form-item>
      <el-form-item label="内容">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="5"
          placeholder="一段完整的练习文本。中文建议 20~60 字，英文建议 10~40 词。"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <!-- 导入 -->
  <el-dialog v-model="importDlg" title="上传 txt 批量导入" width="560px">
    <el-form label-width="86px">
      <el-form-item label="导入到">
        <el-select v-model="imp.mode" style="width: 110px">
          <el-option v-for="m in MODES" :key="m.value" :label="m.label" :value="m.value" />
        </el-select>
        <el-select v-model="imp.difficulty" style="width: 110px; margin-left: 10px">
          <el-option v-for="d in difficulties" :key="d" :label="d" :value="d" />
        </el-select>
      </el-form-item>
      <el-form-item label="分段方式">
        <el-radio-group v-model="imp.split">
          <el-radio value="line">一行一段</el-radio>
          <el-radio value="blank">空行分段</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <div class="split-tip">
      <b>一行一段</b>：文件里每行就是一段练习文本，空行自动忽略。<b>多数情况用这个。</b><br />
      <b>空行分段</b>：用空行隔开的整块算一段，段内换行会折成空格。贴整篇文章时用。
    </div>

    <el-upload drag :http-request="doImport" :show-file-list="false" accept=".txt" :disabled="importing">
      <div class="up">
        <div class="upicon">📄</div>
        <div>把 .txt 拖到这里，或点击选择</div>
        <div class="uphint">支持 UTF-8 和 GBK 编码，单个文件不超过 2 MB；重复内容自动跳过</div>
      </div>
    </el-upload>
  </el-dialog>
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
.summary {
  display: flex;
  gap: 30px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.sgroup {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sname {
  font-weight: 600;
  font-size: 13px;
}
.spill {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
.spill b {
  font-family: ui-monospace, Consolas, monospace;
  margin-left: 3px;
}
.spill.low {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.hint-inline {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.split-tip {
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 14px;
}
.up {
  padding: 26px 0;
}
.upicon {
  font-size: 34px;
  margin-bottom: 8px;
}
.uphint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
</style>

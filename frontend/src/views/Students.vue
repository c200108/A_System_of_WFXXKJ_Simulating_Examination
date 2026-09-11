<script setup>
/**
 * 教师端：学生账号管理。
 *
 * 一个班几十号人，一个个建太慢，所以主推「按班级粘名单」批量建号：
 * 从花名册里复制「学号 姓名」两列粘进来就行，初始密码是学号。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const rows = ref([])
const classes = ref([])
const loading = ref(false)
const picked = ref([])

const query = reactive({ student_class: '', keyword: '' })

const dialog = ref(false)
const editing = ref(null)
const form = reactive({ student_no: '', name: '', student_class: '', password: '' })

const batchDlg = ref(false)
const batch = reactive({ student_class: '', text: '' })
const batching = ref(false)

async function load() {
  loading.value = true
  try {
    const params = {}
    if (query.student_class) params.student_class = query.student_class
    if (query.keyword.trim()) params.keyword = query.keyword.trim()
    rows.value = await api.students(params)
    classes.value = await api.studentClasses()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const pickedNames = computed(() => picked.value.map(s => s.name).join('、'))

// ---------- 单个增改 ----------
function openCreate() {
  editing.value = null
  Object.assign(form, {
    student_no: '',
    name: '',
    student_class: query.student_class || '',
    password: ''
  })
  dialog.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    student_no: row.student_no,
    name: row.name,
    student_class: row.student_class,
    password: ''
  })
  dialog.value = true
}

async function save() {
  if (editing.value) {
    const data = { name: form.name, student_class: form.student_class }
    if (form.password) data.password = form.password
    await api.studentUpdate(editing.value.id, data)
  } else {
    // 学号和密码的规则由后端判，报错会直接显示出来
    await api.studentCreate({ ...form })
  }
  dialog.value = false
  await load()
  ElMessage.success('已保存')
}

// ---------- 批量建号 ----------
async function doBatch() {
  if (!batch.text.trim()) return ElMessage.warning('先把名单粘进来')
  batching.value = true
  try {
    const res = await api.studentBatch({ ...batch })
    batchDlg.value = false
    await load()

    const lines = [
      `新建 ${res.added} 个账号`,
      res.skipped ? `${res.skipped} 个学号已存在，跳过` : '',
      res.error_count ? `${res.error_count} 行格式不对，没有导入` : ''
    ].filter(Boolean)

    await ElMessageBox.alert(
      lines.join('，') +
        '。\n\n初始密码就是学号，请提醒学生登录后到「首页」改密码。' +
        (res.errors?.length ? '\n\n有问题的行：\n' + res.errors.join('\n') : ''),
      '导入完成',
      { confirmButtonText: '知道了' }
    )
  } finally {
    batching.value = false
  }
}

// ---------- 批量操作 ----------
async function bulk(action) {
  const ids = picked.value.map(s => s.id)
  if (!ids.length) return ElMessage.warning('先勾选学生')

  if (action === 'delete') {
    await ElMessageBox.prompt(
      `即将永久删除 ${ids.length} 个学生账号：${pickedNames.value}\n\n` +
        '他们交过的卷子和练过的字都会保留，只是不再挂在账号上。\n' +
        '删除无法撤销。只是想让人登不上的话，用「批量停用」。\n\n' +
        '确认请输入「删除」两个字：',
      '危险操作',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
        inputPlaceholder: '在这里输入：删除',
        inputValidator: v => (v || '').trim() === '删除' || '请准确输入「删除」两个字',
        inputErrorMessage: '请准确输入「删除」两个字'
      }
    )
  } else if (action === 'reset_password') {
    await ElMessageBox.confirm(
      `把这 ${ids.length} 个学生的密码重置成各自的学号？\n${pickedNames.value}`,
      '重置密码',
      { type: 'warning' }
    )
  } else if (action === 'disable') {
    await ElMessageBox.confirm(
      `停用 ${ids.length} 个账号？停用后他们登不上，数据都在，随时可以再启用。`,
      '批量停用',
      { type: 'warning' }
    )
  }

  const res = await api.studentBulk(ids, action)
  picked.value = []
  await load()
  const verb = {
    delete: '删除',
    disable: '停用',
    enable: '启用',
    reset_password: '重置密码'
  }[action]
  ElMessage.success(`已${verb} ${res.affected} 个账号`)
}

const fmt = t => String(t || '').replace('T', ' ').slice(0, 16)
</script>

<template>
  <el-card shadow="never" class="page-card">
    <template #header>
      <div class="head">
        <span>学生账号</span>
        <div>
          <el-button size="small" @click="batchDlg = true">按班级批量建号</el-button>
          <el-button size="small" type="primary" @click="openCreate">添加一个</el-button>
        </div>
      </div>
    </template>

    <el-alert type="info" :closable="false" class="hint">
      学生用<b>学号</b>登录学生平台（网站首页），初始密码就是学号。
      系统里没有邮箱，学生忘了密码只能由老师重置。
    </el-alert>

    <div class="bar">
      <el-select v-model="query.student_class" placeholder="全部班级" clearable style="width: 160px" @change="load">
        <el-option v-for="c in classes" :key="c" :label="c" :value="c" />
      </el-select>
      <el-input
        v-model="query.keyword"
        placeholder="搜姓名或学号"
        clearable
        style="width: 200px"
        @keyup.enter="load"
      />
      <el-button type="primary" @click="load">查询</el-button>
      <span class="total">共 {{ rows.length }} 人</span>
    </div>
  </el-card>

  <el-card shadow="never">
    <div v-if="picked.length" class="bulkbar">
      <span class="cnt">已选 <b>{{ picked.length }}</b> 人</span>
      <span class="names">{{ pickedNames }}</span>
      <span class="grow" />
      <el-button size="small" @click="bulk('reset_password')">重置密码</el-button>
      <el-button size="small" @click="bulk('enable')">启用</el-button>
      <el-button size="small" type="warning" @click="bulk('disable')">停用</el-button>
      <el-button size="small" type="danger" @click="bulk('delete')">删除</el-button>
      <el-button size="small" link @click="picked = []">取消选择</el-button>
    </div>

    <el-empty v-if="!rows.length && !loading" description="还没有学生账号，先用「按班级批量建号」导一批" :image-size="80" />
    <el-table
      v-else
      :data="rows"
      v-loading="loading"
      border
      size="small"
      max-height="600"
      @selection-change="picked = $event"
    >
      <el-table-column type="selection" width="42" />
      <el-table-column label="序号" width="60" align="center">
        <!-- 显示行号而不是数据库主键，删掉谁之后编号自动接上 -->
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="student_no" label="学号" width="130" />
      <el-table-column prop="name" label="姓名" width="110" show-overflow-tooltip />
      <el-table-column prop="student_class" label="班级" width="130">
        <template #default="{ row }">
          <span v-if="row.student_class">{{ row.student_class }}</span>
          <span v-else class="blank">未分班</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <span :class="row.is_active ? 'on' : 'off'">{{ row.is_active ? '正常' : '已停用' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="140">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <!-- 单个增改 -->
  <el-dialog v-model="dialog" :title="editing ? '编辑学生' : '添加学生'" width="440px">
    <el-form label-width="80px">
      <el-form-item label="学号">
        <el-input v-model="form.student_no" :disabled="!!editing" placeholder="登录用，建议用学籍号" />
        <span v-if="editing" class="inline-hint">学号是身份，要换只能删了重建</span>
      </el-form-item>
      <el-form-item label="姓名">
        <el-input v-model="form.name" placeholder="学生姓名" />
      </el-form-item>
      <el-form-item label="班级">
        <el-input v-model="form.student_class" placeholder="如 七(3)班" />
      </el-form-item>
      <el-form-item :label="editing ? '重置密码' : '初始密码'">
        <el-input v-model="form.password" :placeholder="editing ? '留空则不改密码' : '留空则用学号当密码'" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <!-- 批量建号 -->
  <el-dialog v-model="batchDlg" title="按班级批量建号" width="560px">
    <el-form label-width="80px">
      <el-form-item label="班级">
        <el-input v-model="batch.student_class" placeholder="如 七(3)班，这一批都归到这个班" style="width: 240px" />
      </el-form-item>
    </el-form>

    <div class="tip">
      一行一个学生，<b>学号在前，姓名在后，中间用空格隔开</b>。<br />
      从花名册里把两列复制过来直接粘贴即可。已存在的学号会自动跳过。<br />
      <b>初始密码就是学号</b>，提醒学生登录后到「首页」改掉。
    </div>

    <el-input
      v-model="batch.text"
      type="textarea"
      :rows="10"
      placeholder="20260101 张三&#10;20260102 李四&#10;20260103 王五"
      class="mono"
    />

    <template #footer>
      <el-button @click="batchDlg = false">取消</el-button>
      <el-button type="primary" :loading="batching" @click="doBatch">开始导入</el-button>
    </template>
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
.bar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.total {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
.blank {
  color: var(--el-text-color-placeholder);
}
.on {
  color: var(--el-color-success);
}
.off {
  color: var(--el-text-color-placeholder);
}
.inline-hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.bulkbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 9px 14px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  font-size: 13px;
}
.bulkbar .cnt b {
  color: var(--el-color-primary);
  font-family: ui-monospace, Consolas, monospace;
  margin: 0 2px;
}
.bulkbar .names {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bulkbar .grow {
  flex: 1;
}

.tip {
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.mono :deep(textarea) {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 13px;
  line-height: 1.8;
}
</style>

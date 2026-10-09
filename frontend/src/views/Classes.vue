<script setup>
/**
 * 班级管理。挂在「学生」工作台里，和学生账号并排（见 StudentHub.vue）。
 *
 * 班级归属决定谁能给谁发考试：老师只能给自己名下的班发，管理员发的
 * 全体学生都收得到。所以「把班分给谁」是这一页最要紧的操作。
 *
 * 老师也能打开这一页，但只能看 —— 发考试要选班，得知道有哪些班；
 * 点开某个班还能看清里面都有谁。**增删改和分配一律限管理员**，
 * 界面藏起来只是顺手，真正拦住的是后端的 require_admin。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { currentUser } from '../auth'

const rows = ref([])
const teachers = ref([])
const loading = ref(false)

const isAdmin = computed(() => currentUser.value?.role === 'admin')

// ---------- 勾选 ----------
// 勾中的班级 id。批量删班、批量分配班主任都用它 —— 开学建错一批、
// 一个年级六个班要分给同一位老师，一个个点太慢。
const picked = ref([])
const isPicked = id => picked.value.includes(id)
const togglePick = (id, on) => {
  picked.value = on ? [...new Set([...picked.value, id])] : picked.value.filter(x => x !== id)
}
const pickedRows = computed(() => rows.value.filter(c => isPicked(c.id)))

/** 一个年级整体勾上 / 取消。年级是最常用的批量单位。 */
function toggleGrade(list, on) {
  const ids = list.map(c => c.id)
  picked.value = on
    ? [...new Set([...picked.value, ...ids])]
    : picked.value.filter(x => !ids.includes(x))
}
const gradeAllPicked = list => list.length > 0 && list.every(c => isPicked(c.id))
const gradeSomePicked = list => list.some(c => isPicked(c.id)) && !gradeAllPicked(list)

function toggleAll() {
  picked.value = picked.value.length === rows.value.length ? [] : rows.value.map(c => c.id)
}

const dialog = ref(false)
const editing = ref(null)
const form = reactive({ grade: '', name: '', owner_id: null })

const batchDlg = ref(false)
const batch = reactive({ grade: '', start: 1, end: 12, suffix: '班' })

const ownerDlg = ref(false)
const ownerPick = ref(null)

async function load() {
  loading.value = true
  try {
    rows.value = await api.classes({ include_inactive: true })
    if (isAdmin.value) teachers.value = await api.listUsers()
    // 列表刷新后把已经不存在的班从勾选里去掉，否则批量操作会带上幽灵 id
    const live = new Set(rows.value.map(c => c.id))
    picked.value = picked.value.filter(id => live.has(id))
  } finally {
    loading.value = false
  }
}
onMounted(load)

/** 按年级分组显示，一屏能看清整个年级的归属情况 */
const grouped = computed(() => {
  const map = new Map()
  for (const c of rows.value) {
    if (!map.has(c.grade)) map.set(c.grade, [])
    map.get(c.grade).push(c)
  }
  return [...map.entries()].map(([grade, list]) => ({ grade, list }))
})

const noOwner = computed(() => rows.value.filter(c => !c.owner_id).length)

// ---------- 班级详情 ----------
const detail = ref(null)          // 当前打开的班级
const detailRows = ref([])        // 这个班的学生
const detailLoading = ref(false)
const detailKeyword = ref('')

async function openDetail(row) {
  detail.value = row
  detailKeyword.value = ''
  detailRows.value = []
  detailLoading.value = true
  try {
    detailRows.value = await api.students({ class_id: row.id })
  } finally {
    detailLoading.value = false
  }
}

const detailShown = computed(() => {
  const kw = detailKeyword.value.trim()
  if (!kw) return detailRows.value
  return detailRows.value.filter(s => s.student_no.includes(kw) || s.name.includes(kw))
})

/** 男女人数是名单里现成的，如实数一下；成绩类统计要等总览做出来。 */
const detailStats = computed(() => {
  const list = detailRows.value
  return {
    total: list.length,
    male: list.filter(s => s.gender === '男').length,
    female: list.filter(s => s.gender === '女').length,
    unknown: list.filter(s => !s.gender).length,
    inactive: list.filter(s => !s.is_active).length
  }
})

// ---------- 增删改 ----------
function openCreate() {
  editing.value = null
  Object.assign(form, { grade: '', name: '', owner_id: null })
  dialog.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, { grade: row.grade, name: row.name, owner_id: row.owner_id })
  dialog.value = true
}

async function save() {
  if (editing.value) {
    await api.classUpdate(editing.value.id, { ...form })
  } else {
    await api.classCreate({ ...form })
  }
  dialog.value = false
  await load()
  ElMessage.success('已保存')
}

/** 直接在列表里换班主任，不用开弹窗 */
async function setOwner(row, owner_id) {
  await api.classUpdate(row.id, { owner_id })
  await load()
  ElMessage.success(owner_id ? '已分配' : '已取消分配')
}

async function doBatch() {
  if (!batch.grade.trim()) return ElMessage.warning('先填年级')
  const res = await api.classBatch({ ...batch })
  batchDlg.value = false
  await load()
  ElMessage.success(
    `新建 ${res.added} 个班` + (res.skipped ? `，${res.skipped} 个已存在跳过` : '')
  )
}

async function remove(row) {
  const tip =
    row.student_count > 0
      ? `「${row.display}」里还有 ${row.student_count} 名学生。\n删除后他们会变成「未分班」，需要重新分配。\n\n确认请输入「删除」两个字：`
      : `确定删除「${row.display}」吗？\n\n确认请输入「删除」两个字：`

  await ElMessageBox.prompt(tip, '删除班级', {
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
    confirmButtonClass: 'el-button--danger',
    inputPlaceholder: '在这里输入：删除',
    inputValidator: v => (v || '').trim() === '删除' || '请准确输入「删除」两个字',
    inputErrorMessage: '请准确输入「删除」两个字'
  })

  // 班里有人时后端会拦一道，这里明确带上 force 表示"我知道"
  const res = await api.classDelete(row.id, row.student_count > 0)
  if (detail.value?.id === row.id) detail.value = null
  await load()
  ElMessage.success(
    res.detached ? `已删除，${res.detached} 名学生变成未分班` : '已删除'
  )
}

// ---------- 批量操作 ----------
async function removePicked() {
  const list = pickedRows.value
  if (!list.length) return ElMessage.warning('先勾选要删的班')

  const withStudents = list.filter(c => c.student_count > 0)
  const total = withStudents.reduce((n, c) => n + c.student_count, 0)
  const names = list.map(c => c.display).join('、')

  // 把"有人的班"单独摆出来 —— 批量操作最怕的就是顺手把有学生的班一起删了
  const lines = [`即将删除 ${list.length} 个班级：`, names]
  if (withStudents.length) {
    lines.push(
      `其中 ${withStudents.length} 个班里还有学生，共 ${total} 人：`,
      withStudents.map(c => `　${c.display}（${c.student_count} 人）`).join('\n'),
      '删除后这些学生会变成「未分班」，需要重新分配。'
    )
  } else {
    lines.push('这些班里都没有学生。')
  }
  lines.push('确认请输入「删除」两个字：')

  await ElMessageBox.prompt(lines.join('\n\n'), '批量删除班级', {
    confirmButtonText: `确认删除 ${list.length} 个班`,
    cancelButtonText: '取消',
    confirmButtonClass: 'el-button--danger',
    inputPlaceholder: '在这里输入：删除',
    inputValidator: v => (v || '').trim() === '删除' || '请准确输入「删除」两个字',
    inputErrorMessage: '请准确输入「删除」两个字'
  })

  const res = await api.classBulkDelete(list.map(c => c.id), withStudents.length > 0)
  picked.value = []
  await load()
  if (detail.value && !rows.value.some(c => c.id === detail.value.id)) detail.value = null
  ElMessage.success(
    res.detached
      ? `已删除 ${res.deleted} 个班，${res.detached} 名学生变成未分班`
      : `已删除 ${res.deleted} 个班`
  )
}

function openOwnerDlg() {
  if (!picked.value.length) return ElMessage.warning('先勾选要分配的班')
  ownerPick.value = null
  ownerDlg.value = true
}

async function doBulkOwner() {
  const res = await api.classBulkOwner(picked.value, ownerPick.value ?? null)
  ownerDlg.value = false
  picked.value = []
  await load()
  ElMessage.success(
    ownerPick.value ? `已把 ${res.updated} 个班分配出去` : `已取消 ${res.updated} 个班的分配`
  )
}
</script>

<template>
  <el-card shadow="never" class="page-card">
    <template #header>
      <div class="head">
        <span>班级</span>
        <div v-if="isAdmin">
          <el-button size="small" @click="batchDlg = true">按年级批量建班</el-button>
          <el-button size="small" type="primary" @click="openCreate">新建班级</el-button>
        </div>
      </div>
    </template>

    <el-alert v-if="isAdmin" type="info" :closable="false">
      班级决定<b>谁能给谁发考试</b>：老师只能给自己名下的班发，管理员发的考试全体学生都收得到。
      老师名下一个班都没有时，发不出考试。点班级名片可以看这个班都有谁。
    </el-alert>
    <el-alert v-else type="info" :closable="false">
      这里显示全校班级，<b>带「我的班」标记的是你带的班</b>。发考试时只能选这些班。
      点班级名片可以看这个班都有谁；班级的增删改和分配由管理员操作。
    </el-alert>

    <div v-if="isAdmin && noOwner" class="warn">
      还有 <b>{{ noOwner }}</b> 个班没有分配老师，这些班的学生只能收到管理员发的考试。
    </div>
  </el-card>

  <!-- 勾了才出现，平时不占地方 -->
  <el-card v-if="isAdmin && picked.length" shadow="never" class="picked-bar">
    <span>已选中 <b>{{ picked.length }}</b> 个班级</span>
    <el-button size="small" @click="picked = []">取消选择</el-button>
    <el-button size="small" type="primary" @click="openOwnerDlg">批量分配老师</el-button>
    <el-button size="small" type="danger" @click="removePicked">批量删除</el-button>
  </el-card>

  <el-card v-loading="loading" shadow="never">
    <el-empty v-if="!rows.length && !loading" description="还没有班级，先用「按年级批量建班」建一批" :image-size="80" />

    <div v-if="isAdmin && rows.length" class="allbar">
      <el-button link size="small" @click="toggleAll">
        {{ picked.length === rows.length ? '取消全选' : `全选（${rows.length} 个班）` }}
      </el-button>
    </div>

    <div v-for="g in grouped" :key="g.grade" class="gradeblock">
      <h3 class="gname">
        <el-checkbox
          v-if="isAdmin"
          :model-value="gradeAllPicked(g.list)"
          :indeterminate="gradeSomePicked(g.list)"
          @change="toggleGrade(g.list, $event)"
        />
        {{ g.grade }}<span class="gcount">{{ g.list.length }} 个班</span>
      </h3>
      <div class="grid">
        <article
          v-for="c in g.list"
          :key="c.id"
          class="cls"
          :class="{ mine: c.owner_id === currentUser?.id, orphan: !c.owner_id, on: isPicked(c.id) }"
        >
          <div class="top">
            <el-checkbox
              v-if="isAdmin"
              :model-value="isPicked(c.id)"
              @change="togglePick(c.id, $event)"
            />
            <!-- 班名可点，进班级详情。勾选框在它外面，点勾不会顺带打开详情 -->
            <button type="button" class="cname" @click="openDetail(c)">{{ c.name }}</button>
            <el-tag v-if="c.owner_id === currentUser?.id" size="small" type="success" effect="light">
              我的班
            </el-tag>
          </div>

          <button type="button" class="stu" @click="openDetail(c)">
            {{ c.student_count }} 名学生 <span class="go">查看 ›</span>
          </button>

          <div class="owner">
            <el-select
              v-if="isAdmin"
              :model-value="c.owner_id"
              placeholder="未分配"
              clearable
              size="small"
              style="width: 100%"
              @change="setOwner(c, $event ?? null)"
            >
              <el-option
                v-for="t in teachers"
                :key="t.id"
                :label="`${t.name || t.username}${t.role === 'admin' ? '（管理员）' : ''}`"
                :value="t.id"
                :disabled="!t.is_active"
              />
            </el-select>
            <span v-else class="ownername">
              {{ c.owner_name || '未分配' }}
            </span>
          </div>

          <div v-if="isAdmin" class="acts">
            <el-button link size="small" type="primary" @click="openEdit(c)">改名</el-button>
            <el-button link size="small" type="danger" @click="remove(c)">删除</el-button>
          </div>
        </article>
      </div>
    </div>
  </el-card>

  <!-- 班级详情：这个班都有谁，加上一块总览的位置 -->
  <el-drawer
    :model-value="!!detail"
    :title="detail ? detail.display : ''"
    size="min(760px, 94vw)"
    @update:model-value="detail = null"
  >
    <template v-if="detail">
      <div class="dmeta">
        <span>班主任：<b>{{ detail.owner_name || '未分配' }}</b></span>
        <span>学生：<b>{{ detailStats.total }}</b> 人</span>
        <span>
          男 <b>{{ detailStats.male }}</b> · 女 <b>{{ detailStats.female }}</b>
          <template v-if="detailStats.unknown"> · 未填 <b>{{ detailStats.unknown }}</b></template>
        </span>
        <span v-if="detailStats.inactive" class="muted">停用 {{ detailStats.inactive }} 人</span>
      </div>

      <div class="soon">
        <b>班级总览</b>
        <span>考试均分、及格率、打字训练情况这些还没做，先占个位置。</span>
      </div>

      <div class="dsearch">
        <el-input
          v-model="detailKeyword"
          size="small"
          clearable
          placeholder="按学号或姓名找人"
          style="width: 220px"
        />
        <span class="muted">共 {{ detailShown.length }} 人</span>
      </div>

      <el-table v-loading="detailLoading" :data="detailShown" size="small" height="calc(100vh - 300px)">
        <el-table-column prop="student_no" label="学号" width="130" />
        <el-table-column prop="name" label="姓名" min-width="110" />
        <el-table-column prop="gender" label="性别" width="70">
          <template #default="{ row }">{{ row.gender || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag v-if="!row.is_active" size="small" type="info">停用</el-tag>
            <span v-else class="muted">正常</span>
          </template>
        </el-table-column>
        <template #empty>
          <span class="muted">
            {{ detailKeyword ? '没找到这个人' : '这个班还没有学生，去「学生管理」导入名单' }}
          </span>
        </template>
      </el-table>
    </template>
  </el-drawer>

  <!-- 新建 / 改名 -->
  <el-dialog v-model="dialog" :title="editing ? '修改班级' : '新建班级'" width="420px">
    <el-form label-width="70px">
      <el-form-item label="年级">
        <el-input v-model="form.grade" placeholder="如 七年级" style="width: 160px" />
      </el-form-item>
      <el-form-item label="班级">
        <el-input v-model="form.name" placeholder="如 3班" style="width: 160px" />
      </el-form-item>
      <el-form-item label="任课老师">
        <el-select v-model="form.owner_id" placeholder="暂不分配" clearable style="width: 200px">
          <el-option
            v-for="t in teachers"
            :key="t.id"
            :label="t.name || t.username"
            :value="t.id"
            :disabled="!t.is_active"
          />
        </el-select>
      </el-form-item>
      <p v-if="editing" class="dlg-tip">
        改了班级名，这个班里学生的班级显示也会跟着改；已经发出去的考试不受影响。
      </p>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <!-- 批量建班 -->
  <el-dialog v-model="batchDlg" title="按年级批量建班" width="440px">
    <el-form label-width="70px">
      <el-form-item label="年级">
        <el-input v-model="batch.grade" placeholder="如 七年级" style="width: 160px" />
      </el-form-item>
      <el-form-item label="班号">
        <el-input-number v-model="batch.start" :min="1" :max="99" controls-position="right" style="width: 100px" />
        <span class="dash">到</span>
        <el-input-number v-model="batch.end" :min="1" :max="99" controls-position="right" style="width: 100px" />
      </el-form-item>
      <el-form-item label="后缀">
        <el-input v-model="batch.suffix" style="width: 100px" />
        <span class="dlg-tip inline">建出来就是「{{ batch.grade || '七年级' }}{{ batch.start }}{{ batch.suffix }}」这样</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="batchDlg = false">取消</el-button>
      <el-button type="primary" @click="doBatch">建班</el-button>
    </template>
  </el-dialog>

  <!-- 批量分配老师 -->
  <el-dialog v-model="ownerDlg" title="批量分配老师" width="460px">
    <p class="dlg-tip">
      把选中的 <b>{{ picked.length }}</b> 个班一起分给同一位老师：<br />
      {{ pickedRows.map(c => c.display).join('、') }}
    </p>
    <el-form label-width="70px" style="margin-top: 12px">
      <el-form-item label="任课老师">
        <el-select v-model="ownerPick" placeholder="留空 = 取消分配" clearable style="width: 220px">
          <el-option
            v-for="t in teachers"
            :key="t.id"
            :label="`${t.name || t.username}${t.role === 'admin' ? '（管理员）' : ''}`"
            :value="t.id"
            :disabled="!t.is_active"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <p class="dlg-tip">这些班原来的归属会被覆盖。留空不选人就是把它们都变回「未分配」。</p>
    <template #footer>
      <el-button @click="ownerDlg = false">取消</el-button>
      <el-button type="primary" @click="doBulkOwner">
        {{ ownerPick ? '分配' : '取消分配' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.warn {
  margin-top: 12px;
  padding: 9px 14px;
  border-radius: 8px;
  font-size: 13px;
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.warn b {
  font-family: ui-monospace, Consolas, monospace;
}

.picked-bar {
  margin-bottom: 12px;
  display: flex;
}
.picked-bar :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
}
.allbar {
  margin-bottom: 10px;
}
.gradeblock {
  margin-bottom: 24px;
}
.gname {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
}
.gcount {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}
.cls {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--el-bg-color);
}
.cls.mine {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}
.cls.orphan {
  border-style: dashed;
}
.cls.on {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-7);
}
.top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cname {
  border: none;
  background: none;
  padding: 0;
  font-family: inherit;
  font-size: 15px;
  font-weight: 600;
  color: inherit;
  cursor: pointer;
  text-align: left;
}
.cname:hover {
  color: var(--el-color-primary);
}
.stu {
  border: none;
  background: none;
  padding: 0;
  font-family: inherit;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  text-align: left;
}
.stu:hover {
  color: var(--el-color-primary);
}
.stu .go {
  opacity: 0;
  transition: opacity 0.15s;
}
.cls:hover .stu .go {
  opacity: 1;
}
.ownername {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.acts {
  display: flex;
  gap: 4px;
  margin-top: 2px;
}
.dlg-tip {
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
  color: var(--el-text-color-secondary);
}
.dlg-tip.inline {
  margin-left: 12px;
}
.dash {
  margin: 0 8px;
  color: var(--el-text-color-secondary);
}

/* ---------- 详情抽屉 ---------- */
.dmeta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.soon {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
  margin: 12px 0;
  padding: 10px 14px;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.dsearch {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>

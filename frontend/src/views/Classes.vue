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
 *
 * 例外是**上机座次表**：每个班自己的事，班主任（名下的老师）和管理员都能传、换、删。
 * 图片点开在新页面直接看，Excel 点了下载。
 */
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download } from '../api'
import { currentUser } from '../auth'

// 在线座次：表格库（Jspreadsheet CE + ExcelJS）几百 KB，只有点开「查看」才下载
const SeatSheet = defineAsyncComponent(() => import('../components/SeatSheet.vue'))
const seatSheet = ref(null)
// 课堂情况日志：座次表右边一栏，跟着座次面板一起懒加载
const ClassLogs = defineAsyncComponent(() => import('../components/ClassLogs.vue'))
const classLogs = ref(null)
const panelFull = ref(false)
const panelFolded = ref(false)

/**
 * 点面板外面的空白处就收起成右下角的小按钮（2.22.0 起取代「收起」按钮），表格里没保存的改动不丢。
 * 弹出来的对话框、下拉框、右键菜单、提示条都挂在 body 上、不在面板里，点它们不算「外面」。
 */
const NOT_OUTSIDE = [
  '.seatpanel', '.seatpill', '.seatmenu', '.seat-ghost', '.el-overlay', '.el-popper', '.el-message',
  '.el-message-box__wrapper', '.el-notification', '.el-color-dropdown', '.jcontextmenu', '.jss_contextmenu'
].join(',')
function onOutside(e) {
  if (!detail.value || panelFolded.value || e.button !== 0) return
  if (e.target.closest && e.target.closest(NOT_OUTSIDE)) return
  if (!document.body.contains(e.target)) return       // 点的东西已经被移走了（下拉选完就消失）
  panelFolded.value = true
}
onMounted(() => document.addEventListener('mousedown', onOutside, true))
onBeforeUnmount(() => document.removeEventListener('mousedown', onOutside, true))

/**
 * 点班级卡片的空白处就打开在线座次（2.20.1 起取代「查看」按钮）。
 * 点在勾选框、下拉框、按钮、链接上是在做别的事，不跳。
 */
function onCardClick(e, c) {
  if (e.target.closest('button, a, input, label, .el-checkbox, .el-select, .el-button')) return
  if (window.getSelection?.().toString()) return      // 在选字，别打断
  openDetail(c)
}

async function closeDetail() {
  if (classLogs.value?.dirty) {
    try {
      await ElMessageBox.confirm('课堂日志写了还没保存，关掉就没了，确定关闭吗？', '关闭在线座次', {
        type: 'warning',
        confirmButtonText: '不要了，关闭',
        cancelButtonText: '回去保存'
      })
    } catch {
      return
    }
  }
  if (seatSheet.value?.dirty) {
    try {
      await ElMessageBox.confirm('座次表改了还没保存，先保存吗？', '关闭在线座次', {
        type: 'warning',
        confirmButtonText: '保存后关闭',
        cancelButtonText: '不保存',
        distinguishCancelAndClose: true
      })
      await seatSheet.value.save()
    } catch (action) {
      if (action !== 'cancel') return          // 点了右上角 ×：哪儿也不去
    }
  }
  detail.value = null
  panelFolded.value = false
}

/** 座次表里右键设了班长 / 组长：面板顶上的「班长 / 组长」跟着刷新 */
async function reloadRoster() {
  if (detail.value) detailRows.value = await api.students({ class_id: detail.value.id })
}

function onSeatSaved(got) {
  const row = rows.value.find(c => c.id === got.id)
  if (row) Object.assign(row, got)
  if (detail.value) Object.assign(detail.value, got)
}

// ---------- 上机座次表 ----------
const seatInput = ref()
const seatFor = ref(null)
const seatBusy = ref(0)
const canSeat = c => isAdmin.value || c.owner_id === currentUser.value?.id

function pickSeat(c) {
  seatFor.value = c
  seatInput.value.value = ''
  seatInput.value.click()
}

async function onSeatFile(e) {
  const file = e.target.files?.[0]
  const c = seatFor.value
  if (!file || !c) return
  if (!/\.(png|jpe?g|gif|webp|bmp|xlsx?)$/i.test(file.name)) {
    return ElMessage.warning('座次表只支持图片（png/jpg/gif/webp/bmp）或表格（xls/xlsx）')
  }
  seatBusy.value = c.id
  try {
    const got = await api.classSeatUpload(c.id, file)
    Object.assign(c, got)
    if (detail.value?.id === c.id) Object.assign(detail.value, got)
    ElMessage.success(`「${c.display}」的座次表已上传`)
  } finally {
    seatBusy.value = 0
  }
}

async function openSeat(c) {
  if (c.seat_kind === 'image') {
    window.open(c.seat_url, '_blank', 'noopener')
  } else {
    await download(api.classSeatFile(c.id), c.seat_name || `${c.display}座次表.xlsx`)
  }
}

async function removeSeat(c) {
  await ElMessageBox.confirm(`删掉「${c.display}」的座次表？`, '提示', { type: 'warning' })
  const got = await api.classSeatDelete(c.id)
  Object.assign(c, got)
  if (detail.value?.id === c.id) Object.assign(detail.value, got)
  ElMessage.success('已删除')
}

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
  panelFolded.value = false
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

// ---------- 班干部 ----------
const monitor = computed(() => detailRows.value.find(s => s.class_role === '班长'))
const leaders = computed(() => detailRows.value.filter(s => s.class_role === '组长'))

/** 设班长 / 组长。一个班一位班长，换人时后端把原来那位卸任，所以设完整班重拉一遍。 */
async function setRole(row, role) {
  if ((row.class_role || '') === role) return
  await api.studentUpdate(row.id, { class_role: role })
  detailRows.value = await api.students({ class_id: detail.value.id })
  ElMessage.success(role ? `已设 ${row.name} 为${role}` : `已取消 ${row.name} 的班干部`)
}

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
      老师名下一个班都没有时，发不出考试。点班级卡片任意空白处打开这个班的在线座次。
    </el-alert>
    <el-alert v-else type="info" :closable="false">
      这里显示全校班级，<b>带「我的班」标记的是你带的班</b>。发考试时只能选这些班。
      点班级卡片任意空白处打开这个班的在线座次；班级的增删改和分配由管理员操作。
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

  <!-- 座次表上传用的隐藏文件框，所有班共用一个 -->
  <input ref="seatInput" type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.bmp,.xls,.xlsx" hidden @change="onSeatFile" />

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
        <!-- 整张卡片可点（空白处、班名、人数），打开在线座次；勾选框、下拉、按钮各管各的 -->
        <article
          v-for="c in g.list"
          :key="c.id"
          class="cls"
          :class="{ mine: c.owner_id === currentUser?.id, orphan: !c.owner_id, on: isPicked(c.id) }"
          :title="`点击打开 ${c.display} 的在线座次`"
          @click="onCardClick($event, c)"
        >
          <div class="top">
            <el-checkbox
              v-if="isAdmin"
              :model-value="isPicked(c.id)"
              @change="togglePick(c.id, $event)"
            />
            <span class="cname">{{ c.name }}</span>
            <el-tag v-if="c.owner_id === currentUser?.id" size="small" type="success" effect="light">
              我的班
            </el-tag>
          </div>

          <span class="stu">{{ c.student_count }} 名学生</span>

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

          <div class="seat" v-loading="seatBusy === c.id">
            <span class="seatlbl">座次表</span>
            <template v-if="c.seat_kind">
              <el-button link size="small" type="primary" :title="c.seat_name" @click="openSeat(c)">
                {{ c.seat_kind === 'image' ? '🖼 看图片' : '📊 下载' }}
              </el-button>
              <el-button v-if="canSeat(c)" link size="small" @click="pickSeat(c)">更换</el-button>
              <el-button v-if="canSeat(c)" link size="small" type="danger" @click="removeSeat(c)">删</el-button>
            </template>
            <template v-else>
              <el-button v-if="canSeat(c)" link size="small" type="primary" @click="pickSeat(c)">上传</el-button>
              <span v-else class="muted">未上传</span>
            </template>
          </div>

          <div v-if="isAdmin" class="acts">
            <el-button link size="small" type="primary" @click="openEdit(c)">改名</el-button>
            <el-button link size="small" type="danger" @click="remove(c)">删除</el-button>
          </div>
        </article>
      </div>
    </div>
  </el-card>

  <!-- 班级在线座次（点卡片打开）：可浮动、可折叠的面板，主要区域给「在线座次」（2.20.0）。
       名单列表挪走了：人在「学生管理」里管，班长 / 组长也在那儿设 -->
  <teleport to="body">
    <section v-if="detail" v-show="!panelFolded" class="seatpanel" :class="{ full: panelFull }">
      <header class="phead">
        <b class="ptitle">{{ detail.display }} · 在线座次</b>
        <span class="pmeta">
          班主任 <b>{{ detail.owner_name || '未分配' }}</b>　学生 <b>{{ detailStats.total }}</b> 人
          （男 {{ detailStats.male }} · 女 {{ detailStats.female }}<template v-if="detailStats.unknown"> · 未填 {{ detailStats.unknown }}</template>）
          <template v-if="monitor">　班长 <b>{{ monitor.name }}</b></template>
          <template v-if="leaders.length">　组长 <b>{{ leaders.map(s => s.name).join('、') }}</b></template>
        </span>
        <div class="flex-1" />
        <template v-if="detail.seat_kind">
          <el-button link size="small" type="primary" @click="openSeat(detail)">
            {{ detail.seat_kind === 'image' ? '看原来上传的图片' : '下载原来上传的表格' }}
          </el-button>
        </template>
        <el-button v-if="canSeat(detail)" link size="small" @click="pickSeat(detail)">
          {{ detail.seat_kind ? '更换上传的座次表' : '上传座次表文件' }}
        </el-button>
        <el-button size="small" @click="panelFull = !panelFull">{{ panelFull ? '还原大小' : '全屏' }}</el-button>
        <el-button size="small" type="danger" plain @click="closeDetail">关闭</el-button>
      </header>
      <SeatSheet ref="seatSheet" :key="detail.id" :cls="detail" :wide="panelFull" @saved="onSeatSaved" @roles="reloadRoster">
        <template #side>
          <ClassLogs
            ref="classLogs"
            :key="detail.id"
            :cls="detail"
            :can-edit="canSeat(detail)"
            :students="detailRows.filter(s => s.is_active)"
          />
        </template>
      </SeatSheet>
    </section>
    <button v-if="detail && panelFolded" type="button" class="seatpill" @click="panelFolded = false">
      ▲ {{ detail.display }} 在线座次（点开）
    </button>
  </teleport>

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
.seatpanel {
  position: fixed;
  top: 64px;
  right: 16px;
  bottom: 16px;
  width: min(1100px, calc(100vw - 32px));
  z-index: 1900;
  display: flex;
  flex-direction: column;
  padding: 10px 14px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  overflow: hidden;
}
/* 「全屏」= 放大成居中的大浮窗，四周留边、不贴满屏幕；高度跟窗口走，
   里面的表格自己量剩下的空间（SeatSheet 的 ResizeObserver），不会撑出窗外 */
.seatpanel.full {
  top: 4vh;
  bottom: 4vh;
  left: 50%;
  right: auto;
  transform: translateX(-50%);
  width: min(1600px, 92vw);
}
.phead {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.phead :deep(.el-button + .el-button) {
  margin-left: 0;
}
.ptitle {
  font-size: 15px;
}
.pmeta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.flex-1 {
  flex: 1;
}
.seatpill {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 1900;
  padding: 10px 16px;
  border: none;
  border-radius: 20px;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
}
.seat {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 6px;
  font-size: 12px;
}
.seatlbl {
  color: var(--el-text-color-secondary);
  margin-right: 6px;
}
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
/* 年级之间：每个年级一块浅底色区域 + 年级名左侧色条，两块之间再隔一条粗分界线，一眼分得开 */
.gradeblock {
  padding: 14px 16px 18px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}
.gradeblock + .gradeblock {
  margin-top: 26px;
  position: relative;
}
.gradeblock + .gradeblock::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: -14px;
  border-top: 2px dashed var(--el-border-color-darker);
}
.gname {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 14px;
  padding-left: 10px;
  border-left: 4px solid var(--el-color-primary);
  line-height: 1.3;
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
  border: 1.5px solid var(--el-border-color);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--el-bg-color);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cls:hover {
  border-color: var(--el-color-primary-light-3);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1);
}
.cls :deep(.el-select),
.cls :deep(.el-checkbox) {
  cursor: default;
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
  font-size: 17px;
  font-weight: 700;
}
.cls:hover .cname {
  color: var(--el-color-primary);
}
.stu {
  font-size: 12px;
  color: var(--el-text-color-secondary);
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

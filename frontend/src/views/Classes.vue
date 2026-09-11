<script setup>
/**
 * 班级管理（管理员）。
 *
 * 班级归属决定谁能给谁发考试：老师只能给自己名下的班发，管理员发的
 * 全体学生都收得到。所以「把班分给谁」是这一页最要紧的操作。
 *
 * 老师也能打开这一页，但只能看 —— 发考试要选班，得知道有哪些班。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { currentUser } from '../auth'

const rows = ref([])
const teachers = ref([])
const loading = ref(false)

const isAdmin = computed(() => currentUser.value?.role === 'admin')

const dialog = ref(false)
const editing = ref(null)
const form = reactive({ grade: '', name: '', owner_id: null })

const batchDlg = ref(false)
const batch = reactive({ grade: '', start: 1, end: 12, suffix: '班' })

async function load() {
  loading.value = true
  try {
    rows.value = await api.classes({ include_inactive: true })
    if (isAdmin.value) teachers.value = await api.listUsers()
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
  await load()
  ElMessage.success(
    res.detached ? `已删除，${res.detached} 名学生变成未分班` : '已删除'
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
      老师名下一个班都没有时，发不出考试。
    </el-alert>
    <el-alert v-else type="info" :closable="false">
      这里显示全校班级，<b>带「我的班」标记的是你带的班</b>。发考试时只能选这些班。
      班级的增删改和分配由管理员操作。
    </el-alert>

    <div v-if="isAdmin && noOwner" class="warn">
      还有 <b>{{ noOwner }}</b> 个班没有分配老师，这些班的学生只能收到管理员发的考试。
    </div>
  </el-card>

  <el-card v-loading="loading" shadow="never">
    <el-empty v-if="!rows.length && !loading" description="还没有班级，先用「按年级批量建班」建一批" :image-size="80" />

    <div v-for="g in grouped" :key="g.grade" class="gradeblock">
      <h3 class="gname">{{ g.grade }}<span class="gcount">{{ g.list.length }} 个班</span></h3>
      <div class="grid">
        <article
          v-for="c in g.list"
          :key="c.id"
          class="cls"
          :class="{ mine: c.owner_id === currentUser?.id, orphan: !c.owner_id }"
        >
          <div class="top">
            <span class="cname">{{ c.name }}</span>
            <el-tag v-if="c.owner_id === currentUser?.id" size="small" type="success" effect="light">
              我的班
            </el-tag>
          </div>

          <div class="stu">{{ c.student_count }} 名学生</div>

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

.gradeblock {
  margin-bottom: 24px;
}
.gname {
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
.top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cname {
  font-size: 15px;
  font-weight: 600;
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
</style>

<script setup>
/**
 * 在线座次：小组设置。小组跟着学生走（存的是「哪位学生在哪个组」），拖着换座位，颜色跟着人走。
 * 每组一个淡色底色；组名、颜色能改，能整块框选一片座位一次分组。保存座次表时一起存。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { GROUP_COLORS } from './seatBoard'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  groups: { type: Array, required: true },          // [{ id, name, color }]（直接改这个数组）
  groupOf: { type: Object, required: true },        // { 学生 id: 组 id }（直接改）
  students: { type: Array, default: () => [] },
  selection: { type: String, default: '' },         // 表格上框选的区域，如 B3:D8
  selectedStudents: { type: Function, required: true } // () => 框选区域里的学生
})
const emit = defineEmits(['update:modelValue', 'changed'])

const target = ref('')
const members = gid => props.students.filter(s => String(props.groupOf[s.id] || '') === String(gid))
const ungrouped = computed(() => props.students.filter(s => !props.groupOf[s.id]).length)

function nextId() {
  return String(Math.max(0, ...props.groups.map(g => Number(g.id) || 0)) + 1)
}

function addGroup() {
  const i = props.groups.length
  props.groups.push({ id: nextId(), name: `第${i + 1}组`, color: GROUP_COLORS[i % GROUP_COLORS.length] })
  emit('changed')
}

function quickCreate(n) {
  for (let i = props.groups.length; i < n; i++) addGroup()
}

async function removeGroup(g) {
  const n = members(g.id).length
  if (n) await ElMessageBox.confirm(`「${g.name}」里有 ${n} 位同学，删掉小组后他们变成不分组。`, '删除小组', { type: 'warning' })
  props.groups.splice(props.groups.indexOf(g), 1)
  Object.keys(props.groupOf).forEach(k => String(props.groupOf[k]) === String(g.id) && delete props.groupOf[k])
  emit('changed')
}

function assignSelection() {
  if (!props.selection) return ElMessage.info('先关掉这个框，在表格上框选一片座位，再打开「小组」')
  const list = props.selectedStudents()
  if (!list.length) return ElMessage.info(`选中的 ${props.selection} 里没有认得出的学生`)
  list.forEach(s => {
    if (target.value) props.groupOf[s.id] = target.value
    else delete props.groupOf[s.id]
  })
  emit('changed')
  const g = props.groups.find(x => x.id === target.value)
  ElMessage.success(`${list.length} 位同学${g ? `分到「${g.name}」` : '取消了分组'}`)
}

async function clearAll() {
  await ElMessageBox.confirm('所有同学都变成不分组（小组本身留着）？', '清空分组', { type: 'warning' })
  Object.keys(props.groupOf).forEach(k => delete props.groupOf[k])
  emit('changed')
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="小组"
    width="560px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p class="tip">
      小组跟着学生走：拖着换座位，底色跟着人一起走。右键学生也能单独分组。改完记得点座次表的「保存」。
    </p>

    <div v-if="!groups.length" class="empty">
      还没有小组。
      <el-button size="small" type="primary" @click="quickCreate(4)">一下建 4 个组</el-button>
      <el-button size="small" @click="quickCreate(6)">建 6 个</el-button>
    </div>

    <div v-for="g in groups" :key="g.id" class="grow" :style="{ background: g.color }">
      <el-color-picker
        v-model="g.color"
        size="small"
        :predefine="GROUP_COLORS"
        @change="emit('changed')"
      />
      <el-input v-model="g.name" size="small" maxlength="12" style="width: 120px" @change="emit('changed')" />
      <span class="names">
        <b>{{ members(g.id).length }}</b> 人
        <template v-if="members(g.id).length">：{{ members(g.id).map(s => s.name).join('、') }}</template>
      </span>
      <el-button link size="small" type="danger" @click="removeGroup(g)">删</el-button>
    </div>
    <div v-if="groups.length" class="bar">
      <el-button size="small" @click="addGroup">+ 加一个组</el-button>
      <span class="muted">没分组的 {{ ungrouped }} 人</span>
      <div class="flex-1" />
      <el-button size="small" link type="danger" @click="clearAll">清空分组</el-button>
    </div>

    <el-divider />
    <div class="bar">
      <span>把表格上选中的 <b>{{ selection || '（先框选）' }}</b> 里的学生分到</span>
      <el-select v-model="target" size="small" style="width: 120px" placeholder="选组">
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        <el-option label="不分组" value="" />
      </el-select>
      <el-button size="small" type="primary" @click="assignSelection">分过去</el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.tip {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.empty {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.grow {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 6px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  color: #303133;
}
.names {
  flex: 1;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}
.flex-1 {
  flex: 1;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>

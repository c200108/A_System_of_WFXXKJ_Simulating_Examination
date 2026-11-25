<script setup>
/**
 * 发布考试选班级（2.28.0）：按年级分行，年级名前一个勾 = 一键全选 / 全不选这个年级，
 * 后面是这个年级的各个班，点一下选上 / 取消。一屏看得清哪些年级、哪些班选了。
 *
 * v-model：选中的班级 id 数组。classes：[{ id, grade, name, display }]。
 */
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  classes: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue'])

const picked = computed(() => new Set(props.modelValue))
const grades = computed(() => {
  const map = new Map()
  for (const c of props.classes) {
    const g = c.grade || '其他'
    if (!map.has(g)) map.set(g, [])
    map.get(g).push(c)
  }
  // 班号按数字排：2 班在 10 班前面
  return [...map.entries()].map(([grade, list]) => ({
    grade,
    list: list.slice().sort((a, b) => String(a.name).localeCompare(String(b.name), 'zh-CN', { numeric: true }))
  }))
})

function set(ids) {
  emit('update:modelValue', [...new Set(ids)])
}
function toggle(id) {
  const s = new Set(props.modelValue)
  s.has(id) ? s.delete(id) : s.add(id)
  set([...s])
}
const allOf = g => g.list.length > 0 && g.list.every(c => picked.value.has(c.id))
const someOf = g => g.list.some(c => picked.value.has(c.id)) && !allOf(g)
function toggleGrade(g, on) {
  const ids = g.list.map(c => c.id)
  set(on ? [...props.modelValue, ...ids] : props.modelValue.filter(id => !ids.includes(id)))
}
</script>

<template>
  <div class="cp">
    <div v-for="g in grades" :key="g.grade" class="row">
      <el-checkbox
        class="gr"
        :model-value="allOf(g)"
        :indeterminate="someOf(g)"
        @change="v => toggleGrade(g, v)"
      >
        <b>{{ g.grade }}</b>
      </el-checkbox>
      <div class="chips">
        <button
          v-for="c in g.list"
          :key="c.id"
          type="button"
          class="chip"
          :class="{ on: picked.has(c.id) }"
          @click="toggle(c.id)"
        >
          {{ c.name }}
        </button>
      </div>
    </div>
    <div v-if="!grades.length" class="none">还没有能选的班级</div>
    <div v-if="modelValue.length" class="sum">
      已选 {{ modelValue.length }} 个班
      <el-button link size="small" type="primary" @click="set([])">清空</el-button>
    </div>
  </div>
</template>

<style scoped>
.cp {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 6px 10px;
  max-height: 260px;
  overflow-y: auto;
}
.row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 5px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.row:last-of-type {
  border-bottom: none;
}
.gr {
  flex: none;
  width: 92px;
  height: 26px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.chip {
  padding: 1px 10px;
  height: 24px;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  background: var(--el-bg-color);
  color: var(--el-text-color-regular);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
}
.chip:hover {
  border-color: var(--el-color-primary-light-5);
}
.chip.on {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}
.none,
.sum {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-top: 4px;
}
</style>

<script setup>
/**
 * 在线座次：右键学生格子弹出的菜单（加分 / 减分 / 班干部 / 小组 / 移走）。
 * 只有本班老师和管理员会看到；右键空格子、讲台这些还是表格本来的菜单（插入删除行列）。
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  student: { type: Object, default: null },
  total: { type: Number, default: 0 },
  groups: { type: Array, default: () => [] },
  groupId: { type: [String, Number], default: '' }
})
const emit = defineEmits(['close', 'points', 'custom', 'history', 'role', 'group', 'remove'])

const box = ref(null)
const pos = ref({ left: 0, top: 0 })
const sub = ref(false)

// 贴着鼠标开；靠近屏幕右边 / 下边时往回收，别跑出窗口
watch(
  () => [props.open, props.x, props.y],
  async () => {
    sub.value = false
    if (!props.open) return
    pos.value = { left: props.x, top: props.y }
    await nextTick()
    const r = box.value?.getBoundingClientRect()
    if (!r) return
    pos.value = {
      left: Math.max(4, Math.min(props.x, window.innerWidth - r.width - 8)),
      top: Math.max(4, Math.min(props.y, window.innerHeight - r.height - 8))
    }
  }
)

function outside(e) {
  if (props.open && box.value && !box.value.contains(e.target)) emit('close')
}
function esc(e) {
  if (props.open && e.key === 'Escape') emit('close')
}
window.addEventListener('mousedown', outside, true)
window.addEventListener('keydown', esc)
window.addEventListener('scroll', outside, true)
onBeforeUnmount(() => {
  window.removeEventListener('mousedown', outside, true)
  window.removeEventListener('keydown', esc)
  window.removeEventListener('scroll', outside, true)
})

const act = (name, ...args) => {
  emit(name, ...args)
  emit('close')
}
</script>

<template>
  <teleport to="body">
    <div
      v-if="open && student"
      ref="box"
      class="seatmenu"
      :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
      @contextmenu.prevent
    >
      <div class="mhead">
        <b>{{ student.name }}</b>
        <span class="muted">{{ student.student_no }}</span>
        <span v-if="student.class_role" class="role">{{ student.class_role }}</span>
        <span class="pts" :class="{ neg: total < 0 }">{{ total > 0 ? '+' : '' }}{{ total }} 分</span>
      </div>
      <div class="mrow">
        <button type="button" class="chip plus" @click="act('points', 1)">+1</button>
        <button type="button" class="chip plus" @click="act('points', 2)">+2</button>
        <button type="button" class="chip plus" @click="act('points', 5)">+5</button>
        <button type="button" class="chip minus" @click="act('points', -1)">−1</button>
        <button type="button" class="chip minus" @click="act('points', -2)">−2</button>
      </div>
      <button type="button" class="item" @click="act('custom')">✎ 自定义加减分（写原因）…</button>
      <button type="button" class="item" @click="act('history')">🧾 得分记录 / 撤销</button>
      <div class="sep" />
      <button type="button" class="item" :disabled="student.class_role === '班长'" @click="act('role', '班长')">
        👑 设为班长
      </button>
      <button type="button" class="item" :disabled="student.class_role === '组长'" @click="act('role', '组长')">
        ⭐ 设为组长
      </button>
      <button v-if="student.class_role" type="button" class="item" @click="act('role', '')">取消{{ student.class_role }}</button>
      <div class="sep" />
      <div class="item has-sub" @mouseenter="sub = true" @mouseleave="sub = false" @click="sub = !sub">
        🎨 分到小组 <span class="arrow">›</span>
        <div v-if="sub" class="submenu">
          <button
            v-for="g in groups"
            :key="g.id"
            type="button"
            class="item"
            :class="{ cur: String(g.id) === String(groupId) }"
            @click.stop="act('group', g.id)"
          >
            <i class="dot" :style="{ background: g.color }" />{{ g.name }}
          </button>
          <button type="button" class="item" :class="{ cur: !groupId }" @click.stop="act('group', '')">不分组</button>
          <button type="button" class="item muted" @click.stop="act('group', '__manage')">管理小组…</button>
        </div>
      </div>
      <div class="sep" />
      <button type="button" class="item danger" @click="act('remove')">从这个座位移走</button>
    </div>
  </teleport>
</template>

<style scoped>
.seatmenu {
  position: fixed;
  z-index: 3000;
  min-width: 210px;
  padding: 6px;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
  font-size: 13px;
  user-select: none;
}
.mhead {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 4px 8px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 6px;
}
.mhead b {
  font-size: 15px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.role {
  font-size: 11px;
  padding: 0 5px;
  border-radius: 6px;
  background: #e6a23c;
  color: #fff;
}
.pts {
  margin-left: auto;
  font-weight: 700;
  color: #529b2e;
}
.pts.neg {
  color: #c45656;
}
.mrow {
  display: flex;
  gap: 4px;
  padding: 0 4px 6px;
}
.chip {
  flex: 1;
  padding: 4px 0;
  border: none;
  border-radius: 6px;
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
}
.chip.plus {
  background: #e1f3d8;
  color: #3e7d1f;
}
.chip.minus {
  background: #fde2e2;
  color: #b23a3a;
}
.chip:hover {
  filter: brightness(0.95);
}
.item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: none;
  border-radius: 6px;
  font: inherit;
  color: var(--el-text-color-regular);
  text-align: left;
  cursor: pointer;
}
.item:hover:not(:disabled) {
  background: var(--el-fill-color-light);
}
.item:disabled {
  color: var(--el-text-color-placeholder);
  cursor: default;
}
.item.danger {
  color: var(--el-color-danger);
}
.item.cur {
  font-weight: 700;
  color: var(--el-color-primary);
}
.arrow {
  margin-left: auto;
}
.sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--el-border-color-lighter);
}
.submenu {
  position: absolute;
  left: 100%;
  top: -6px;
  min-width: 150px;
  padding: 6px;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
}
.dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.12);
}
</style>

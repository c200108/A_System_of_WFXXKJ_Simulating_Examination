<script setup>
/**
 * 客观题怎么作答（2.27.0）：单选、多选、判断、填空，三个答题页共用
 * （/take 公开链接、学生平台答题页、教师组卷页的在线自测）。
 *
 * 交上去的值（v-model）：
 *   单选 / 判断  —— 原选项字母 'B'
 *   多选         —— 勾中的原选项字母按字母序连起来 'ABD'（乱序时屏幕上显示的是新字母 o.show，
 *                   交的仍是原字母 o.label，判分不受影响）
 *   填空         —— 一个空：直接是那段文字；几个空：JSON 数组 '["数据","特征库"]'
 *                   全都没填交空串，「已作答」才数得对
 * 题目的形状来自服务端：q.multi 多选、q.blanks 几个空（只有个数，不是答案）。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps({
  q: { type: Object, required: true },
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const isBlank = computed(() => props.q.type === '填空题')
const multi = computed(() => !!props.q.multi)
const blankCount = computed(() => Math.max(1, Number(props.q.blanks) || 1))

// 多选勾中的字母：本地留一份，连着勾两个（父组件还没传回新值）也不会丢
const toSet = v => new Set(String(v || '').toUpperCase().split('').filter(Boolean))
const picked = ref(toSet(props.modelValue))
let lastPicked = props.modelValue

function pickOne(label) {
  if (!props.disabled) emit('update:modelValue', label)
}
function toggle(label) {
  if (props.disabled) return
  const s = new Set(picked.value)
  s.has(label) ? s.delete(label) : s.add(label)
  picked.value = s
  lastPicked = [...s].sort().join('')
  emit('update:modelValue', lastPicked)
}

/** 填空：每个空的内容。本地留一份，连着改两个空（父组件还没把新值传回来）也不会互相覆盖 */
function parseBlanks(raw) {
  raw = String(raw || '')
  if (blankCount.value === 1) return [raw]
  try {
    const got = JSON.parse(raw)
    if (Array.isArray(got)) return Array.from({ length: blankCount.value }, (_, i) => String(got[i] ?? ''))
  } catch {
    /* 不是数组：当成第一空 */
  }
  return Array.from({ length: blankCount.value }, (_, i) => (i === 0 ? raw : ''))
}
const blanks = ref(parseBlanks(props.modelValue))
let lastSent = props.modelValue
watch(
  () => props.modelValue,
  v => {
    // 外面改的（比如「重新作答」清空）才同步进来
    if (v !== lastSent) blanks.value = parseBlanks(v)
    if (v !== lastPicked) picked.value = toSet(v)
  }
)
function setBlank(i, v) {
  const next = blanks.value.slice()
  next[i] = v
  blanks.value = next
  lastSent = blankCount.value === 1 ? v : next.some(x => x.trim()) ? JSON.stringify(next) : ''
  emit('update:modelValue', lastSent)
}
const CN = '一二三四五六七八九十'
</script>

<template>
  <div class="oa">
    <!-- 填空题：一个空一个输入框 -->
    <template v-if="isBlank">
      <div v-for="(v, i) in blanks" :key="i" class="blank">
        <span class="bl">{{ blankCount > 1 ? `第${CN[i] || i + 1}空` : '答案' }}</span>
        <el-input
          :model-value="v"
          :disabled="disabled"
          maxlength="200"
          placeholder="在这里填写"
          @update:model-value="setBlank(i, $event)"
        />
      </div>
    </template>

    <!-- 多选题：复选框，可以选好几个 -->
    <template v-else-if="multi">
      <div class="mtip">多选题：有两个或两个以上正确选项，多选、错选、漏选均不得分</div>
      <label
        v-for="o in q.options"
        :key="o.label"
        class="op"
        :class="{ picked: picked.has(o.label), disabled }"
      >
        <input type="checkbox" :disabled="disabled" :checked="picked.has(o.label)" @change="toggle(o.label)" />
        <span class="L">{{ o.show || o.label }}</span><span>{{ o.content }}</span>
      </label>
    </template>

    <!-- 单选、判断 -->
    <template v-else>
      <label
        v-for="o in q.options"
        :key="o.label"
        class="op"
        :class="{ picked: modelValue === o.label, disabled }"
      >
        <input
          type="radio"
          :name="'q' + q.id"
          :value="o.label"
          :disabled="disabled"
          :checked="modelValue === o.label"
          @change="pickOne(o.label)"
        />
        <!-- 乱序时显示新位置的字母（o.show），交的仍是原字母（o.label） -->
        <span class="L">{{ o.show || o.label }}</span><span>{{ o.content }}</span>
      </label>
    </template>
  </div>
</template>

<style scoped>
label.op {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  padding: 6px 9px;
  border-radius: 7px;
  border: 1px solid transparent;
  cursor: pointer;
}
label.op:hover {
  background: var(--el-fill-color-light);
}
label.op.picked {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
label.op.disabled {
  cursor: default;
}
.L {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  min-width: 18px;
}
.mtip {
  margin: 2px 0 6px;
  font-size: 12.5px;
  color: var(--el-color-warning-dark-2, #b88230);
}
.blank {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 6px 0;
}
.bl {
  flex: none;
  min-width: 48px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>

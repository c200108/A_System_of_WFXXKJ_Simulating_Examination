<script setup>
/**
 * 长文字只露两行，多出来的藏起来，末尾「…」后面跟一个「展开」；展开后变「收起」。
 *
 * 题库列表里题干、选项、答案都可能很长（真题里有三四百字的题干），整段铺开
 * 一页只剩三五道题。放不满两行的根本不显示「展开」—— 量的是渲染出来的高度，
 * 不是字数，所以中英文、列宽变化都准。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  text: { type: [String, Number], default: '' },
  lines: { type: Number, default: 2 }
})

const box = ref(null)
const open = ref(false)
const overflow = ref(false)

function measure() {
  const el = box.value
  if (!el || open.value) return
  overflow.value = el.scrollHeight > el.clientHeight + 1
}

let watcher = null
onMounted(() => {
  nextTick(measure)
  // 拖列宽、窗口缩放之后重新量：原来两行放得下的，窄了可能就放不下了
  if (window.ResizeObserver && box.value) {
    watcher = new ResizeObserver(measure)
    watcher.observe(box.value)
  }
})
onBeforeUnmount(() => watcher && watcher.disconnect())
watch(
  () => props.text,
  () => {
    open.value = false
    nextTick(measure)
  }
)

function toggle() {
  open.value = !open.value
  if (!open.value) nextTick(measure)
}
</script>

<template>
  <div class="clamp">
    <div ref="box" class="txt" :class="{ shut: !open }" :style="{ '-webkit-line-clamp': open ? 'none' : lines }">
      <slot>{{ text }}</slot>
    </div>
    <a v-if="overflow || open" class="more" @click.stop="toggle">{{ open ? '收起' : '展开' }}</a>
  </div>
</template>

<style scoped>
.clamp {
  display: flex;
  align-items: flex-end;
  gap: 4px;
}
.txt {
  flex: 1;
  min-width: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.txt.shut {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.more {
  flex: none;
  color: var(--el-color-primary);
  font-size: 12px;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.more:hover {
  text-decoration: underline;
}
</style>

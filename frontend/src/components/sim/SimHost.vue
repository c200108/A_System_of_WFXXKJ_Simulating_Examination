<script setup>
/**
 * 仿真题的外壳：按题型挑一个仿真器，收着学生的终态和操作日志。
 *
 * 学生的作答就是一段 JSON：{ state: 终态, log: [操作...] }，当成这道题的答案
 * 交上去。判分只看 state（服务端按检查点断言），log 只用于事后回放和申诉 ——
 * 按"点了哪几下"判分会把用了别的正确路径的学生判错。
 */
import { computed, ref, watch } from 'vue'
import SimWindows from './SimWindows.vue'
import SimWps from './SimWps.vue'
import SimHtml from './SimHtml.vue'

const props = defineProps({
  /** { kind, title, env } —— 服务端下发的那一份，不含检查点 */
  sim: { type: Object, required: true },
  /** 学生这道题的作答字符串（接着做时回填） */
  modelValue: { type: String, default: '' },
  readonly: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const KIND_NAMES = { win: 'Windows 操作', wps: 'WPS 文字', html: '网页编程' }
const COMPONENTS = { win: SimWindows, wps: SimWps, html: SimHtml }

const state = ref(null)
const log = ref([])

function boot() {
  try {
    const got = JSON.parse(props.modelValue || 'null')
    state.value = got && got.state ? got.state : null
    log.value = got && Array.isArray(got.log) ? got.log : []
  } catch {
    state.value = null
    log.value = []
  }
}
boot()
watch(() => props.sim, boot)

const comp = computed(() => COMPONENTS[props.sim?.kind] || null)
const touched = computed(() => state.value !== null)

function onState(next) {
  state.value = next
  emit('update:modelValue', JSON.stringify({ state: next, log: log.value.slice(-200) }))
}

function onLog(entry) {
  // 只留最近 200 步。日志是给回放用的，不该把答案包撑大
  log.value = [...log.value, entry].slice(-200)
  // 仿真器是先发状态再发日志的，这里补发一次，否则交上去的包里
  // 永远少最后一步的日志
  if (state.value !== null) {
    emit('update:modelValue', JSON.stringify({ state: state.value, log: log.value }))
  }
}

function reset() {
  state.value = null
  log.value = []
  emit('update:modelValue', '')
  // 换个 key 让子组件整个重建，回到初始环境
  seed.value++
}
const seed = ref(0)
</script>

<template>
  <div class="host">
    <div class="head">
      <span class="badge">{{ KIND_NAMES[sim.kind] || '操作' }}</span>
      <span class="title">{{ sim.title }}</span>
      <span class="grow" />
      <span v-if="touched" class="saved">已记录你的操作</span>
      <span v-else class="hint">按题目要求操作，系统自动记录结果</span>
      <button v-if="!readonly" class="reset" @click="reset">重来</button>
    </div>

    <component
      :is="comp"
      v-if="comp"
      :key="seed"
      :env="sim.env || {}"
      :model-value="state"
      :readonly="readonly"
      @update:model-value="onState"
      @log="onLog"
    />
    <p v-else class="bad">这道题的仿真环境读不出来（题型：{{ sim.kind }}），请找老师。</p>
  </div>
</template>

<style scoped>
.host { display: flex; flex-direction: column; gap: 8px; }
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
}
.badge {
  background: var(--el-color-primary-light-9, #eaf2ff);
  color: var(--el-color-primary, #2c6fd1);
  border: 1px solid var(--el-color-primary-light-7, #b9d4ff);
  border-radius: 10px;
  padding: 1px 10px;
  font-size: 12px;
}
.title { font-weight: 600; }
.grow { flex: 1; }
.hint, .saved { font-size: 12px; color: var(--el-text-color-secondary, #6b7480); }
.saved { color: #1a7f37; }
.reset {
  border: 1px solid var(--el-border-color, #ccd4e0);
  background: var(--el-bg-color, #fff);
  color: inherit;
  border-radius: 4px;
  padding: 2px 10px;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}
.bad { color: #b3261e; }
</style>

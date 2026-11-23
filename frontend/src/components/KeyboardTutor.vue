<script setup>
/**
 * 打字入门（原「认识键盘」，2.25.3）：/dazi 和学生平台的打字页共用。
 *
 * 给零基础的学生练指法，几样帮他们少走弯路的东西：
 * - 开始前：键盘图按「哪根手指管哪些键」上色，F、J 标出凸点，文字讲清楚八个手指放哪、大拇指放空格；
 * - 练的时候：一次只亮一个键，旁边写「用 左手无名指 按 S」；按对了才往下走，按错了那个键闪红，
 *   不跳过 —— 先求准；拼音短句课在汉字上方标拼音，打到哪个字母就点亮哪个；
 * - 可以关掉键盘图「盲打」：键位熟了就别看图，逼自己凭手指位置找键；
 * - 练完：列出最常按错的键和该用的手指，告诉他下一步练哪一课。
 *
 * 课程和原文由服务端出（services/keyboard_lessons.py），这里只管显示和按键；
 * 交上去的是「按过的键依次排成的串」，正确率由服务端按原文算。
 */
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

const props = defineProps({
  running: { type: Boolean, default: false },
  lessons: { type: Array, default: () => [] },
  lesson: { type: String, default: 'home' }
})
const emit = defineEmits(['done'])

const ROWS = [
  ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='],
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']', '\\'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', "'"],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/'],
  [' ']
]
const OFFSET = [0, 0.5, 0.8, 1.3, 3.6] // 每排往右错开多少个键宽，和真键盘一样斜着排

// 哪根手指管哪个键（标准指法）
const FINGER_KEYS = {
  lp: '`1qaz-', lr: '2wsx', lm: '3edc', li: '45rtfgvb',
  ri: '67yuhjnm', rm: '8ik,', rr: '9ol.', rp: "0-=p[]\\;'/", th: ' '
}
const FINGER_NAME = {
  lp: '左手小指', lr: '左手无名指', lm: '左手中指', li: '左手食指',
  ri: '右手食指', rm: '右手中指', rr: '右手无名指', rp: '右手小指', th: '大拇指'
}
const fingerOf = {}
for (const [f, ks] of Object.entries(FINGER_KEYS)) for (const k of ks) if (!fingerOf[k]) fingerOf[k] = f
const HOME = 'asdfjkl;'
const label = k => (k === ' ' ? '空格' : k.toUpperCase())

const units = ref([])
const target = ref('')
const st = reactive({ pos: 0, total: 0, correct: 0, keys: '', wrong: '', started: 0 })
const errors = reactive({}) // { 应按的键: 按错次数 }
const blind = ref(false)
let wrongTimer = null

const next = computed(() => target.value[st.pos] ?? '')
const progress = computed(() => (target.value ? Math.round((st.pos / target.value.length) * 100) : 0))
const lessonInfo = computed(() => props.lessons.find(l => l.id === props.lesson) || null)
const weak = computed(() =>
  Object.entries(errors)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([k, n]) => ({ k, n, finger: FINGER_NAME[fingerOf[k]] || '' }))
)

// 拼音 / 指法组：每个 unit 里每个字母在原文里的位置，拿来点亮当前字母
const shown = computed(() => {
  let at = 0
  return units.value.map(u => {
    const start = at
    at += u.keys.length
    return { ...u, start, end: at }
  })
})

function load(newUnits, text) {
  units.value = newUnits || []
  target.value = text || ''
  st.pos = st.total = st.correct = 0
  st.keys = ''
  st.wrong = ''
  st.started = Date.now()
  for (const k of Object.keys(errors)) delete errors[k]
}

function onKeydown(e) {
  if (!props.running || !target.value) return
  if (e.ctrlKey || e.metaKey || e.altKey) return
  const k = e.key === ' ' || e.code === 'Space' ? ' ' : e.key.length === 1 ? e.key.toLowerCase() : ''
  if (!k) return // Shift、退格这些不算一次按键
  e.preventDefault()
  st.total++
  st.keys += k
  if (k === next.value) {
    st.correct++
    st.pos++
    if (st.pos >= target.value.length) emit('done')
  } else {
    errors[next.value] = (errors[next.value] || 0) + 1
    st.wrong = k
    clearTimeout(wrongTimer)
    wrongTimer = setTimeout(() => (st.wrong = ''), 260)
  }
}

function keyCls(k) {
  const cls = ['f-' + (fingerOf[k] || 'lp')]
  if (k === ' ') cls.push('space')
  if (props.running && k === next.value) cls.push('next')
  if (props.running && st.wrong && k === st.wrong) cls.push('bad')
  if (HOME.includes(k)) cls.push('home')
  return cls
}

const kpm = computed(() => {
  const mins = (Date.now() - st.started) / 60000
  return mins > 0 && st.correct ? Math.round(st.correct / mins) : 0
})

defineExpose({ load, st, kpm })

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(wrongTimer)
})
</script>

<template>
  <div class="tutor">
    <!-- 开始之前：手指放哪 -->
    <div v-if="!running && !target" class="intro">
      <h4>开始之前：先把手指放好</h4>
      <ol>
        <li>左手食指放在 <b>F</b>、右手食指放在 <b>J</b> —— 这两个键上有小凸起，不看键盘也摸得到。</li>
        <li>其余手指依次排开：左手 <b>A S D</b>（小指、无名指、中指），右手 <b>K L ;</b>（中指、无名指、小指）。</li>
        <li>两个大拇指轻轻搭在<b>空格</b>上。手腕悬空，手指自然弯曲。</li>
        <li>每个键只用一根手指（键盘上的颜色），按完马上回到这一排 —— 它叫「基准键」。</li>
      </ol>
      <p v-if="lessonInfo" class="ldesc">本课「{{ lessonInfo.title }}」：{{ lessonInfo.desc }}</p>
    </div>

    <!-- 练习中：原文 -->
    <div v-else class="text">
      <span
        v-for="(u, i) in shown"
        :key="i"
        class="unit"
        :class="{ gap: !u.text, now: running && st.pos >= u.start && st.pos < u.end, done: st.pos >= u.end }"
      >
        <span v-if="u.text" class="py">
          <i v-for="(c, j) in u.keys" :key="j" :class="{ ok: st.pos > u.start + j, cur: running && st.pos === u.start + j }">{{ c }}</i>
        </span>
        <span v-if="u.text && u.text !== u.keys" class="hz">{{ u.text }}</span>
        <span v-else-if="!u.text" class="sp">␣</span>
      </span>
    </div>

    <div v-if="running && next" class="hint">
      下一个键：<b class="big">{{ label(next) }}</b>
      用 <b :class="'c-' + fingerOf[next]">{{ FINGER_NAME[fingerOf[next]] }}</b>
      <span v-if="!HOME.includes(next) && next !== ' '" class="muted">，按完回到基准键</span>
      <span class="stat">进度 {{ progress }}% · 正确率 {{ st.total ? Math.round((st.correct / st.total) * 100) : 100 }}%</span>
    </div>

    <div v-show="!blind || !running" class="kb">
      <div v-for="(row, i) in ROWS" :key="i" class="krow" :style="{ paddingLeft: OFFSET[i] * 38 + 'px' }">
        <div v-for="k in row" :key="k" class="key" :class="keyCls(k)">
          {{ k === ' ' ? '空格' : k.toUpperCase() }}<span v-if="k === 'f' || k === 'j'" class="bump" />
        </div>
      </div>
    </div>
    <div class="legend">
      <span v-for="(n, f) in FINGER_NAME" :key="f"><i :class="'dot f-' + f" />{{ n }}</span>
      <el-checkbox v-model="blind" size="small" class="blind">盲打：练习时不显示键盘</el-checkbox>
    </div>

    <div v-if="!running && target && st.pos >= target.length" class="summary">
      <template v-if="weak.length">
        最常按错：
        <span v-for="w in weak" :key="w.k" class="weak">{{ label(w.k) }}（{{ w.finger }}，错 {{ w.n }} 次）</span>
        。下次先盯住这几个键，慢一点、按准了再加速。
      </template>
      <template v-else>一个都没按错！可以试试勾上「盲打」，或者换下一课。</template>
    </div>
  </div>
</template>

<style scoped>
.tutor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.intro h4 {
  margin: 0 0 6px;
}
.intro ol {
  margin: 0;
  padding-left: 20px;
  line-height: 1.9;
}
.ldesc {
  margin: 6px 0 0;
  color: var(--el-color-primary);
}
.text {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 4px 2px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  font-size: 22px;
  line-height: 1.2;
  user-select: none;
}
.unit {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  padding: 2px 3px;
  border-radius: 4px;
  color: var(--el-text-color-placeholder);
}
.unit.now {
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-primary);
}
.unit.done {
  color: var(--el-color-success);
}
.unit.gap {
  min-width: 10px;
}
.py {
  font-family: Consolas, Menlo, monospace;
  font-size: 18px;
  letter-spacing: 1px;
}
.py i {
  font-style: normal;
}
.py i.ok {
  color: var(--el-color-success);
}
.py i.cur {
  color: #fff;
  background: var(--el-color-primary);
  border-radius: 3px;
}
.hz {
  font-size: 24px;
}
.sp {
  font-size: 12px;
  opacity: 0.5;
}
.hint {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 15px;
}
.big {
  display: inline-block;
  min-width: 40px;
  padding: 2px 10px;
  border-radius: 6px;
  background: var(--el-color-primary);
  color: #fff;
  text-align: center;
  font-size: 20px;
}
.stat {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.muted {
  color: var(--el-text-color-secondary);
}
.kb {
  display: flex;
  flex-direction: column;
  gap: 5px;
  user-select: none;
  overflow-x: auto;
}
.krow {
  display: flex;
  gap: 5px;
}
.key {
  position: relative;
  flex: none;
  width: 38px;
  height: 38px;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #334;
  transition: transform 0.08s, box-shadow 0.08s;
}
.key.space {
  width: 260px;
}
.key.home {
  border-bottom: 3px solid rgba(0, 0, 0, 0.25);
}
.key.next {
  transform: translateY(-2px);
  box-shadow: 0 0 0 3px var(--el-color-primary), 0 4px 10px rgba(0, 0, 0, 0.18);
  animation: pulse 0.9s ease-in-out infinite;
}
.key.bad {
  background: var(--el-color-danger) !important;
  color: #fff;
}
.bump {
  position: absolute;
  bottom: 5px;
  width: 10px;
  height: 2px;
  border-radius: 1px;
  background: #334;
}
@keyframes pulse {
  50% {
    box-shadow: 0 0 0 5px var(--el-color-primary-light-5), 0 4px 10px rgba(0, 0, 0, 0.18);
  }
}
/* 八根手指各一个颜色：左右对称的手指同色系 */
.f-lp, .dot.f-lp { background: #fde2e2; }
.f-lr, .dot.f-lr { background: #fdebd3; }
.f-lm, .dot.f-lm { background: #fbf5c8; }
.f-li, .dot.f-li { background: #d9f2d9; }
.f-ri, .dot.f-ri { background: #d6ecfb; }
.f-rm, .dot.f-rm { background: #e4defa; }
.f-rr, .dot.f-rr { background: #f6dcf0; }
.f-rp, .dot.f-rp { background: #e3e6ea; }
.f-th, .dot.f-th { background: #f0f0f0; }
.c-lp { color: #c0392b; } .c-lr { color: #c26a12; } .c-lm { color: #9a7d00; } .c-li { color: #2e8b57; }
.c-ri { color: #1f6fb2; } .c-rm { color: #6a4cc2; } .c-rr { color: #b0408f; } .c-rp { color: #556; } .c-th { color: #556; }
.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 4px;
  border-radius: 2px;
  vertical-align: -1px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}
.blind {
  margin-left: auto;
}
.summary {
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--el-color-warning-light-9);
  font-size: 14px;
}
.weak {
  margin: 0 4px;
  font-weight: 600;
}
</style>

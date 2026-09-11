<script setup>
/**
 * 学生平台里的打字训练。
 *
 * 和公开的 /dazi 是同一套练习逻辑，区别只在身份：这里的班级姓名来自
 * 登录账号，学生不用填也改不了，成绩自动挂到他自己名下。
 *
 * 原页面的说明：
 *
 * 四个模块：认识键盘、英文打字、中文打字、自由打字。
 * 前三个计时评分；自由打字是个练手的空板子 —— 不限时、不计分、不上报，
 * 敲什么键就在键盘图上亮什么键，用来熟悉键位和输入法。
 *
 * 速度/正确率/星级都由后端算，这里只上报"敲了多少、对了多少、用了多久"
 * 三个原始量 —— 改评分标准不用重新构建前端。
 */
import { computed, onMounted, onUnmounted, reactive, ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api'
import { currentStudent } from '../../auth'

// 键盘五排，和原页面一致
const KB_ROWS = [
  ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='],
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']', '\\'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', "'"],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/'],
  [' ']
]
const KB_LABEL = [
  ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='],
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '[', ']', '\\'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';', "'"],
  ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/'],
  ['空格']
]
const KB_NAMES = ['数字符号排', '字母 QWERTY 排', '字母 ASDF 排', '字母 ZXCV 排', '空格排']


const conf = ref(null)
const mode = ref('keyboard') // keyboard | english | chinese | free
// 只留练习设置；姓名班级从账号读，不进这个对象，免得有人以为能改
const me = reactive({ difficulty: '简单', limit: 3 })
const who = currentStudent

const MODE_TABS = [
  { k: 'keyboard', t: '认识键盘' },
  { k: 'english', t: '英文打字' },
  { k: 'chinese', t: '中文打字' },
  { k: 'free', t: '自由打字' }
]

// 自由打字不计时不评分，所以班级姓名、难度、限时这些对它都没意义
const isFree = computed(() => mode.value === 'free')

const running = ref(false)
const result = ref(null)
const elapsed = ref(0)
const leftSec = ref(0)
let timer = null
let startedAt = 0

// ---------- 认识键盘 ----------
const kb = reactive({ row: 0, ci: 0, total: 0, correct: 0, status: [] })
const kbTip = ref('点击「开始」后，按提示从第一排第一个键依次敲击。')

function resetKb() {
  kb.row = 0
  kb.ci = 0
  kb.total = 0
  kb.correct = 0
  kb.status = KB_ROWS.map(r => r.map(() => 'pending'))
}
resetKb()

const kbDoneCount = computed(() =>
  kb.status.reduce((s, row) => s + row.filter(x => x === 'ok').length, 0)
)
const kbTotalKeys = KB_ROWS.reduce((s, r) => s + r.length, 0)

function keyClass(i, j) {
  if (i !== kb.row) return 'dim'
  const st = kb.status[i][j]
  if (st === 'ok') return 'ok'
  if (st === 'wrong') return 'wrong'
  return j === kb.ci ? 'cur' : 'dim'
}

function onKeydown(e) {
  if (mode.value !== 'keyboard' || !running.value) return
  if (e.ctrlKey || e.metaKey || e.altKey || e.key === 'Shift' || e.key === 'Tab') return
  e.preventDefault()

  const target = KB_ROWS[kb.row][kb.ci]
  const pressed = e.key.length === 1 ? e.key.toLowerCase() : e.key
  kb.total++

  if (pressed === target) {
    kb.status[kb.row][kb.ci] = 'ok'
    kb.correct++
    kb.ci++
    if (kb.ci >= KB_ROWS[kb.row].length) {
      kb.row++
      kb.ci = 0
      if (kb.row >= KB_ROWS.length) return finish()
    }
    kbTip.value = `请按下 ${KB_LABEL[kb.row][kb.ci]} 键`
  } else {
    kb.status[kb.row][kb.ci] = 'wrong'
    kbTip.value = `按错了，本应输入 ${KB_LABEL[kb.row][kb.ci]} 键，请重试。`
  }
}

// ---------- 自由打字 ----------
// 空板子：敲什么键就在键盘图上亮什么键，敲的内容原样显示出来。
// 不计时、不评分、不上报成绩，纯粹用来熟悉键位和输入法。
const free = reactive({ text: '', keys: 0, lastKey: '', lastCode: '' })
const freeLit = ref('') // 当前亮着的那个键，松开就灭
const freeRef = ref(null)
let freeLitTimer = null

/** 键盘事件里的 key 换算成键盘图上的那一格 */
function keyToCell(e) {
  if (e.key === ' ' || e.code === 'Space') return ' '
  return e.key.length === 1 ? e.key.toLowerCase() : ''
}

function freeKeydown(e) {
  const cell = keyToCell(e)
  free.keys++
  free.lastKey = e.key === ' ' ? '空格' : e.key
  free.lastCode = e.code

  if (cell) {
    freeLit.value = cell
    clearTimeout(freeLitTimer)
    // 松开事件不一定收得到（比如按住不放又切了窗口），定时熄灯更稳
    freeLitTimer = setTimeout(() => (freeLit.value = ''), 180)
  }
}

function freeKeyClass(ch) {
  return freeLit.value === ch ? 'lit' : 'idle'
}

function clearFree() {
  free.text = ''
  free.keys = 0
  free.lastKey = ''
  free.lastCode = ''
  freeRef.value?.focus()
}

// ---------- 文本打字 ----------
const target = ref('')
const typed = ref('')
const inputRef = ref(null)

const chars = computed(() => {
  const t = target.value
  const v = typed.value
  return Array.from(t).map((ch, i) => ({
    ch,
    cls: i < v.length ? (v[i] === ch ? 'ok' : 'bad') : i === v.length ? 'todo cur' : 'todo'
  }))
})

const correctCount = computed(() => {
  const t = target.value
  const v = typed.value
  let c = 0
  for (let i = 0; i < Math.min(v.length, t.length); i++) if (v[i] === t[i]) c++
  return c
})

const liveAcc = computed(() =>
  typed.value.length ? Math.round((correctCount.value / typed.value.length) * 100) : 100
)
const liveSpeed = computed(() => {
  const mins = elapsed.value / 60
  return mins > 0 ? Math.round(correctCount.value / mins) : 0
})
const progress = computed(() =>
  target.value ? Math.round((typed.value.length / target.value.length) * 100) : 0
)

function onInput() {
  if (!running.value) return
  if (typed.value.length >= target.value.length) finish()
}

// ---------- 计时 ----------
function tick() {
  elapsed.value = (Date.now() - startedAt) / 1000
  if (me.limit) {
    leftSec.value = Math.max(0, me.limit * 60 - elapsed.value)
    if (leftSec.value <= 0) finish()
  }
}

function fmt(s) {
  s = Math.max(0, Math.floor(s))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

// ---------- 开始 / 结束 ----------
async function start() {

  result.value = null
  elapsed.value = 0
  leftSec.value = me.limit * 60

  if (mode.value === 'keyboard') {
    resetKb()
    kbTip.value = `请按下 ${KB_LABEL[0][0]} 键`
  } else {
    try {
      const res = await api.typingPassage(mode.value, me.difficulty)
      target.value = res.text
    } catch {
      return
    }
    typed.value = ''
    await nextTick()
    inputRef.value?.focus()
  }

  running.value = true
  startedAt = Date.now()
  clearInterval(timer)
  timer = setInterval(tick, 300)
}

async function finish() {
  if (!running.value) return
  running.value = false
  clearInterval(timer)
  const secs = (Date.now() - startedAt) / 1000

  const payload =
    mode.value === 'keyboard'
      ? { module: '键盘', typed_chars: kb.total, correct_chars: kb.correct }
      : {
          module: mode.value === 'english' ? '英文' : '中文',
          typed_chars: typed.value.length,
          correct_chars: correctCount.value
        }

  try {
    result.value = await api.typingSubmit({
      // 后端会用令牌里的账号覆盖这两项，这里传只是为了满足接口结构
      student_name: who.value?.name || '',
      student_class: who.value?.student_class || '',
      difficulty: me.difficulty,
      duration: secs,
      ...payload
    })
  } catch {
    ElMessage.error('成绩上传失败，请截图保存后告诉老师')
  }
}

function switchMode(m) {
  if (running.value) return ElMessage.warning('练习进行中，先完成或等计时结束')
  mode.value = m
  result.value = null
  if (m === 'keyboard') resetKb()
  if (m === 'free') nextTick(() => freeRef.value?.focus())
}

onMounted(async () => {
  try {
    conf.value = await api.typingConfig()
    me.difficulty = conf.value.default_difficulty
    me.limit = conf.value.default_limit
  } catch {
    return
  }
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  clearInterval(timer)
  clearTimeout(freeLitTimer)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="wrap">
    <!-- 顶栏 -->
    <div class="panel top">
      <h1>
        <span class="logo">⌨</span>
        学生打字训练<small>认识键盘 · 英文 · 中文 · 自由打字</small>
      </h1>
      <div class="setrow">
        <div class="field">
          <label>练习者</label>
          <span class="whoami">{{ who?.name }}　{{ who?.student_class || '未分班' }}</span>
        </div>
        <div class="field">
          <label>难度</label>
          <el-select v-model="me.difficulty" :disabled="isFree" style="width: 110px">
            <el-option v-for="d in conf?.difficulties || []" :key="d" :label="d" :value="d" />
          </el-select>
        </div>
        <div class="field">
          <label>限时</label>
          <el-select v-model="me.limit" :disabled="isFree" style="width: 120px">
            <el-option
              v-for="t in conf?.time_limits || []"
              :key="t"
              :label="`${t} 分钟`"
              :value="t"
            />
          </el-select>
        </div>
        <div class="modes">
          <button
            v-for="m in MODE_TABS"
            :key="m.k"
            class="mbtn"
            :class="{ on: mode === m.k }"
            @click="switchMode(m.k)"
          >{{ m.t }}</button>
        </div>
      </div>
      <p v-if="isFree" class="note">
        自由打字<b>不限时、不计分、也不会提交成绩</b>，随便敲，敲到的键会在下面的键盘上亮起来。
      </p>
      <p v-else class="note">完成后成绩<b>自动记到你名下</b>，不用另外交，老师那边能看到。</p>
    </div>

    <!-- 实时状态条 -->
    <div class="panel">
      <div class="livebar">
        <template v-if="isFree">
          <div class="seg"><span>已敲</span><b>{{ free.keys }}</b> 次</div>
          <div class="seg"><span>输入</span><b>{{ free.text.length }}</b> 字</div>
          <div class="seg">
            <span>最后按键</span>
            <b class="lastkey">{{ free.lastKey || '—' }}</b>
          </div>
          <div class="grow" />
          <el-button @click="clearFree">清空重来</el-button>
        </template>
        <template v-else>
          <template v-if="mode === 'keyboard'">
            <div class="seg"><span>状态</span><b>{{ running ? '进行中' : result ? '已完成' : '未开始' }}</b></div>
            <div class="seg"><span>进度</span><b>{{ kb.row }} / 5 排（{{ kbDoneCount }}/{{ kbTotalKeys }} 键）</b></div>
            <div class="seg"><span>正确率</span><b>{{ kb.total ? Math.round((kb.correct / kb.total) * 100) + '%' : '—' }}</b></div>
          </template>
          <template v-else>
            <div class="seg"><span>速度</span><b>{{ liveSpeed }}</b> 字/分</div>
            <div class="seg"><span>正确率</span><b>{{ liveAcc }}%</b></div>
            <div class="seg"><span>进度</span><b>{{ progress }}%</b></div>
          </template>
          <div class="seg"><span>剩余</span><b>{{ fmt(leftSec) }}</b></div>
          <div class="grow" />
          <el-button type="primary" :disabled="running" @click="start">
            {{ result ? '再练一次' : '开始' }}
          </el-button>
          <el-button v-if="running" @click="finish">结束并交成绩</el-button>
        </template>
      </div>

      <!-- 自由打字：不限时的空板子，敲到的键会亮 -->
      <div v-if="isFree" class="body">
        <el-input
          ref="freeRef"
          v-model="free.text"
          type="textarea"
          :rows="4"
          class="ta"
          placeholder="点这里开始随便敲。中英文都行，想练输入法就切到中文输入法。"
          @keydown="freeKeydown"
        />
        <div class="kb freekb">
          <div v-for="(row, i) in KB_ROWS" :key="i" class="krow">
            <div
              v-for="(ch, j) in row"
              :key="j"
              class="key"
              :class="[freeKeyClass(ch), { space: ch === ' ' }]"
            >{{ KB_LABEL[i][j] }}</div>
          </div>
        </div>
        <div class="tip">
          <template v-if="free.lastCode">
            刚才按的是 <b>{{ free.lastKey }}</b>
            <span class="code">（{{ free.lastCode }}）</span>
          </template>
          <template v-else>按任意键试试 —— 键盘图上对应的那一格会亮一下。</template>
        </div>
      </div>

      <!-- 认识键盘 -->
      <div v-else-if="mode === 'keyboard'" class="body">
        <div class="rowtabs">
          <span
            v-for="(n, i) in KB_NAMES"
            :key="i"
            class="rowtab"
            :class="{ on: i === kb.row, done: kb.status[i]?.every(s => s === 'ok') }"
          >{{ i + 1 }}. {{ n }}</span>
        </div>
        <div class="kb">
          <div v-for="(row, i) in KB_ROWS" :key="i" class="krow">
            <div
              v-for="(ch, j) in row"
              :key="j"
              class="key"
              :class="[keyClass(i, j), { space: ch === ' ' }]"
            >{{ KB_LABEL[i][j] }}</div>
          </div>
        </div>
        <div class="tip">{{ kbTip }}</div>
      </div>

      <!-- 文本打字 -->
      <div v-else class="body">
        <div v-if="!target" class="placeholder">点上方「开始」加载练习文本</div>
        <template v-else>
          <div class="display">
            <span v-for="(c, i) in chars" :key="i" class="c" :class="c.cls">{{ c.ch }}</span>
          </div>
          <el-input
            ref="inputRef"
            v-model="typed"
            type="textarea"
            :rows="3"
            :disabled="!running"
            :placeholder="mode === 'english' ? '在此输入上方英文' : '在此用输入法输入上方中文'"
            class="ta"
            @input="onInput"
          />
          <div class="meta">
            <span>看上方文字逐字输入，错的会标红</span>
            <span>已输入 {{ typed.length }} / {{ target.length }} 字</span>
          </div>
        </template>
      </div>

      <!-- 成绩 -->
      <div v-if="result" class="result">
        <h3>本次成绩 · {{ result.module }}</h3>
        <div class="grid">
          <div v-if="result.speed"><span>打字速度</span><b>{{ result.speed }} 字/分</b></div>
          <div v-else><span>敲击键数</span><b>{{ kb.total }} 键</b></div>
          <div><span>正确率</span><b>{{ result.accuracy }}%</b></div>
          <div><span>用时</span><b>{{ fmt(result.duration) }}</b></div>
          <div><span>难度</span><b>{{ result.difficulty }}</b></div>
          <div>
            <span>评价</span>
            <b class="stars">{{ '★'.repeat(result.stars) + '☆'.repeat(3 - result.stars) }}</b>
          </div>
        </div>
        <p class="ok-note">✓ 成绩已提交给老师</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1180px;
  margin: 0 auto;
  padding: 22px 18px 60px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 14px;
  overflow: hidden;
}
.top {
  padding: 18px 22px;
}
h1 {
  font-size: 19px;
  font-weight: 650;
  display: flex;
  align-items: center;
  gap: 11px;
  margin: 0 0 16px;
}
.logo {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: linear-gradient(135deg, #5b7cfa, #4f6ef7);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
}
h1 small {
  font-weight: 400;
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
.setrow {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: flex-end;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.whoami {
  display: inline-block;
  font-size: 13.5px;
  padding: 6px 14px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
.field label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.field i {
  color: var(--el-color-danger);
  font-style: normal;
}
.modes {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.mbtn {
  padding: 8px 18px;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  color: var(--el-text-color-regular);
  border-radius: 9px;
  cursor: pointer;
  font-size: 13.5px;
  font-family: inherit;
}
.mbtn:hover {
  border-color: var(--el-color-primary-light-5);
}
.mbtn.on {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
  font-weight: 600;
}
.note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 12px 0 0;
}
.livebar {
  display: flex;
  gap: 22px;
  align-items: center;
  flex-wrap: wrap;
  padding: 13px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.seg {
  display: flex;
  flex-direction: column;
}
.seg span {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.seg b {
  font-size: 15px;
}
.grow {
  flex: 1;
}
.body {
  padding: 20px;
}
.rowtabs {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.rowtab {
  padding: 6px 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
.rowtab.on {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
  font-weight: 600;
}
.rowtab.done {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
  border-color: var(--el-color-success-light-5);
}
.kb {
  padding: 8px 0;
}
.krow {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin: 8px 0;
}
.key {
  width: 48px;
  height: 48px;
  border: 1.5px solid var(--el-border-color);
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
  user-select: none;
  transition: 0.12s;
}
.key.space {
  width: 300px;
}
.key.cur {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: 0 0 0 3px var(--el-color-primary-light-8);
}
.key.ok {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
  color: var(--el-color-success);
}
.key.wrong {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.key.dim {
  opacity: 0.45;
}
/* 自由打字：平时是暗的，敲到哪个键哪个键亮一下 */
.key.idle {
  opacity: 0.5;
}
.key.lit {
  opacity: 1;
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  color: #fff;
  transform: translateY(2px);
  box-shadow: 0 0 0 4px var(--el-color-primary-light-8);
}
.freekb {
  margin-top: 18px;
}
.lastkey {
  font-family: ui-monospace, Consolas, monospace;
}
.tip .code {
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12.5px;
}
.tip {
  margin-top: 16px;
  padding: 14px 18px;
  background: var(--el-color-primary-light-9);
  border-radius: 10px;
  font-size: 13.5px;
  min-height: 22px;
}
.display {
  padding: 18px;
  font-size: 19px;
  line-height: 2.05;
  letter-spacing: 0.5px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
  min-height: 120px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  user-select: none;
  margin-bottom: 14px;
}
.c {
  border-radius: 3px;
  padding: 0 1px;
}
.c.todo {
  color: var(--el-text-color-placeholder);
}
.c.ok {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}
.c.bad {
  color: #fff;
  background: var(--el-color-danger);
}
.c.cur {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 1px;
}
.ta :deep(textarea) {
  font-size: 17px;
  line-height: 1.7;
}
.meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 7px;
}
.placeholder {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 50px 0;
}
.result {
  margin: 0 20px 20px;
  padding: 18px;
  border-radius: 11px;
  background: var(--el-color-success-light-9);
  border: 1px solid var(--el-color-success-light-5);
}
.result h3 {
  font-size: 16px;
  margin: 0 0 12px;
}
.grid {
  display: flex;
  gap: 26px;
  flex-wrap: wrap;
}
.grid div span {
  display: block;
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
  margin-bottom: 3px;
}
.grid div b {
  font-size: 19px;
}
.stars {
  color: #e6a23c;
  letter-spacing: 3px;
}
.ok-note {
  margin: 14px 0 0;
  color: var(--el-color-success);
  font-weight: 600;
  font-size: 13px;
}
@media (max-width: 820px) {
  .modes {
    margin-left: 0;
    width: 100%;
  }
  .key {
    width: 34px;
    height: 40px;
    font-size: 13px;
  }
  .key.space {
    width: 180px;
  }
}
</style>

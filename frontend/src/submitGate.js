/**
 * 交卷门槛：考试时间过了三分之二、**并且**答完三分之二的题，才放行交卷。
 *
 * 学生端 exe（desktop/client/exam_ui.py）是同一条规矩，改一边记得改另一边。
 *
 * 开考时间记在 localStorage 里（按考试分开记）：学生刷新页面、不小心关了再进来，
 * 已经考过的时间照算，不会从零开始重新等。交卷成功后清掉。
 */
import { computed, onBeforeUnmount, ref } from 'vue'

export const GATE_RATIO = 2 / 3

/** 卷面上的「40」「40分钟」都变成 40；写不出数字的按 45 分钟算（和学生端一致）。 */
export function durationMinutes(duration) {
  const digits = String(duration ?? '').replace(/\D/g, '')
  return digits ? parseInt(digits, 10) : 45
}

/** 至少要答几题 / 至少要考几秒。向上取整：30 题要答满 20 题，45 分钟要考满 30 分钟。 */
export function gateNeeds(totalQuestions, minutes) {
  return {
    questions: Math.ceil(totalQuestions * GATE_RATIO),
    seconds: Math.ceil(minutes * 60 * GATE_RATIO)
  }
}

function fmt(sec) {
  const s = Math.max(0, Math.ceil(sec))
  const m = Math.floor(s / 60)
  return m ? `${m} 分 ${String(s % 60).padStart(2, '0')} 秒` : `${s} 秒`
}

/**
 * @param key      这场考试的标识（考试 id 或口令），用来分开记开考时间
 * @param paper    ref：取回来的卷子（有 total、duration）
 * @param answered computed：已作答题数
 */
export function useSubmitGate(key, paper, answered) {
  const storeKey = `examStartedAt:${key}`
  const now = ref(Date.now())
  let startedAt = 0

  function start() {
    try {
      startedAt = Number(localStorage.getItem(storeKey)) || 0
    } catch {
      startedAt = 0
    }
    if (!startedAt || startedAt > Date.now()) {
      startedAt = Date.now()
      try {
        localStorage.setItem(storeKey, String(startedAt))
      } catch {
        /* 无痕模式写不进去也照样考，只是刷新后重新计时 */
      }
    }
    now.value = Date.now()
  }

  function done() {
    try {
      localStorage.removeItem(storeKey)
    } catch {
      /* 忽略 */
    }
  }

  const timer = setInterval(() => (now.value = Date.now()), 1000)
  onBeforeUnmount(() => clearInterval(timer))

  const needs = computed(() =>
    gateNeeds(paper.value?.total || 0, durationMinutes(paper.value?.duration))
  )
  const elapsed = computed(() => (startedAt ? (now.value - startedAt) / 1000 : 0))
  const waitSeconds = computed(() => Math.max(0, needs.value.seconds - elapsed.value))
  const moreQuestions = computed(() => Math.max(0, needs.value.questions - answered.value))
  // 老师给这场考试开了「允许提前交卷」：不设门槛
  const early = computed(() => !!paper.value?.early_submit)
  const canSubmit = computed(
    () => early.value || (waitSeconds.value <= 0 && moreQuestions.value <= 0)
  )

  /** 交不了时说清楚还差什么；能交时是空串 */
  const reason = computed(() => {
    if (canSubmit.value) return ''
    const parts = []
    if (moreQuestions.value > 0) parts.push(`还要再答 ${moreQuestions.value} 题`)
    if (waitSeconds.value > 0) parts.push(`还要再等 ${fmt(waitSeconds.value)}`)
    return (
      `考试时间过了三分之二、并且答完三分之二的题（至少 ${needs.value.questions} 题）才能交卷：` +
      parts.join('，')
    )
  })

  return { start, done, canSubmit, reason, needs, waitSeconds, moreQuestions }
}

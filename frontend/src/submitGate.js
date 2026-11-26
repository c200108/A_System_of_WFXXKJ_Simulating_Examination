/**
 * 交卷门槛：考试时间过了一半、**并且**答完一半的题，才放行交卷。
 *
 * 学生端 exe（desktop/client/exam_ui.py）是同一条规矩，改一边记得改另一边。
 *
 * 开考时间记在 localStorage 里（按考试分开记）：学生刷新页面、不小心关了再进来，
 * 已经考过的时间照算，不会从零开始重新等。交卷成功后清掉。
 */
import { computed, onBeforeUnmount, ref } from 'vue'

export const GATE_RATIO = 1 / 2
/** 记下的开考时间超过「时长 + 这么多秒」就当是上次没交完的旧记录，重新计时 */
const STALE_GRACE = 600
/** 剩这么多秒倒计时变红 */
export const LATE_SECONDS = 180

/** 卷面上的「40」「40分钟」都变成 40；写不出数字的按 45 分钟算（和学生端一致）。 */
export function durationMinutes(duration) {
  const digits = String(duration ?? '').replace(/\D/g, '')
  return digits ? parseInt(digits, 10) : 45
}

/** 至少要答几题 / 至少要考几秒。向上取整：30 题要答满 15 题，45 分钟要考满 22 分 30 秒。 */
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
 * @param live     （可选）问教师端最新设置的函数，返回 { early_submit }。
 *                 老师考试**中途**打开「允许提前交卷」，取卷时那份是旧的，靠它每 60 秒跟上（各页面随机错开）
 */
export function useSubmitGate(key, paper, answered, live = null) {
  const storeKey = `examStartedAt:${key}`
  const now = ref(Date.now())
  let startedAt = 0

  /**
   * 开始计时。paperKey 是「这一套卷子」的标识（网页链接开了乱序时是服务端给的 draw）：
   * 记下的开考时间是另一套卷子的（刷新换了题）就重新计时；同一套（临时保存后刷新）接着计。
   *
   * 2.29.1：以前只认考试，不认卷子，而且开过一次没交就一直记着 —— 隔天再打开，一进来就是
   * 「考试时间已到」。现在除了换卷子重新计时，记下的时间已经超过「时长 + 10 分钟」的
   * （上次开着没交、早就考完了）也当这次是重新开考。
   */
  function start(paperKey = '') {
    let saved = null
    try {
      const raw = localStorage.getItem(storeKey)
      saved = raw && raw.startsWith('{') ? JSON.parse(raw) : raw ? { at: Number(raw), paper: null } : null
    } catch {
      saved = null
    }
    const limit = (durationMinutes(paper.value?.duration) * 60 + STALE_GRACE) * 1000
    const at = Number(saved?.at) || 0
    const fresh =
      !at || at > Date.now() || Date.now() - at > limit || (saved?.paper ?? null) !== String(paperKey)
    startedAt = fresh ? Date.now() : at
    if (fresh) {
      try {
        localStorage.setItem(storeKey, JSON.stringify({ at: startedAt, paper: String(paperKey) }))
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
  const liveEarly = ref(null)        // 问到过就以它为准；没问到（断网）就用取卷时那份
  async function sync() {
    if (!live || !paper.value) return
    try {
      const got = await live()
      if (got && 'early_submit' in got) liveEarly.value = !!got.early_submit
    } catch {
      /* 连不上就按原来的设置走，不打扰学生 */
    }
  }
  // 每 60 秒问一次；第一次在 0～60 秒里随机挑个时候，全班同时打开试卷也不会扎堆
  const LIVE_MS = 60000
  let liveTimer = null
  const firstTimer = live
    ? setTimeout(() => {
        sync()
        liveTimer = setInterval(sync, LIVE_MS)
      }, Math.random() * LIVE_MS)
    : null
  onBeforeUnmount(() => {
    clearInterval(timer)
    if (firstTimer) clearTimeout(firstTimer)
    if (liveTimer) clearInterval(liveTimer)
  })

  const needs = computed(() =>
    gateNeeds(paper.value?.total || 0, durationMinutes(paper.value?.duration))
  )
  const elapsed = computed(() => (startedAt ? (now.value - startedAt) / 1000 : 0))
  const waitSeconds = computed(() => Math.max(0, needs.value.seconds - elapsed.value))
  const moreQuestions = computed(() => Math.max(0, needs.value.questions - answered.value))
  // 老师给这场考试开了「允许提前交卷」：不设门槛
  const early = computed(() =>
    liveEarly.value === null ? !!paper.value?.early_submit : liveEarly.value
  )
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
      `考试时间过了一半、并且答完一半的题（至少 ${needs.value.questions} 题）才能交卷：` +
      parts.join('，')
    )
  })

  // 剩余答题时间：答题页左下角一直显示，最后 3 分钟变红；到点由答题页强制交卷（2.29.1）
  const startedRef = ref(0)
  const remaining = computed(() =>
    startedRef.value ? durationMinutes(paper.value?.duration) * 60 - (now.value - startedRef.value) / 1000 : null
  )
  const late = computed(() => remaining.value !== null && remaining.value < LATE_SECONDS)
  const timeUp = computed(() => remaining.value !== null && remaining.value <= 0)
  const remainText = computed(() => {
    const r = remaining.value
    if (r === null) return ''
    if (r <= 0) return '考试时间到，自动交卷'
    const s = Math.ceil(r)
    const h = Math.floor(s / 3600)
    const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
    const ss = String(s % 60).padStart(2, '0')
    return `剩余时间 ${h ? h + ':' : ''}${mm}:${ss}`
  })

  return {
    /** paperKey：这一套卷子的标识（重抽的 draw），换了卷子重新计时 */
    start: (paperKey = '') => {
      start(paperKey)
      startedRef.value = startedAt
    },
    done,
    sync,
    canSubmit,
    reason,
    needs,
    waitSeconds,
    moreQuestions,
    remaining,
    remainText,
    late,
    timeUp
  }
}

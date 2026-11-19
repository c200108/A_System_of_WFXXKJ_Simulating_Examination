/**
 * 计分打字练习的会话（服务端 2.23.1）。/dazi 和学生平台里的打字共用。
 *
 * 原来交成绩只报「敲了多少、对了多少、用了多久」三个数，改个数字就能交上去一个满分。
 * 现在：开练向服务端领会话（服务端出文本、记开始时间）→ 练习中每 1.5 秒把输入框内容
 * 同步上去 → 交成绩只交会话 id 和最终内容。速度、正确率、用时全由服务端算。
 *
 * 同步失败（断网、服务器忙）不打断练习，下次同步或交成绩时一口气补上；
 * 服务端回 4xx（判成粘贴作废、会话过期、已经交过）才停下来告诉学生。
 * 输入法正在打拼音（组字）的时候不同步：框里那几个拼音字母不是最终内容。
 */
import { api, explainError } from './api'

/**
 * opts.getAnswer()   现在的作答：文本模块是输入框内容，键盘模块是按过的键排成的串
 * opts.onFatal(msg)  这次练习不能用了（服务端说的原因），调用方停表、提示学生
 */
export function createTypingSession(opts) {
  let id = ''
  let synced = ''
  let timer = null
  let busy = false
  let composing = false

  async function begin(body) {
    stop()
    id = ''
    const res = await api.typingStart(body)
    id = res.session_id
    synced = ''
    const every = Math.max(0.5, Number(res.sync_interval_sec) || 1.5)
    timer = setInterval(sync, every * 1000)
    return res
  }

  async function sync() {
    if (!id || busy || composing) return
    const answer = opts.getAnswer()
    if (answer === synced) return
    busy = true
    try {
      const res = await api.typingProgress({ session_id: id, answer })
      if (res?.ok !== false) synced = answer
    } catch (err) {
      const st = err?.response?.status
      // 断网、5xx、太频繁：不管它，下次再同步
      if (st >= 400 && st < 500 && st !== 429) {
        stop()
        opts.onFatal(explainError(err))
      }
    } finally {
      busy = false
    }
  }

  function stop() {
    clearInterval(timer)
    timer = null
  }

  /** 交成绩。extra 里放 keystrokes（这次在输入框里按了几次键）。返回服务端算好的成绩 */
  function submit(answer, extra = {}) {
    stop()
    return api.typingSubmit({ session_id: id, answer, ...extra })
  }

  return {
    begin,
    stop,
    submit,
    get id() {
      return id
    },
    setComposing(v) {
      composing = !!v
    }
  }
}

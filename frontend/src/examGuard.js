/**
 * 答题页防作弊（2.28.0）：不让开开发者工具、不让脚本替学生作答。
 *
 *  · 屏蔽 F12、Ctrl+Shift+I / J / C / K、Ctrl+U（看源码）、Ctrl+S（存网页）和右键菜单；
 *  · 发现开发者工具开着（断点停住了），整页盖一层提示，交卷按钮不让点，关掉以后自动恢复；
 *  · 作答只认**真人操作**产生的事件（event.isTrusted），控制台里用脚本点选项、填空不算数
 *    （见 ObjectiveAnswer.vue 的 guard）。
 *
 * 浏览器里的东西不可能做到绝对防住：这些是挡住「随手按 F12 改一改、跑段脚本」的。
 * 真正的底线在服务端 —— 答案从不下发、判分在服务端、交卷限次限频、核对名单。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

const BLOCK_KEYS = new Set(['I', 'J', 'C', 'K'])

export function useExamGuard() {
  const tampered = ref(false)
  let timer = null

  function onKey(e) {
    const k = String(e.key || '').toUpperCase()
    const mod = e.ctrlKey || e.metaKey
    if (
      k === 'F12' ||
      (mod && e.shiftKey && BLOCK_KEYS.has(k)) ||
      (mod && e.altKey && BLOCK_KEYS.has(k)) ||
      (mod && (k === 'U' || k === 'S'))
    ) {
      e.preventDefault()
      e.stopPropagation()
    }
  }
  function onMenu(e) {
    // 输入框里留着右键（有的同学习惯右键粘贴自己刚打的字）；别处一律不弹
    if (!(e.target && e.target.closest && e.target.closest('input, textarea'))) e.preventDefault()
  }
  function check() {
    // 开发者工具开着时，下面这个断点会把页面停住 —— 停住了就说明开着。
    // 不用「窗口内外尺寸差」那种判法：浏览器缩放到 125%、150% 时也差一大截，会冤枉学生
    const t0 = performance.now()
    // eslint-disable-next-line no-new-func
    new Function('debugger')()
    tampered.value = performance.now() - t0 > 120
  }

  onMounted(() => {
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('contextmenu', onMenu, true)
    check()
    timer = setInterval(check, 1500)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKey, true)
    window.removeEventListener('contextmenu', onMenu, true)
    clearInterval(timer)
  })
  return { tampered }
}

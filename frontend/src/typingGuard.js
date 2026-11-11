/**
 * 打字练习防作弊（服务端 2.22.1）。学生打字页（/dazi 和学生平台里的打字）共用。
 *
 * 学生成绩里出现过「8340 字/分、用时 1 秒」这种 —— 复制粘贴进去的。这里在浏览器里挡：
 *
 * 1. 输入框：粘贴、拖放、剪切、复制、右键菜单、Ctrl/⌘ + V/C/X/A、Shift+Insert 全部拦掉；
 *    beforeinput 里来源是粘贴 / 拖放 / 自动替换的也拦（右键菜单被绕过、浏览器扩展塞字都走这里）。
 * 2. 数按键：练习期间输入框里按了多少次键（输入法拼音、五笔编码的按键也算），交成绩时报给服务端。
 *    服务端按「字数 / 按键数」判是不是粘贴进来的，这一层前端改不了结果。
 * 3. 字数突变：一次输入里冒出好几个字、而这期间几乎没按键（扩展、脚本、语音输入塞进来的），
 *    直接退回去，不让它算数。
 * 4. 开发者工具：F12、Ctrl+Shift+I/J/C/K、Ctrl+U（看源码）、Ctrl+S、⌘+⌥+I/J/C 都拦；
 *    练习进行中每秒用 debugger 计时探一次（开着开发者工具时 debugger 会停住，耗时明显变长），
 *    探到就作废这次练习、不交成绩。思路和开源的 disable-devtool、devtools-detect 一样。
 *
 * 前端这几层都只是「挡住顺手的」；真正把关的是服务端的速度上限和按键数核对（typing_train.py）。
 */

/** 开发者工具 / 看源码 / 存网页这些快捷键 */
export function isDevtoolsKey(e) {
  const k = (e.key || '').toLowerCase()
  if (e.key === 'F12' || e.keyCode === 123) return true
  const mod = e.ctrlKey || e.metaKey
  if (mod && e.shiftKey && ['i', 'j', 'c', 'k', 'e', 'm'].includes(k)) return true // 各浏览器的开发者工具
  if (e.metaKey && e.altKey && ['i', 'j', 'c', 'u'].includes(k)) return true      // macOS
  if (mod && ['u', 's'].includes(k)) return true                                   // 看源码、另存网页
  return false
}

/** 输入框里不许用的编辑快捷键：粘贴、复制、剪切、全选 */
export function isClipboardKey(e) {
  const k = (e.key || '').toLowerCase()
  if ((e.ctrlKey || e.metaKey) && ['v', 'c', 'x', 'a'].includes(k)) return true
  if (e.shiftKey && (e.key === 'Insert' || e.keyCode === 45)) return true // Shift+Insert = 粘贴
  if (e.ctrlKey && (e.key === 'Insert' || e.keyCode === 45)) return true  // Ctrl+Insert = 复制
  return false
}

const BLOCKED_INPUT_TYPES = new Set([
  'insertFromPaste',
  'insertFromPasteAsQuotation',
  'insertFromDrop',
  'insertFromYank',
  'insertReplacementText', // 拼写检查、自动更正替换
  'insertTranspose',
  'deleteByCut',
  'deleteByDrag'
])

/**
 * 开发者工具探测：debugger 语句只有开着开发者工具才会停住。
 * 用 new Function 包一层，免得打包时被当成调试代码删掉。
 */
const probe = (() => {
  try {
    return new Function('debugger')
  } catch {
    return () => {}
  }
})()

export function devtoolsOpen() {
  const t = performance.now()
  probe()
  return performance.now() - t > 100
}

/**
 * 页面级的守卫：整页拦开发者工具快捷键和右键菜单。
 * 返回 { attach(el), detach(), keys, resetRun(), checkDevtools() ... }
 *
 * opts.onBlocked(msg)  拦下了一次粘贴 / 快捷键（给学生提示用）
 * opts.onDevtools()    练习中探到开发者工具
 * opts.isRunning()     现在是不是在计时练习
 */
export function createTypingGuard(opts = {}) {
  const onBlocked = opts.onBlocked || (() => {})
  const onDevtools = opts.onDevtools || (() => {})
  const isRunning = opts.isRunning || (() => false)

  const state = {
    keys: 0,          // 本次练习输入框里的按键数
    keysSinceInput: 0, // 上次输入事件之后又按了几次键
    blocked: 0        // 本次练习拦下的粘贴 / 快捷键次数
  }
  let el = null
  let probeTimer = null
  let lastWarn = 0

  function warn(msg) {
    state.blocked++
    const now = Date.now()
    if (now - lastWarn > 1500) {
      lastWarn = now
      onBlocked(msg)
    }
  }

  // ---------- 整页 ----------
  function onWindowKeydown(e) {
    if (isDevtoolsKey(e)) {
      e.preventDefault()
      e.stopPropagation()
      warn('打字练习页不能打开开发者工具或查看源码')
    }
  }
  function onContextMenu(e) {
    e.preventDefault()
  }
  function onSelectStart(e) {
    // 原文那块不让选中（选不中就复制不了）；输入框里自己打的字照样能选
    if (!(e.target instanceof Element) || !e.target.closest('textarea, input')) e.preventDefault()
  }
  function onWindowCopy(e) {
    e.preventDefault()
  }

  // ---------- 输入框 ----------
  function onPaste(e) {
    e.preventDefault()
    warn('打字练习不能粘贴，请自己一个字一个字地打')
  }
  function onDrop(e) {
    e.preventDefault()
    warn('打字练习不能拖文字进来')
  }
  function onDragOver(e) {
    e.preventDefault()
  }
  function onCopyCut(e) {
    e.preventDefault()
  }
  function onBeforeInput(e) {
    if (BLOCKED_INPUT_TYPES.has(e.inputType)) {
      e.preventDefault()
      warn('打字练习不能粘贴、拖放或自动替换文字')
    }
  }
  function onKeydown(e) {
    if (isClipboardKey(e)) {
      e.preventDefault()
      warn('打字练习不能用复制、粘贴、全选快捷键')
      return
    }
    // 只按 Ctrl / Shift / Alt 这类不算一次「打字」
    if (['Control', 'Shift', 'Alt', 'Meta', 'CapsLock'].includes(e.key)) return
    if (isRunning()) {
      state.keys++
      state.keysSinceInput++
    }
  }

  function attach(target) {
    // 传进来的可以是 el-input 组件，也可以是 textarea 本身
    let node = target
    if (node && !(node instanceof Element)) node = node.textarea || node.input || node.$el
    if (node instanceof Element && !/^(TEXTAREA|INPUT)$/.test(node.tagName)) {
      node = node.querySelector('textarea, input')
    }
    if (!node || node === el) return
    detachInput()
    el = node
    el.setAttribute('autocomplete', 'off')
    el.setAttribute('autocorrect', 'off')
    el.setAttribute('autocapitalize', 'off')
    el.setAttribute('spellcheck', 'false')
    el.addEventListener('paste', onPaste)
    el.addEventListener('drop', onDrop)
    el.addEventListener('dragover', onDragOver)
    el.addEventListener('copy', onCopyCut)
    el.addEventListener('cut', onCopyCut)
    el.addEventListener('beforeinput', onBeforeInput)
    el.addEventListener('keydown', onKeydown)
  }

  function detachInput() {
    if (!el) return
    el.removeEventListener('paste', onPaste)
    el.removeEventListener('drop', onDrop)
    el.removeEventListener('dragover', onDragOver)
    el.removeEventListener('copy', onCopyCut)
    el.removeEventListener('cut', onCopyCut)
    el.removeEventListener('beforeinput', onBeforeInput)
    el.removeEventListener('keydown', onKeydown)
    el = null
  }

  function install() {
    window.addEventListener('keydown', onWindowKeydown, true)
    window.addEventListener('contextmenu', onContextMenu, true)
    document.addEventListener('selectstart', onSelectStart, true)
    document.addEventListener('copy', onWindowCopy, true)
    document.addEventListener('cut', onWindowCopy, true)
  }

  function uninstall() {
    stopProbe()
    detachInput()
    window.removeEventListener('keydown', onWindowKeydown, true)
    window.removeEventListener('contextmenu', onContextMenu, true)
    document.removeEventListener('selectstart', onSelectStart, true)
    document.removeEventListener('copy', onWindowCopy, true)
    document.removeEventListener('cut', onWindowCopy, true)
  }

  /** 开始一次新练习：计数清零，开始探开发者工具 */
  function resetRun() {
    state.keys = 0
    state.keysSinceInput = 0
    state.blocked = 0
    stopProbe()
    probeTimer = setInterval(() => {
      if (isRunning() && devtoolsOpen()) onDevtools()
    }, 1000)
  }

  function stopProbe() {
    clearInterval(probeTimer)
    probeTimer = null
  }

  /**
   * 输入框内容变了：判断这次多出来的字是不是自己敲的。
   * 返回 true = 正常；false = 来路不明（调用方把内容退回去）。
   *
   * 英文：每个字母都要按一次键，多出来的字数不能比这期间的按键数多出 1 个以上。
   * 中文：输入法上屏的那一下前面一定有按键（拼音、编码、空格、数字选词），
   * 一次上屏几个字很正常，但「没按键就冒出两个以上字」或「一次冒出 30 个字以上」不正常。
   */
  function checkGrowth(added, lang) {
    const keys = state.keysSinceInput
    state.keysSinceInput = 0
    if (added <= 1) return true
    let ok
    if (lang === 'english') ok = added <= keys + 1
    else ok = keys > 0 && added <= 30
    if (!ok) warn('检测到不是键盘敲进来的文字，已撤回')
    return ok
  }

  return {
    state,
    install,
    uninstall,
    attach,
    resetRun,
    stopProbe,
    checkGrowth
  }
}

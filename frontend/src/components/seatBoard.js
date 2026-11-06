/**
 * 在线座次的「座位板」交互（2.20.x）：认出格子里是哪位学生、长按拖动换座、小组配色。
 *
 * 表格本体还是 Jspreadsheet（改字、样式、合并都靠它），这里在它上面加一层：
 * - 不碰格子的 style 属性（表格库保存样式就是读 style 属性，碰了会把小组颜色、分数角标存进座次表），
 *   只用 data-* 属性 + 一段生成的 CSS 显示小组底色、班干部和分数角标；
 * - 长按才进入拖动，短按 / 直接拖还是原来的框选，不抢表格本来的操作。
 *
 * 不依赖 Vue 组件，SeatSheet.vue 里接上。
 */

/** 淡色系小组底色：够浅，黑字 / 深色字的姓名照样醒目 */
export const GROUP_COLORS = [
  '#DCEBFF', // 淡蓝
  '#DDF5E3', // 淡绿
  '#FFE9D2', // 淡橙
  '#EFE1FA', // 淡紫
  '#D6F3F5', // 淡青
  '#FFDDE8', // 淡粉
  '#F6F3C9', // 淡黄
  '#E6E9EE' // 淡灰
]

/**
 * 学生名单 → 「格子里的字是谁」。格子里可能写「姓名」或「学号 姓名」（一键导入的两种写法）。
 * 重名的只认「学号 姓名」那种写法，免得认错人。
 */
export function studentIndex(students) {
  const byNo = new Map()
  const byName = new Map()
  for (const s of students || []) {
    byNo.set(String(s.student_no), s)
    const k = String(s.name).trim()
    byName.set(k, byName.has(k) ? null : s) // null = 重名
  }
  return function find(text) {
    const t = String(text ?? '').trim()
    if (!t) return null
    const m = /^(\S+)\s+(.+)$/.exec(t)
    if (m && byNo.has(m[1]) && byNo.get(m[1]).name === m[2].trim()) return byNo.get(m[1])
    if (byName.get(t)) return byName.get(t)
    if (byNo.has(t)) return byNo.get(t)
    return null
  }
}

/** 一段 CSS：每个小组一个底色（按 data-g 属性），只作用在 scope 这个容器里 */
export function groupCss(scope, groups) {
  return (groups || [])
    .map(
      g =>
        `${scope} td[data-g="${CSS.escape(String(g.id))}"]{background-color:${g.color} !important;font-weight:600}`
    )
    .join('\n')
}

/**
 * 长按拖动：在 el（表格外框）里按住一个格子 holdMs 毫秒不动，就「抓起」它，
 * 拖到别的格子松开 → onDrop(fromTd, toTd)。按下后马上挪动超过 slop 像素就当普通框选，不抓。
 *
 * 和表格库的配合：抓起的那一刻发一个 mouseup 让表格库结束它的框选；之后的 mousemove / mouseup
 * 在 window 的捕获阶段就截下来，表格库（挂在 document 上）收不到，不会跟着框选。
 */
export function attachLongPressDrag(el, { canStart, onDrop, label, holdMs = 280, slop = 6 }) {
  let timer = null
  let start = null
  let from = null
  let over = null
  let ghost = null
  let dragging = false
  let synthetic = false

  const tdAt = (x, y) => {
    const n = document.elementFromPoint(x, y)
    const td = n && n.closest ? n.closest('td[data-x][data-y]') : null
    return td && el.contains(td) ? td : null
  }

  function cleanup() {
    clearTimeout(timer)
    timer = null
    window.removeEventListener('mousemove', move, true)
    window.removeEventListener('mouseup', up, true)
    from?.classList.remove('seat-drag-from')
    over?.classList.remove('seat-drop')
    ghost?.remove()
    document.body.classList.remove('seat-dragging')
    from = over = ghost = null
    dragging = false
  }

  function begin() {
    timer = null
    dragging = true
    synthetic = true
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    synthetic = false
    window.getSelection?.().removeAllRanges()
    from.classList.add('seat-drag-from')
    document.body.classList.add('seat-dragging')
    ghost = document.createElement('div')
    ghost.className = 'seat-ghost'
    ghost.textContent = label(from)
    document.body.appendChild(ghost)
    place(start[0], start[1])
  }

  function place(x, y) {
    if (ghost) ghost.style.transform = `translate(${x + 12}px, ${y + 12}px)`
  }

  function down(e) {
    if (e.button !== 0 || dragging) return
    const td = e.target.closest ? e.target.closest('td[data-x][data-y]') : null
    if (!td || !el.contains(td) || !canStart(td)) return
    start = [e.clientX, e.clientY]
    from = td
    timer = setTimeout(begin, holdMs)
    window.addEventListener('mousemove', move, true)
    window.addEventListener('mouseup', up, true)
  }

  function move(e) {
    if (!dragging) {
      if (timer && Math.hypot(e.clientX - start[0], e.clientY - start[1]) > slop) cleanup()
      return
    }
    e.stopPropagation()
    e.preventDefault()
    place(e.clientX, e.clientY)
    const td = tdAt(e.clientX, e.clientY)
    if (td !== over) {
      over?.classList.remove('seat-drop')
      over = td && td !== from ? td : null
      over?.classList.add('seat-drop')
    }
  }

  function up(e) {
    if (synthetic) return
    if (!dragging) return cleanup()
    e.stopPropagation()
    e.preventDefault()
    const src = from
    const dst = tdAt(e.clientX, e.clientY)
    cleanup()
    if (dst && dst !== src) onDrop(src, dst)
  }

  function key(e) {
    if (e.key === 'Escape' && (dragging || timer)) cleanup()
  }

  el.addEventListener('mousedown', down, true)
  window.addEventListener('keydown', key)
  return () => {
    cleanup()
    el.removeEventListener('mousedown', down, true)
    window.removeEventListener('keydown', key)
  }
}

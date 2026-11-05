/**
 * 在线座次 ⇄ Excel（2.20.1）。
 *
 * 把 ExcelJS 读出来的工作表**逐格照搬**成在线座次的表格 JSON：值、合并、字体（字体名 /
 * 字号 / 加粗 / 斜体 / 下划线 / 颜色）、底色、四边边框、水平 + 垂直对齐、换行、列宽、行高。
 * 不往里加东西，也不改用户的格式 —— 老师拿 WPS / Excel 画好的座次表导进来要和原表一样。
 *
 * 不依赖 Vue，单独一个文件，方便在 node 里拿真实的 xlsx 测（scripts 里没挂，测法见更新日志）。
 */

export function colLetters(i) {
  let out = ''
  i += 1
  while (i) {
    const rem = (i - 1) % 26
    out = String.fromCharCode(65 + rem) + out
    i = Math.floor((i - 1) / 26)
  }
  return out
}
export const cellName = (x, y) => `${colLetters(x)}${y + 1}`
export function parseCell(name) {
  const m = /^([A-Z]+)(\d+)$/.exec(String(name).toUpperCase())
  if (!m) return null
  let x = 0
  for (const ch of m[1]) x = x * 26 + (ch.charCodeAt(0) - 64)
  return [x - 1, Number(m[2]) - 1]
}

const MAX_ROWS = 200
const MAX_COLS = 60

// ---------------- 颜色 ----------------
// Office 默认主题色（读不到文件自带主题时用）。顺序是 Excel 引用主题色的下标：lt1 dk1 lt2 dk2 accent1-6 hlink folHlink
const DEFAULT_THEME = ['FFFFFF', '000000', 'E7E6E6', '44546A', '4472C4', 'ED7D31', 'A5A5A5', 'FFC000', '5B9BD5', '70AD47', '0563C1', '954F72']
// 老式调色板里常见的几个（WPS 存文件常带 indexed=64 表示「自动」= 黑字）
const INDEXED = { 8: '000000', 9: 'FFFFFF', 10: 'FF0000', 11: '00FF00', 12: '0000FF', 13: 'FFFF00', 14: 'FF00FF', 15: '00FFFF', 64: '000000' }

function themeColors(wb) {
  const xml = wb && wb._themes && Object.values(wb._themes)[0]
  if (typeof xml !== 'string') return DEFAULT_THEME
  const scheme = /<a:clrScheme[\s\S]*?<\/a:clrScheme>/.exec(xml)
  if (!scheme) return DEFAULT_THEME
  const pick = tag => {
    const m = new RegExp(`<a:${tag}>[\\s\\S]*?(?:srgbClr val="([0-9A-Fa-f]{6})"|lastClr="([0-9A-Fa-f]{6})")`).exec(scheme[0])
    return m ? (m[1] || m[2]).toUpperCase() : null
  }
  const tags = ['lt1', 'dk1', 'lt2', 'dk2', 'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6', 'hlink', 'folHlink']
  return tags.map((t, i) => pick(t) || DEFAULT_THEME[i])
}

function applyTint(hex6, tint) {
  if (!tint) return hex6
  const ch = [0, 2, 4].map(i => parseInt(hex6.slice(i, i + 2), 16))
  const out = ch.map(c => Math.round(tint < 0 ? c * (1 + tint) : c + (255 - c) * tint))
  return out.map(c => Math.max(0, Math.min(255, c)).toString(16).padStart(2, '0')).join('').toUpperCase()
}

function colorOf(c, theme) {
  if (!c) return ''
  let hex6 = ''
  if (c.argb && /^[0-9A-Fa-f]{8}$/.test(c.argb)) hex6 = c.argb.slice(2)
  else if (c.argb && /^[0-9A-Fa-f]{6}$/.test(c.argb)) hex6 = c.argb
  else if (c.theme != null && theme[c.theme]) hex6 = theme[c.theme]
  else if (c.indexed != null && INDEXED[c.indexed]) hex6 = INDEXED[c.indexed]
  if (!hex6) return ''
  return '#' + applyTint(hex6.toUpperCase(), c.tint)
}

// ---------------- 值 ----------------
/**
 * 格子里显示的字。**不能直接用 cell.text**：合并区域里除左上角以外的格子，ExcelJS 取 text
 * 时会去读左上角的值，左上角是空的就对 null 调 toString 崩掉（2.20.0 导入用户空表报的
 * 「Cannot read properties of null (reading 'toString')」就是这个）。
 */
export function cellText(cell) {
  if (cell.isMerged && cell.master && cell.master !== cell) return ''
  const v = cell.value
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') {
    try {
      return cell.text == null ? String(v) : String(cell.text)
    } catch {
      return String(v)
    }
  }
  if (v instanceof Date) {
    try {
      return String(cell.text)
    } catch {
      return v.toISOString().slice(0, 10)
    }
  }
  if (typeof v === 'object') {
    if (Array.isArray(v.richText)) return v.richText.map(t => t.text || '').join('')
    if ('formula' in v || 'sharedFormula' in v || 'result' in v) {
      const r = v.result
      if (r == null) return ''
      if (typeof r === 'object') return r.error || (r instanceof Date ? r.toISOString().slice(0, 10) : '')
      return String(r)
    }
    if (v.text != null) return typeof v.text === 'string' ? v.text : (v.text.richText || []).map(t => t.text || '').join('')
    if (v.error) return String(v.error)
  }
  return ''
}

// ---------------- 样式 ----------------
const H_ALIGN = { left: 'left', center: 'center', right: 'right', centerContinuous: 'center', justify: 'justify', distributed: 'justify', fill: 'left' }
const V_ALIGN = { top: 'top', middle: 'middle', center: 'middle', bottom: 'bottom', justify: 'middle', distributed: 'middle' }

function borderCss(b, theme) {
  if (!b || !b.style) return ''
  const width = { thin: 1, hair: 1, dotted: 1, dashed: 1, dashDot: 1, dashDotDot: 1, medium: 2, mediumDashed: 2, mediumDashDot: 2, mediumDashDotDot: 2, slantDashDot: 2, thick: 3, double: 3 }[b.style] || 1
  const line = b.style === 'double' ? 'double' : /dot/i.test(b.style) && !/dash/i.test(b.style) ? 'dotted' : /dash/i.test(b.style) ? 'dashed' : 'solid'
  return `${width}px ${line} ${colorOf(b.color, theme) || '#000000'}`
}

function fontCss(f, theme, css) {
  if (!f) return
  if (f.name) css.push(`font-family:"${String(f.name).replace(/"/g, '')}"`)
  if (f.size) css.push(`font-size:${Math.round((f.size * 4) / 3)}px`)
  if (f.bold) css.push('font-weight:bold')
  if (f.italic) css.push('font-style:italic')
  const deco = []
  if (f.underline && f.underline !== 'none') deco.push('underline')
  if (f.strike) deco.push('line-through')
  if (deco.length) css.push(`text-decoration:${deco.join(' ')}`)
  const fc = colorOf(f.color, theme)
  if (fc) css.push(`color:${fc}`)
}

function fillCss(fill, theme, css) {
  if (!fill || fill.type !== 'pattern' || !fill.pattern || fill.pattern === 'none') return
  // 实心填充看前景色；其余花纹没法在网页上画，取前景色当底色最接近
  const bg = colorOf(fill.fgColor, theme) || colorOf(fill.bgColor, theme)
  if (bg) css.push(`background-color:${bg}`)
}

/** 合并区域里除左上角以外的格子名 */
export function coveredCells(mergeCells) {
  const out = new Set()
  Object.entries(mergeCells || {}).forEach(([name, [w, h]]) => {
    const p = parseCell(name)
    if (!p) return
    for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) if (dx || dy) out.add(cellName(p[0] + dx, p[1] + dy))
  })
  return out
}

// ---------------- 主函数 ----------------
/**
 * ExcelJS Workbook → 表格 JSON（{ data, mergeCells, style, colWidths, rowHeights }）。
 * 范围按「有字 / 有边框 / 有底色 / 在合并区域里 / 设了行高」收，WPS 常把列定义写到第 258 列，
 * 不能照 dimension 带出几百列空列。
 */
export function sheetFromWorkbook(wb) {
  const sheet = wb.worksheets[0]
  if (!sheet) throw new Error('这个文件里没有工作表')
  const theme = themeColors(wb)

  // ---- 收范围 ----
  const merges = []
  for (const m of sheet.model.merges || []) {
    const [a, z] = String(m).split(':')
    const p1 = parseCell(a)
    const p2 = parseCell(z || a)
    if (p1 && p2) merges.push([Math.min(p1[0], p2[0]), Math.min(p1[1], p2[1]), Math.max(p1[0], p2[0]), Math.max(p1[1], p2[1])])
  }
  let maxX = 0
  let maxY = 0
  sheet.eachRow({ includeEmpty: true }, (row, r) => {
    if (r > MAX_ROWS) return
    if (row.height) maxY = Math.max(maxY, r - 1)
    row.eachCell({ includeEmpty: false }, (cell, c) => {
      if (c > MAX_COLS) return
      const st = cell.style || {}
      const hasBorder = st.border && Object.values(st.border).some(b => b && b.style)
      const hasFill = st.fill && st.fill.type === 'pattern' && st.fill.pattern && st.fill.pattern !== 'none'
      if (cellText(cell).trim() || hasBorder || hasFill) {
        maxX = Math.max(maxX, c - 1)
        maxY = Math.max(maxY, r - 1)
      }
    })
  })
  for (const [, , x2, y2] of merges) {
    if (x2 < MAX_COLS) maxX = Math.max(maxX, x2)
    if (y2 < MAX_ROWS) maxY = Math.max(maxY, y2)
  }
  const cols = Math.min(maxX + 1, MAX_COLS)
  const rows = Math.min(maxY + 1, MAX_ROWS)

  // ---- 合并 ----
  const mergeCells = {}
  const mergeAt = {}
  for (const [x1, y1, x2, y2] of merges) {
    if (x1 >= cols || y1 >= rows) continue
    const w = Math.min(x2, cols - 1) - x1 + 1
    const h = Math.min(y2, rows - 1) - y1 + 1
    if (w > 1 || h > 1) {
      mergeCells[cellName(x1, y1)] = [w, h]
      mergeAt[cellName(x1, y1)] = [x1, y1, x1 + w - 1, y1 + h - 1]
    }
  }

  // ---- 逐格 ----
  const data = Array.from({ length: rows }, () => Array(cols).fill(''))
  const style = {}
  const at = (x, y) => sheet.getRow(y + 1).getCell(x + 1)
  const covered = coveredCells(mergeCells)
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const cell = at(x, y)
      data[y][x] = cellText(cell)
      // 合并区域里被盖住的格子不带样式：表格库把它们的样式也套在左上角那格上，
      // 会把左上角的居中冲成靠左（讲台 F19:H19 就这样歪过）。它们的边框已经并进左上角了
      if (covered.has(cellName(x, y))) continue
      const st = cell.style || {}
      const css = []
      fillCss(st.fill, theme, css)
      fontCss(st.font, theme, css)
      const al = st.alignment || {}
      css.push(`text-align:${H_ALIGN[al.horizontal] || (typeof cell.value === 'number' ? 'right' : 'left')}`)
      css.push(`vertical-align:${V_ALIGN[al.vertical] || 'bottom'}`)
      // 换行不写进样式：表格每列都开了自动换行（pre-wrap），原表里的回车照样分行，
      // 一键排座写进去的「学号 + 姓名」在窄格子里也能折下来，不会被截掉
      if (al.indent) css.push(`padding-left:${al.indent * 9}px`)
      // 边框：合并区域的右 / 下边框存在最右列 / 最下行的格子上，要从那里取
      const box = mergeAt[cellName(x, y)]
      const b = st.border || {}
      const sides = { top: b.top, left: b.left, right: b.right, bottom: b.bottom }
      if (box) {
        sides.right = (at(box[2], y).style.border || {}).right || sides.right
        sides.bottom = (at(x, box[3]).style.border || {}).bottom || sides.bottom
      }
      for (const side of ['top', 'right', 'bottom', 'left']) {
        const v = borderCss(sides[side], theme)
        if (v) css.push(`border-${side}:${v}`)
      }
      style[cellName(x, y)] = css.join(';') + ';'
    }
  }

  // ---- 列宽、行高 ----
  // Excel 列宽单位是「字符」，换成像素 ≈ 宽 × 7 + 5；行高是磅，× 4/3 是像素
  const defW = sheet.properties?.defaultColWidth || 9
  const defH = sheet.properties?.defaultRowHeight || 15
  const colWidths = []
  for (let c = 1; c <= cols; c++) {
    const col = sheet.getColumn(c)
    const w = col.hidden ? 0 : col.width || defW
    colWidths.push(Math.max(8, Math.round(w * 7 + 5)))
  }
  const rowHeights = {}
  for (let r = 1; r <= rows; r++) {
    const h = sheet.getRow(r).height || defH
    rowHeights[r - 1] = Math.max(8, Math.round((h * 4) / 3))
  }
  return { data, mergeCells, style, colWidths, rowHeights, imported: true }
}

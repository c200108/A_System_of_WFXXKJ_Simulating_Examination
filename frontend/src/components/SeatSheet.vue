<script setup>
/**
 * 在线座次（2.20.0）：每个班一张可编辑的座次表。
 *
 * 表格本体用 Jspreadsheet CE（MIT），读写 Excel 座次样式用 ExcelJS（MIT）。两个库都
 * 只在打开这个组件时才下载（Classes.vue 里 defineAsyncComponent 懒加载），平时的页面
 * 不背这几百 KB。局域网版不能联网，库都打包进 web/，不走 CDN。选型理由见
 * docs/更新日志/2.20.0.md。
 *
 * 一键导入本班学生：区域、排法交给服务端算（/api/classes/{id}/seat-plan，
 * services/seating.py），这里只负责把「哪个格子放谁」填进表格。学困生标记是学生隐私，
 * 表格里**不标**谁是学困生，导出、打印也就不会带出去。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import jspreadsheet from 'jspreadsheet-ce'
import 'jsuites/dist/jsuites.css'
import 'jspreadsheet-ce/dist/jspreadsheet.css'
import { api, download } from '../api'

const props = defineProps({
  cls: { type: Object, required: true },        // 班级行（id / display / seat_kind / seat_name）
  height: { type: Number, default: 520 }         // 表格区域高度（像素），面板全屏时会变
})
const emit = defineEmits(['saved'])

const host = ref(null)
const fileInput = ref(null)
const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const canEdit = ref(false)
const students = ref([])
const lastSel = ref('')           // 表格上最近一次框选的区域，如 B2:D5
let ws = null                     // 当前工作表实例

const DEFAULT_COLS = 12
const DEFAULT_ROWS = 14

// ---------------- 单元格名 ----------------
function colLetters(i) {
  let out = ''
  i += 1
  while (i) {
    const rem = (i - 1) % 26
    out = String.fromCharCode(65 + rem) + out
    i = Math.floor((i - 1) / 26)
  }
  return out
}
const cellName = (x, y) => `${colLetters(x)}${y + 1}`
function parseCell(name) {
  const m = /^([A-Z]+)(\d+)$/.exec(String(name).toUpperCase())
  if (!m) return null
  let x = 0
  for (const ch of m[1]) x = x * 26 + (ch.charCodeAt(0) - 64)
  return [x - 1, Number(m[2]) - 1]
}

// ---------------- 建表 ----------------
function blankSheet() {
  const data = Array.from({ length: DEFAULT_ROWS }, () => Array(DEFAULT_COLS).fill(''))
  data[0][0] = '讲　台'
  return {
    data,
    mergeCells: { A1: [DEFAULT_COLS, 1] },
    style: { A1: 'text-align:center;font-weight:bold;background-color:#eef3ff;' },
    colWidths: Array(DEFAULT_COLS).fill(90),
    rowHeights: {},
    seatRanges: '',
    zoneRanges: ''
  }
}

function build(sheet) {
  destroy()
  const s = sheet || blankSheet()
  const cols = Math.max(DEFAULT_COLS, ...(s.data || []).map(r => r.length), (s.colWidths || []).length)
  const rows = Math.max(DEFAULT_ROWS, (s.data || []).length)
  const rowsCfg = {}
  Object.entries(s.rowHeights || {}).forEach(([i, h]) => (rowsCfg[i] = { height: h }))
  const sheets = jspreadsheet(host.value, {
    tabs: false,
    // 自带工具栏的图标走 Google 的 Material Icons 字体（要联网），局域网版显示成一串英文 ——
    // 不用它，上面自己做了加粗、对齐、颜色几个按钮
    toolbar: false,
    worksheets: [
      {
        data: s.data && s.data.length ? s.data : [['']],
        minDimensions: [cols, rows],
        mergeCells: s.mergeCells || {},
        style: s.style || {},
        columns: Array.from({ length: cols }, (_, i) => ({
          width: (s.colWidths || [])[i] || 90,
          align: 'center',
          wordWrap: true
        })),
        rows: rowsCfg,
        editable: canEdit.value,
        tableOverflow: true,
        tableWidth: '100%',
        tableHeight: `${props.height}px`,
        defaultColAlign: 'center'
      }
    ],
    onselection: (_inst, x1, y1, x2, y2) => {
      const a = cellName(Math.min(x1, x2), Math.min(y1, y2))
      const b = cellName(Math.max(x1, x2), Math.max(y1, y2))
      lastSel.value = a === b ? a : `${a}:${b}`
    },
    onchange: () => (dirty.value = true),
    onmerge: () => (dirty.value = true),
    onchangestyle: () => (dirty.value = true),
    onresizecolumn: () => (dirty.value = true),
    onresizerow: () => (dirty.value = true),
    oninsertrow: () => (dirty.value = true),
    oninsertcolumn: () => (dirty.value = true),
    ondeleterow: () => (dirty.value = true),
    ondeletecolumn: () => (dirty.value = true)
  })
  ws = sheets[0]
  form.ranges = s.seatRanges || form.ranges
  form.zone = s.zoneRanges || form.zone
  dirty.value = false
}

function destroy() {
  if (host.value && ws) {
    try {
      jspreadsheet.destroy(host.value, true)
    } catch {
      /* 已经没了 */
    }
  }
  ws = null
  if (host.value) host.value.innerHTML = ''
}

/** 把表格现在的样子收成一份 JSON（存服务器、导出 Excel、打印都用它）。 */
function snapshot() {
  const data = ws.getData()
  const widths = ws.getWidth()
  const heights = ws.getHeight()
  const rowHeights = {}
  ;(heights || []).forEach((h, i) => {
    const n = parseInt(h, 10)
    if (n && n !== 26) rowHeights[i] = n
  })
  const style = {}
  Object.entries(ws.getStyle() || {}).forEach(([k, v]) => {
    if (v && String(v).trim()) style[k] = v
  })
  return {
    version: 1,
    data,
    mergeCells: ws.getMerge() || {},
    style,
    colWidths: (widths || []).map(w => parseInt(w, 10) || 90),
    rowHeights,
    seatRanges: form.ranges,
    zoneRanges: form.zone
  }
}

// ---------------- 读写服务器 ----------------
async function load() {
  loading.value = true
  try {
    const got = await api.classSeatSheet(props.cls.id)
    canEdit.value = got.can_edit
    students.value = got.students || []
    await nextTick()
    build(got.sheet)
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!ws) return
  saving.value = true
  try {
    const got = await api.classSeatSheetSave(props.cls.id, snapshot())
    dirty.value = false
    emit('saved', got)
    ElMessage.success('座次表已保存')
  } finally {
    saving.value = false
  }
}

async function clearAll() {
  await ElMessageBox.confirm('清空整张座次表，重新从空白开始？（保存之后才生效）', '清空', { type: 'warning' })
  build(blankSheet())
  dirty.value = true
}

// ---------------- 导入 Excel 座次样式 ----------------
function argb(c) {
  const v = c && c.argb
  return v && /^[0-9A-Fa-f]{8}$/.test(v) ? '#' + v.slice(2) : ''
}

/** Excel（ExcelJS 读出来的第一张表）→ 我们的表格 JSON：值、合并、填充色、字体、对齐、边框、列宽行高。 */
async function fromExcel(buffer) {
  const ExcelJS = (await import('exceljs')).default
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(buffer)
  const sheet = wb.worksheets[0]
  if (!sheet) throw new Error('这个文件里没有工作表')
  const rows = Math.min(Math.max(sheet.rowCount, 1), 200)
  const cols = Math.min(Math.max(sheet.columnCount, 1), 60)
  const data = Array.from({ length: rows }, () => Array(cols).fill(''))
  const style = {}
  for (let r = 1; r <= rows; r++) {
    const row = sheet.getRow(r)
    for (let c = 1; c <= cols; c++) {
      const cell = row.getCell(c)
      data[r - 1][c - 1] = cell.text == null ? '' : String(cell.text)
      const css = []
      const fill = cell.fill
      if (fill && fill.type === 'pattern' && fill.pattern === 'solid') {
        const bg = argb(fill.fgColor)
        if (bg) css.push(`background-color:${bg}`)
      }
      const f = cell.font || {}
      if (f.bold) css.push('font-weight:bold')
      if (f.italic) css.push('font-style:italic')
      if (argb(f.color)) css.push(`color:${argb(f.color)}`)
      if (f.size) css.push(`font-size:${Math.round((f.size * 4) / 3)}px`)
      const al = cell.alignment || {}
      if (al.horizontal && ['left', 'center', 'right'].includes(al.horizontal)) {
        css.push(`text-align:${al.horizontal}`)
      }
      const b = cell.border || {}
      for (const side of ['top', 'right', 'bottom', 'left']) {
        if (b[side] && b[side].style) {
          const w = ['medium', 'thick', 'double'].includes(b[side].style) ? 2 : 1
          css.push(`border-${side}:${w}px solid ${argb(b[side].color) || '#333'}`)
        }
      }
      if (css.length) style[cellName(c - 1, r - 1)] = css.join(';') + ';'
    }
  }
  const mergeCells = {}
  for (const m of sheet.model.merges || []) {
    const [a, z] = m.split(':')
    const p1 = parseCell(a)
    const p2 = parseCell(z || a)
    if (!p1 || !p2) continue
    if (p1[0] >= cols || p1[1] >= rows) continue
    mergeCells[cellName(p1[0], p1[1])] = [p2[0] - p1[0] + 1, p2[1] - p1[1] + 1]
  }
  const colWidths = []
  for (let c = 1; c <= cols; c++) {
    const w = sheet.getColumn(c).width
    colWidths.push(w ? Math.round(w * 7 + 5) : 90)
  }
  const rowHeights = {}
  for (let r = 1; r <= rows; r++) {
    const h = sheet.getRow(r).height
    if (h) rowHeights[r - 1] = Math.round((h * 4) / 3)
  }
  return { data, mergeCells, style, colWidths, rowHeights, seatRanges: form.ranges, zoneRanges: form.zone }
}

async function askOverwrite(what) {
  if (!dirty.value && !hasContent()) return
  await ElMessageBox.confirm(`${what}会替换掉现在的整张座次表，确定吗？`, '导入座次样式', { type: 'warning' })
}

function hasContent() {
  return !!ws && ws.getData().some(r => r.some(v => String(v ?? '').trim() && v !== '讲　台'))
}

function pickExcel() {
  fileInput.value.value = ''
  fileInput.value.click()
}

async function onExcel(e) {
  const file = e.target.files?.[0]
  if (!file) return
  if (!/\.xlsx$/i.test(file.name)) return ElMessage.warning('只认 .xlsx（老的 .xls 先用 Excel / WPS 另存为 .xlsx）')
  await askOverwrite(`导入「${file.name}」`)
  try {
    build(await fromExcel(await file.arrayBuffer()))
    dirty.value = true
    ElMessage.success('已导入座次样式，看过没问题点「保存」')
  } catch (err) {
    ElMessage.error(`读不了这个文件：${err.message || err}`)
  }
}

/** 原来上传过 Excel 座次表的班：直接导进来。图片没法变成表格，只能照着画。 */
async function importUploaded() {
  await askOverwrite(`导入已上传的「${props.cls.seat_name}」`)
  const blob = await api.classSeatFile(props.cls.id)
  try {
    build(await fromExcel(await blob.arrayBuffer()))
    dirty.value = true
    ElMessage.success('已导入原来上传的座次表，看过没问题点「保存」')
  } catch (err) {
    ElMessage.error(`读不了原来上传的座次表（.xls 老格式要先另存为 .xlsx）：${err.message || err}`)
  }
}

// ---------------- 导出 Excel / 打印 ----------------
function cssMap(text) {
  const out = {}
  String(text || '')
    .split(';')
    .forEach(kv => {
      const i = kv.indexOf(':')
      if (i > 0) out[kv.slice(0, i).trim().toLowerCase()] = kv.slice(i + 1).trim()
    })
  return out
}
const hex = v => {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(v || '').trim())
  return m ? 'FF' + m[1].toUpperCase() : ''
}

async function exportExcel() {
  const s = snapshot()
  const ExcelJS = (await import('exceljs')).default
  const wb = new ExcelJS.Workbook()
  const sheet = wb.addWorksheet('座次表')
  s.data.forEach((row, y) =>
    row.forEach((v, x) => {
      if (v !== '' && v != null) sheet.getCell(y + 1, x + 1).value = v
    })
  )
  s.colWidths.forEach((w, i) => (sheet.getColumn(i + 1).width = Math.max(4, Math.round((w - 5) / 7))))
  Object.entries(s.rowHeights).forEach(([i, h]) => (sheet.getRow(Number(i) + 1).height = Math.round((h * 3) / 4)))
  Object.entries(s.style).forEach(([name, text]) => {
    const p = parseCell(name)
    if (!p) return
    const cell = sheet.getCell(p[1] + 1, p[0] + 1)
    const css = cssMap(text)
    if (hex(css['background-color'])) {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: hex(css['background-color']) } }
    }
    const font = {}
    if (css['font-weight'] === 'bold') font.bold = true
    if (hex(css.color)) font.color = { argb: hex(css.color) }
    if (css['font-size']) font.size = Math.round((parseInt(css['font-size'], 10) * 3) / 4) || undefined
    if (Object.keys(font).length) cell.font = font
    const border = {}
    for (const side of ['top', 'right', 'bottom', 'left']) {
      if (css[`border-${side}`]) border[side] = { style: 'thin' }
    }
    if (Object.keys(border).length) cell.border = border
  })
  for (let y = 0; y < s.data.length; y++) {
    for (let x = 0; x < (s.data[y] || []).length; x++) {
      const cell = sheet.getCell(y + 1, x + 1)
      cell.alignment = { horizontal: cssMap(s.style[cellName(x, y)])['text-align'] || 'center', vertical: 'middle', wrapText: true }
    }
  }
  Object.entries(s.mergeCells).forEach(([name, [w, h]]) => {
    const p = parseCell(name)
    if (p && (w > 1 || h > 1)) sheet.mergeCells(p[1] + 1, p[0] + 1, p[1] + h, p[0] + w)
  })
  const buf = await wb.xlsx.writeBuffer()
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  await download(Promise.resolve(blob), `${props.cls.display}座次表.xlsx`)
}

function printSheet() {
  const s = snapshot()
  const covered = new Set()
  Object.entries(s.mergeCells).forEach(([name, [w, h]]) => {
    const p = parseCell(name)
    for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) if (dx || dy) covered.add(cellName(p[0] + dx, p[1] + dy))
  })
  // 打印只到最后一个有内容的行列，别把一大片空格子印出来
  let maxY = 0
  let maxX = 0
  s.data.forEach((row, y) =>
    row.forEach((v, x) => {
      if (String(v ?? '').trim() || s.style[cellName(x, y)]) {
        maxY = Math.max(maxY, y)
        maxX = Math.max(maxX, x)
      }
    })
  )
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
  let html = '<table>'
  for (let y = 0; y <= maxY; y++) {
    html += `<tr style="height:${s.rowHeights[y] || 34}px">`
    for (let x = 0; x <= maxX; x++) {
      const name = cellName(x, y)
      if (covered.has(name)) continue
      const m = s.mergeCells[name]
      const span = m ? ` colspan="${m[0]}" rowspan="${m[1]}"` : ''
      html += `<td${span} style="width:${s.colWidths[x] || 90}px;${esc(s.style[name] || '')}">${esc((s.data[y] || [])[x])}</td>`
    }
    html += '</tr>'
  }
  html += '</table>'
  const w = window.open('', '_blank')
  if (!w) return ElMessage.warning('浏览器拦住了打印窗口，请允许弹出窗口')
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(props.cls.display)}座次表</title>
<style>body{font-family:"Microsoft YaHei",sans-serif;margin:16px}h2{text-align:center;font-size:18px}
table{border-collapse:collapse;margin:0 auto}td{border:1px solid #888;text-align:center;font-size:14px;padding:2px 4px}</style>
</head><body><h2>${esc(props.cls.display)} 上机座次表</h2>${html}</body></html>`)
  w.document.close()
  w.focus()
  setTimeout(() => w.print(), 300)
}

// ---------------- 样式：加粗、对齐、颜色（作用于选中的格子） ----------------
const bg = ref('#fff3c4')
const fg = ref('#c0392b')
function selCells() {
  if (!lastSel.value) {
    ElMessage.info('先在表格上框选格子')
    return []
  }
  return expandRanges(lastSel.value)
}
function styleSel(key, value) {
  const cells = selCells()
  if (!cells.length) return
  if (key === 'font-weight') {
    const on = String(ws.getStyle(cells[0], 'font-weight') || '') === 'bold'
    value = on ? 'normal' : 'bold'
  }
  const o = {}
  cells.forEach(c => (o[c] = `${key}:${value}`))
  ws.setStyle(o)
  dirty.value = true
}
function borderSel() {
  const cells = selCells()
  if (!cells.length) return
  const o = {}
  cells.forEach(c => (o[c] = 'border:1px solid #333'))
  ws.setStyle(o)
  dirty.value = true
}
function clearStyleSel() {
  const cells = selCells()
  if (!cells.length) return
  const o = {}
  cells.forEach(c => (o[c] = ''))
  ws.resetStyle(o)
  dirty.value = true
}

// ---------------- 合并单元格 ----------------
function mergeSel() {
  if (!lastSel.value || !lastSel.value.includes(':')) return ElMessage.info('先在表格上框选要合并的几个格子')
  const [a, b] = lastSel.value.split(':').map(parseCell)
  ws.setMerge(cellName(a[0], a[1]), b[0] - a[0] + 1, b[1] - a[1] + 1)
  dirty.value = true
}
function unmergeSel() {
  if (!lastSel.value) return
  const a = parseCell(lastSel.value.split(':')[0])
  try {
    ws.removeMerge(cellName(a[0], a[1]))
    dirty.value = true
  } catch {
    ElMessage.info('选中的左上角不是合并单元格')
  }
}

// ---------------- 一键导入本班学生 ----------------
const dlg = ref(false)
const planning = ref(false)
const form = reactive({
  ranges: '',
  zone: '',
  shuffle: true,
  alternate_gender: false,
  struggling_zone: false,
  content: 'name'
})
const weakCount = computed(() => students.value.filter(s => s.struggling).length)

function useSelection(key) {
  if (!lastSel.value) return ElMessage.info('先在表格上框选一块区域（可以框好几次，每次点一下这个按钮）')
  form[key] = form[key].trim() ? `${form[key].trim()}, ${lastSel.value}` : lastSel.value
}

/** 合并单元格里除了左上角以外的格子不能当座位 */
function mergedSkip() {
  const out = []
  Object.entries(ws.getMerge() || {}).forEach(([name, [w, h]]) => {
    const p = parseCell(name)
    for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) if (dx || dy) out.push(cellName(p[0] + dx, p[1] + dy))
  })
  return out
}

async function runPlan() {
  if (!form.ranges.trim()) return ElMessage.warning('先写要放学生的区域，比如 B2:B15, A4:H4')
  planning.value = true
  let got
  try {
    got = await api.classSeatPlan(props.cls.id, {
      ...form,
      skip: mergedSkip(),
      seed: `${Date.now()}-${Math.random()}`
    })
  } finally {
    planning.value = false
  }
  // 要填的格子里已经有字：重新排之前先问一句
  const filled = got.assignments.filter(a => {
    const p = parseCell(a.cell)
    return String(ws.getValueFromCoords(p[0], p[1]) ?? '').trim()
  }).length
  if (filled) {
    await ElMessageBox.confirm(`这些座位里已经有 ${filled} 个格子写了字，重新排会覆盖掉，确定吗？`, '重新排座位', {
      type: 'warning',
      confirmButtonText: '覆盖并重新排'
    })
  }
  // 区域里的座位先清空（多出来的座位要留空），再填人
  const seatsAll = new Set(got.assignments.map(a => a.cell))
  for (const name of expandRanges(form.ranges)) {
    if (!seatsAll.has(name)) {
      const p = parseCell(name)
      if (p) ws.setValueFromCoords(p[0], p[1], '', true)
    }
  }
  for (const a of got.assignments) {
    const p = parseCell(a.cell)
    ws.setValueFromCoords(p[0], p[1], a.text, true)
  }
  dirty.value = true
  dlg.value = false
  const tip = got.warnings.length ? '\n\n' + got.warnings.join('\n') : ''
  ElMessageBox.alert(`排好了 ${got.assignments.length} 位同学（共 ${got.seats} 个座位）。看过没问题点「保存」。${tip}`, '一键导入本班学生')
}

/** 前端也展开一遍区域（只用来清空多余座位；真正的规则在服务端 seating.py） */
function expandRanges(text) {
  const out = []
  for (const part of String(text).split(/[\s,，;；、]+/).filter(Boolean)) {
    const [a, b] = part.replace('：', ':').split(':')
    const p1 = parseCell(a)
    const p2 = parseCell(b || a)
    if (!p1 || !p2) continue
    for (let y = Math.min(p1[1], p2[1]); y <= Math.max(p1[1], p2[1]); y++) {
      for (let x = Math.min(p1[0], p2[0]); x <= Math.max(p1[0], p2[0]); x++) out.push(cellName(x, y))
    }
  }
  return out
}

watch(
  () => props.height,
  h => {
    const box = host.value?.querySelector('.jss_content')
    if (box) box.style.maxHeight = `${h}px`
  }
)

onMounted(load)
onBeforeUnmount(destroy)
defineExpose({ dirty, save })
</script>

<template>
  <div class="seat-sheet" v-loading="loading">
    <input ref="fileInput" type="file" accept=".xlsx" hidden @change="onExcel" />
    <div class="tools">
      <template v-if="canEdit">
        <el-button type="primary" size="small" @click="dlg = true">一键导入本班学生</el-button>
        <el-button size="small" @click="pickExcel">导入 Excel 座次样式</el-button>
        <el-button v-if="cls.seat_kind === 'sheet'" size="small" @click="importUploaded">
          导入已上传的「{{ cls.seat_name }}」
        </el-button>
        <el-divider direction="vertical" />
        <el-button size="small" @click="styleSel('font-weight')"><b>加粗</b></el-button>
        <el-button size="small" @click="styleSel('text-align', 'left')">左</el-button>
        <el-button size="small" @click="styleSel('text-align', 'center')">中</el-button>
        <el-button size="small" @click="styleSel('text-align', 'right')">右</el-button>
        <el-color-picker v-model="bg" size="small" title="底色" />
        <el-button size="small" @click="styleSel('background-color', bg || '#ffffff')">填底色</el-button>
        <el-color-picker v-model="fg" size="small" title="字色" />
        <el-button size="small" @click="styleSel('color', fg || '#000000')">改字色</el-button>
        <el-button size="small" @click="borderSel">加边框</el-button>
        <el-button size="small" @click="clearStyleSel">清样式</el-button>
        <el-divider direction="vertical" />
        <el-button size="small" @click="mergeSel">合并选中格</el-button>
        <el-button size="small" @click="unmergeSel">取消合并</el-button>
        <el-button size="small" @click="clearAll">清空</el-button>
        <el-divider direction="vertical" />
      </template>
      <el-button size="small" @click="exportExcel">导出 Excel</el-button>
      <el-button size="small" @click="printSheet">打印</el-button>
      <div class="flex-1" />
      <span v-if="lastSel" class="sel">选中 <b>{{ lastSel }}</b></span>
      <el-button v-if="canEdit" type="success" size="small" :loading="saving" @click="save">
        {{ dirty ? '保存 *' : '保存' }}
      </el-button>
      <span v-if="!canEdit" class="muted">不是你带的班，只能看</span>
    </div>
    <p v-if="canEdit" class="hint">
      双击格子改字；框选几个格子后，用上面的按钮加粗、对齐、填底色、加边框、合并；右键能插入 / 删除行列。原来上传的是图片的话，照着图在这里画一遍再「一键导入本班学生」。
    </p>
    <div ref="host" class="host" />

    <el-dialog v-model="dlg" title="一键导入本班学生" width="560px" append-to-body>
      <el-form label-width="96px" size="small">
        <el-form-item label="放在哪些格子">
          <el-input v-model="form.ranges" type="textarea" :rows="2" placeholder="如 B2:B15, A4:H4, A1:D5（可以写好几段、不连续）" />
          <div class="row">
            <el-button size="small" link type="primary" @click="useSelection('ranges')">
              + 加入表格上选中的 {{ lastSel || '区域' }}
            </el-button>
            <span class="muted">按区域先后、区域里先行后列排</span>
          </div>
        </el-form-item>
        <el-form-item label="格子里写">
          <el-radio-group v-model="form.content">
            <el-radio value="name">姓名</el-radio>
            <el-radio value="no_name">学号 + 姓名</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="排法">
          <el-radio-group v-model="form.shuffle">
            <el-radio :value="true">随机分座</el-radio>
            <el-radio :value="false">按学号顺序</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="男女交错">
          <el-switch v-model="form.alternate_gender" />
          <span class="muted sw">相邻座位尽量一男一女；没填性别的同学照样排</span>
        </el-form-item>
        <el-form-item label="学困生区域">
          <el-switch v-model="form.struggling_zone" />
          <span class="muted sw">本班标了 {{ weakCount }} 位学困生（在「学生管理」里设，学生自己看不到）</span>
        </el-form-item>
        <el-form-item v-if="form.struggling_zone" label="固定区域">
          <el-input v-model="form.zone" placeholder="如 A2:D3，学困生优先排进这里" />
          <el-button size="small" link type="primary" @click="useSelection('zone')">
            + 加入表格上选中的 {{ lastSel || '区域' }}
          </el-button>
        </el-form-item>
        <p class="muted">本班在用的学生 {{ students.length }} 人。排好后先看一眼，再点「保存」。</p>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="planning" @click="runPlan">排座位</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}
.tools :deep(.el-button + .el-button) {
  margin-left: 0;
}
.flex-1 {
  flex: 1;
}
.sel {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.sw {
  margin-left: 10px;
}
.row {
  display: flex;
  gap: 10px;
  align-items: center;
}
.host {
  width: 100%;
  overflow: auto;
}
.host :deep(.jss_container) {
  max-width: 100%;
}
</style>

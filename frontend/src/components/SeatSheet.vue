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
import { cellName, coveredCells, parseCell, sheetFromWorkbook } from './seatExcel'
import { attachLongPressDrag, groupCss, studentIndex } from './seatBoard'
import SeatMenu from './SeatMenu.vue'
import SeatGroups from './SeatGroups.vue'

const props = defineProps({
  cls: { type: Object, required: true },        // 班级行（id / display / seat_kind / seat_name）
  wide: { type: Boolean, default: false }       // 面板全屏：表格和右边一栏拉开一点
})
const emit = defineEmits(['saved', 'roles'])

const host = ref(null)
const fileInput = ref(null)
const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const canEdit = ref(false)
const students = ref([])
const lastSel = ref('')           // 表格上最近一次框选的区域，如 B2:D5
let ws = null                     // 当前工作表实例

// ---------------- 座位板：小组、得分、班干部（seatBoard.js） ----------------
const uid = `s${Math.random().toString(36).slice(2, 8)}`
const groups = reactive([])       // [{ id, name, color }]，跟座次表一起存
const groupOf = reactive({})      // { 学生 id: 组 id }，小组跟着人走
const points = reactive({})       // { 学生 id: 总分 }，存在服务器（/points），加减立即生效
const finder = computed(() => studentIndex(students.value))
const studentAt = (x, y) => (ws ? finder.value(ws.getValueFromCoords(x, y)) : null)
const broken = reactive({})       // { 格子名: 说明 }：设备故障、不可入座的座位，跟座次表一起存

// ---------------- 缩放（只改显示，不改座次表；每人自己记在浏览器里） ----------------
const ZOOMS = [50, 60, 70, 80, 90, 100, 110, 125, 150, 175, 200]
const zoom = ref(100)
try {
  zoom.value = Number(localStorage.getItem('seat-zoom')) || 100
} catch {
  /* 无痕模式读不了就用 100% */
}
function applyZoom() {
  const box = host.value?.querySelector('.jss_container')
  if (box) box.style.zoom = zoom.value === 100 ? '' : String(zoom.value / 100)
  fitHeight()
  try {
    localStorage.setItem('seat-zoom', String(zoom.value))
  } catch {
    /* 存不了也没关系 */
  }
}
function stepZoom(d) {
  // 「适应」算出来的比例（如 69%）不在档位里：往上 / 往下找最近的一档
  const next = d > 0 ? ZOOMS.find(z => z > zoom.value) : [...ZOOMS].reverse().find(z => z < zoom.value)
  if (next) zoom.value = next
  applyZoom()
}
const zoomOptions = computed(() => [...new Set([...ZOOMS, zoom.value])].sort((a, b) => a - b))
/** 按表格区的宽高算一个刚好放得下整张表的比例 */
function fitZoom() {
  const box = host.value?.querySelector('.jss_container')
  const table = host.value?.querySelector('.jss_content table')
  if (!box || !table) return
  box.style.zoom = ''
  const side = host.value.parentElement.querySelector('.logs')
  const room = host.value.parentElement.clientWidth - (side ? side.offsetWidth + (props.wide ? 50 : 20) : 0)
  const sw = room / (table.offsetWidth + 4)
  const sh = host.value.clientHeight / (table.offsetHeight + 4)
  const best = Math.floor(Math.min(sw, sh, 2) * 100)
  zoom.value = Math.max(50, Math.min(200, best))
  applyZoom()
}

const DEFAULT_COLS = 12
const DEFAULT_ROWS = 14
const tableH = ref(400)           // 表格可见高度：跟着面板实际剩下的空间走（ResizeObserver）

// ---------------- 建表 ----------------
/** 读不到默认空表时的兜底：一行讲台 + 空格子 */
function fallbackSheet() {
  const data = Array.from({ length: DEFAULT_ROWS }, () => Array(DEFAULT_COLS).fill(''))
  data[0][0] = '讲　台'
  return {
    data,
    mergeCells: { A1: [DEFAULT_COLS, 1] },
    style: { A1: 'text-align:center;font-weight:bold;background-color:#eef3ff;' },
    colWidths: Array(DEFAULT_COLS).fill(90),
    rowHeights: {}
  }
}

/**
 * 没画过座次表的班默认用 public/seat-default.xlsx（学校给的空表，2.20.1）。
 * 打包进前端，局域网版不联网也有；读一次缓存下来。
 */
let templateCache = null
async function defaultSheet() {
  if (!templateCache) {
    try {
      const res = await fetch(`${import.meta.env.BASE_URL}seat-default.xlsx`, { cache: 'no-cache' })
      if (!res.ok) throw new Error(res.status)
      templateCache = await fromExcel(await res.arrayBuffer())
    } catch {
      templateCache = fallbackSheet()
    }
  }
  return JSON.parse(JSON.stringify(templateCache))
}

function build(sheet) {
  destroy()
  const s = sheet || fallbackSheet()
  // 行列数照表格本身来，不再硬凑 12 × 14：导入的表几行几列就是几行几列
  const cols = Math.max(1, ...(s.data || []).map(r => r.length), (s.colWidths || []).length)
  const rows = Math.max(1, (s.data || []).length)
  const rowsCfg = {}
  // 表格库直接把 height 塞进 style.height，必须带 px，光写数字浏览器不认（2.20.1 及以前行高因此一直没生效）
  Object.entries(s.rowHeights || {}).forEach(([i, h]) => (rowsCfg[i] = { height: `${parseInt(h, 10)}px` }))
  // 合并区域里被盖住的格子的样式会被表格库叠到左上角那格上，去掉
  const covered = coveredCells(s.mergeCells)
  const style = {}
  Object.entries(s.style || {}).forEach(([k, v]) => {
    if (!covered.has(k)) style[k] = v
  })
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
        style,
        columns: Array.from({ length: cols }, (_, i) => ({
          width: (s.colWidths || [])[i] || 90,
          align: 'center',
          wordWrap: true
        })),
        rows: rowsCfg,
        editable: canEdit.value,
        tableOverflow: true,
        tableHeight: `${tableH.value}px`,
        defaultColAlign: 'center'
      }
    ],
    onselection: (_inst, x1, y1, x2, y2) => {
      const a = cellName(Math.min(x1, x2), Math.min(y1, y2))
      const b = cellName(Math.max(x1, x2), Math.max(y1, y2))
      lastSel.value = a === b ? a : `${a}:${b}`
    },
    onchange: () => {
      dirty.value = true
      decorate()
    },
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
  // 小组是跟人走的：导入 Excel 样式、清空表格时 s 里没有小组，就留着原来的
  if (s.groups) groups.splice(0, groups.length, ...s.groups)
  if (s.groupOf) {
    Object.keys(groupOf).forEach(k => delete groupOf[k])
    Object.assign(groupOf, s.groupOf)
  }
  if (s.broken) {
    Object.keys(broken).forEach(k => delete broken[k])
    Object.assign(broken, s.broken)
  }
  decorate()
  applyZoom()
  form.ranges = s.seatRanges || form.ranges
  form.zone = s.zoneRanges || form.zone
  dirty.value = false
  fitHeight()
}

/** 表格可见高度 = 外框剩下的高度。面板拉大缩小、全屏还原都会触发 */
function fitHeight() {
  const h = host.value?.clientHeight
  if (!h) return
  tableH.value = Math.max(160, h)
  const box = host.value.querySelector('.jss_content')
  if (box) {
    // 缩放（zoom）连滚动区的 max-height 一起缩，要除回去，滚动区才正好占满表格区
    box.style.maxHeight = `${Math.floor(tableH.value / (zoom.value / 100))}px`
    box.style.height = 'auto'
  }
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
    if (n) rowHeights[i] = n
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
    zoneRanges: form.zone,
    groups: groups.map(g => ({ ...g })),
    groupOf: { ...groupOf },
    broken: { ...broken }
  }
}

// ---------------- 读写服务器 ----------------
async function load() {
  loading.value = true
  try {
    const got = await api.classSeatSheet(props.cls.id)
    canEdit.value = got.can_edit
    students.value = got.students || []
    if (got.can_edit) loadPoints()
    await nextTick()
    build(got.sheet || (await defaultSheet()))
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
  await ElMessageBox.confirm('清空整张座次表，换回默认空表重新开始？（保存之后才生效）', '清空', { type: 'warning' })
  build(await defaultSheet())
  dirty.value = true
}

// ---------------- 导入 Excel 座次样式 ----------------
/** Excel → 表格 JSON。逐格照搬，规则全在 seatExcel.js */
async function fromExcel(buffer) {
  const ExcelJS = (await import('exceljs')).default
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(buffer)
  return { ...sheetFromWorkbook(wb), seatRanges: form.ranges, zoneRanges: form.zone }
}

async function askOverwrite(what) {
  if (!dirty.value && !props.cls.has_seat_sheet && !hasContent()) return
  await ElMessageBox.confirm(`${what}会替换掉现在的整张座次表，确定吗？`, '导入座次样式', { type: 'warning' })
}

/** 表格里有没有学生名字（默认空表里本来就有的座位号、讲台不算） */
function hasContent() {
  if (!ws) return false
  const base = new Set((templateCache?.data || []).flat().map(v => String(v ?? '').trim()))
  return ws.getData().some(r => r.some(v => String(v ?? '').trim() && !base.has(String(v).trim()) && v !== '讲　台'))
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
    if (css['font-family']) font.name = css['font-family'].replace(/["']/g, '')
    if (css['font-weight'] === 'bold') font.bold = true
    if (css['font-style'] === 'italic') font.italic = true
    if (/underline/.test(css['text-decoration'] || '')) font.underline = true
    if (/line-through/.test(css['text-decoration'] || '')) font.strike = true
    if (hex(css.color)) font.color = { argb: hex(css.color) }
    if (css['font-size']) font.size = Math.round((parseFloat(css['font-size']) * 3) / 4) || undefined
    if (Object.keys(font).length) cell.font = font
    const border = {}
    for (const side of ['top', 'right', 'bottom', 'left']) {
      const v = css[`border-${side}`]
      if (!v || /none|^0/.test(v)) continue
      const w = parseInt(v, 10) || 1
      const style = /double/.test(v) ? 'double' : /dashed/.test(v) ? 'dashed' : /dotted/.test(v) ? 'dotted' : w >= 3 ? 'thick' : w === 2 ? 'medium' : 'thin'
      const color = hex((/#[0-9a-f]{6}/i.exec(v) || [])[0])
      border[side] = color ? { style, color: { argb: color } } : { style }
    }
    if (css.border && !/none|^0/.test(css.border)) {
      for (const side of ['top', 'right', 'bottom', 'left']) border[side] = border[side] || { style: 'thin' }
    }
    if (Object.keys(border).length) cell.border = border
  })
  const V = { top: 'top', middle: 'middle', bottom: 'bottom' }
  for (let y = 0; y < s.data.length; y++) {
    for (let x = 0; x < (s.data[y] || []).length; x++) {
      const cell = sheet.getCell(y + 1, x + 1)
      const css = cssMap(s.style[cellName(x, y)])
      cell.alignment = {
        horizontal: css['text-align'] || 'center',
        vertical: V[css['vertical-align']] || 'middle',
        wrapText: true
      }
    }
  }
  Object.entries(s.mergeCells).forEach(([name, [w, h]]) => {
    const p = parseCell(name)
    if (p && (w > 1 || h > 1)) sheet.mergeCells(p[1] + 1, p[0] + 1, p[1] + h, p[0] + w)
  })
  // 小组底色也带进 Excel（座次表本身没填底色的格子才用）
  Object.entries(groupFills(s)).forEach(([name, color]) => {
    const p = parseCell(name)
    const cell = sheet.getCell(p[1] + 1, p[0] + 1)
    if (!cell.fill || cell.fill.type !== 'pattern' || cell.fill.pattern !== 'solid') {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: hex(color) } }
    }
  })
  const buf = await wb.xlsx.writeBuffer()
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  await download(Promise.resolve(blob), `${props.cls.display}座次表.xlsx`)
}

function printSheet() {
  const s = snapshot()
  const fills = groupFills(s)
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
  // 表格自己画了边框（导入的 Excel、默认空表）就照它的来；一条边框都没有的老表才给每格补细线
  const ownBorders = Object.values(s.style).some(v => /border/.test(v))
  let html = `<table class="${ownBorders ? 'own' : ''}">`
  for (let y = 0; y <= maxY; y++) {
    html += `<tr style="height:${s.rowHeights[y] || 34}px">`
    for (let x = 0; x <= maxX; x++) {
      const name = cellName(x, y)
      if (covered.has(name)) continue
      const m = s.mergeCells[name]
      const span = m ? ` colspan="${m[0]}" rowspan="${m[1]}"` : ''
      const bk = s.broken && s.broken[name] !== undefined
      const gc = bk ? 'background-color:#eeeeee;color:#999;' : fills[name] ? `background-color:${fills[name]};` : ''
      html += `<td${span} style="width:${s.colWidths[x] || 90}px;${esc(s.style[name] || '')}${gc}">${bk ? `设备故障${s.broken[name] ? '：' + esc(s.broken[name]) : ''}` : esc((s.data[y] || [])[x])}</td>`
    }
    html += '</tr>'
  }
  html += '</table>'
  const w = window.open('', '_blank')
  if (!w) return ElMessage.warning('浏览器拦住了打印窗口，请允许弹出窗口')
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(props.cls.display)}座次表</title>
<style>body{font-family:"Microsoft YaHei",sans-serif;margin:16px}h2{text-align:center;font-size:18px}
table{border-collapse:collapse;margin:0 auto}td{border:1px solid #888;text-align:center;vertical-align:middle;font-size:14px;padding:2px 4px;white-space:pre-wrap}
table.own td{border:none}</style>
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

/**
 * 自动认座位（2.22.0）：表里写着座位号（A1、B12、C3 这种「字母 + 数字」）的格子，
 * 它右边那一格就是座位。按座位号排（A1、A2 … A16、B1 …、C1 …），连着往下的几格并成一段（B3:B18），
 * 区域写得短。右边那格写着别的字（不是学生）、是合并格被盖住的部分，就不算。
 */
const SEAT_LABEL = /^([A-Za-z]{1,2})\s*-?\s*(\d{1,3})$/
function detectSeats() {
  if (!ws) return []
  const data = ws.getData()
  const covered = new Set(mergedSkip())
  const found = []
  data.forEach((row, y) =>
    row.forEach((v, x) => {
      const m = SEAT_LABEL.exec(String(v ?? '').trim())
      if (!m || x + 1 >= row.length) return
      const seat = cellName(x + 1, y)
      if (covered.has(seat)) return
      const right = String(row[x + 1] ?? '').trim()
      if (right && (SEAT_LABEL.test(right) || !finder.value(right))) return
      found.push({ cell: seat, x: x + 1, y, key: [m[1].toUpperCase(), Number(m[2])] })
    })
  )
  found.sort((a, b) => (a.key[0] === b.key[0] ? a.key[1] - b.key[1] : a.key[0] < b.key[0] ? -1 : 1))
  return found
}
/** 认出来的座位 → 区域文字：同一列连着往下的并成 B3:B18 */
function seatsToRanges(list) {
  const parts = []
  let run = null
  for (const s of list) {
    if (run && s.x === run.x && s.y === run.y2 + 1) run.y2 = s.y
    else {
      if (run) parts.push(run)
      run = { x: s.x, y1: s.y, y2: s.y }
    }
  }
  if (run) parts.push(run)
  return parts.map(r => (r.y1 === r.y2 ? cellName(r.x, r.y1) : `${cellName(r.x, r.y1)}:${cellName(r.x, r.y2)}`)).join(', ')
}
const detected = ref(0)
function autoSeats(quiet = false) {
  const list = detectSeats()
  detected.value = list.length
  if (!list.length) {
    if (!quiet) ElMessage.warning('表里没认出座位号（A1、B2 这种）。手动框选要放学生的格子再「加入」也行')
    return
  }
  form.ranges = seatsToRanges(list)
  const nBroken = list.filter(s => broken[s.cell] !== undefined).length
  if (!quiet) {
    ElMessage.success(`认出 ${list.length} 个座位（座位号右边的格子）${nBroken ? `，其中 ${nBroken} 个设备故障会跳过` : ''}`)
  }
}
function openPlan() {
  // 第一次打开、还没写区域：先按座位号自动认一遍
  if (!form.ranges.trim()) autoSeats(true)
  dlg.value = true
}

async function runPlan() {
  if (!form.ranges.trim()) return ElMessage.warning('先写要放学生的区域，比如 B2:B15, A4:H4，或点「自动识别座位」')
  planning.value = true
  let got
  try {
    got = await api.classSeatPlan(props.cls.id, {
      ...form,
      // 合并格被盖住的部分、设备故障的座位都不排人
      skip: [...mergedSkip(), ...Object.keys(broken)],
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

// ================================================================ 座位板交互
/** 哪些格子坐着分了组的学生 → 小组底色（打印、导出 Excel 用） */
function groupFills(s) {
  const color = Object.fromEntries(groups.map(g => [String(g.id), g.color]))
  const out = {}
  s.data.forEach((row, y) =>
    row.forEach((v, x) => {
      const st = finder.value(v)
      const c = st && color[String(groupOf[st.id] || '')]
      if (c) out[cellName(x, y)] = c
    })
  )
  return out
}

/** 给格子挂上 data-*：小组底色、班干部、分数角标都靠 CSS 读这几个属性显示，不写进格子样式 */
let decoFrame = 0
function decorate() {
  // 用 setTimeout 不用 requestAnimationFrame：窗口在后台时 rAF 会停，切回来角标才出来
  clearTimeout(decoFrame)
  decoFrame = setTimeout(() => {
    if (!ws || !host.value) return
    const set = (el, k, v) => (v ? el.setAttribute(k, v) : el.removeAttribute(k))
    const live = new Set(groups.map(g => String(g.id)))
    host.value.querySelectorAll('.jss_content td[data-x][data-y]').forEach(td => {
      const st = studentAt(Number(td.dataset.x), Number(td.dataset.y))
      const p = st ? points[st.id] || 0 : 0
      const g = st ? String(groupOf[st.id] || '') : ''
      set(td, 'data-sid', st ? String(st.id) : '')
      set(td, 'data-g', live.has(g) ? g : '')
      set(td, 'data-role', st ? st.class_role || '' : '')
      set(td, 'data-pts', p ? (p > 0 ? `+${p}` : String(p)) : '')
      const bk = broken[cellName(Number(td.dataset.x), Number(td.dataset.y))]
      set(td, 'data-broken', bk === undefined ? '' : bk || '设备故障')
      const gname = live.has(g) ? groups.find(x => String(x.id) === g)?.name : ''
      set(
        td,
        'title',
        st
          ? [st.name, st.class_role, gname, canEdit.value ? `${p > 0 ? '+' : ''}${p} 分` : '', canEdit.value ? '长按拖动换座 · 右键更多' : '']
              .filter(Boolean)
              .join(' · ')
          : ''
      )
    })
  }, 16)
}

// ---- 小组底色：生成一段 CSS（只认 data-g），挂在 <head> 里 ----
let groupStyle = null
watch(
  groups,
  () => {
    if (groupStyle) groupStyle.textContent = groupCss(`.seat-sheet[data-uid="${uid}"]`, groups)
    decorate()
  },
  { deep: true }
)
watch(groupOf, decorate, { deep: true })
watch(students, decorate, { deep: true })
watch(broken, decorate, { deep: true })

// ---- 长按拖动换座 ----
const xy = td => [Number(td.dataset.x), Number(td.dataset.y)]
function onDrop(fromTd, toTd) {
  const [fx, fy] = xy(fromTd)
  const [tx, ty] = xy(toTd)
  const a = ws.getValueFromCoords(fx, fy)
  const b = ws.getValueFromCoords(tx, ty)
  const sa = finder.value(a)
  const sb = finder.value(b)
  if (String(b ?? '').trim() && !sb) {
    return ElMessage.warning(`${cellName(tx, ty)} 写着「${String(b).trim()}」，不是学生座位，换不过去`)
  }
  if (broken[cellName(tx, ty)] !== undefined) {
    return ElMessage.warning(`${cellName(tx, ty)} 设备故障（${broken[cellName(tx, ty)] || '不可入座'}），不能坐`)
  }
  ws.setValueFromCoords(tx, ty, a, true)
  ws.setValueFromCoords(fx, fy, b ?? '', true)
  dirty.value = true
  decorate()
  ElMessage.success(sb ? `${sa.name} ⇄ ${sb.name} 互换了座位` : `${sa.name} 换到了 ${cellName(tx, ty)}`)
}

// ---- 右键学生：加减分、班干部、小组 ----
// mode：student 一位学生 / batch 框选了好几位 / seat 空座位（设备故障）
const menu = reactive({ open: false, x: 0, y: 0, mode: 'student', student: null, batch: [], cell: null, seat: '' })
const menuTotal = computed(() => (menu.student ? points[menu.student.id] || 0 : 0))
const inSel = (x, y) => expandRanges(lastSel.value).includes(cellName(x, y))
const isSeatCell = (x, y) => detectSeats().some(s => s.x === x && s.y === y)
function onContext(e) {
  if (!canEdit.value || !ws) return
  const td = e.target.closest ? e.target.closest('td[data-x][data-y]') : null
  if (!td || !host.value.contains(td)) return
  const [x, y] = xy(td)
  const st = studentAt(x, y)
  const name = cellName(x, y)
  const base = { open: true, x: e.clientX, y: e.clientY, cell: [x, y], seat: name, student: st, batch: [] }
  // 右键点在框选区域里、区域里有两位以上学生：批量菜单
  if (inSel(x, y)) {
    const list = selectedStudents()
    if (list.length > 1) {
      e.preventDefault()
      e.stopPropagation()
      return Object.assign(menu, base, { mode: 'batch', batch: list, student: null })
    }
  }
  if (st) {
    e.preventDefault()
    e.stopPropagation()
    return Object.assign(menu, base, { mode: 'student' })
  }
  // 空座位（座位号旁边那格）或已标故障的格子：设备故障菜单；其他格子照旧给表格自己的菜单（插入删除行列）
  if (!String(ws.getValueFromCoords(x, y) ?? '').trim() && (broken[name] !== undefined || isSeatCell(x, y))) {
    e.preventDefault()
    e.stopPropagation()
    return Object.assign(menu, base, { mode: 'seat' })
  }
}
/** 右键按下时如果点在框选区域里，别让表格库把选区改成这一格（批量菜单要用整片选区） */
function onRightDown(e) {
  if (e.button !== 2 || !ws) return
  const td = e.target.closest ? e.target.closest('td[data-x][data-y]') : null
  if (td && host.value.contains(td) && inSel(...xy(td))) e.stopPropagation()
}

// ---- 批量：框选的几位学生一起加减分、分组 ----
async function addPointsBulk(delta, reason = '', list = menu.batch) {
  const got = await api.classPointBulk(props.cls.id, { student_ids: list.map(s => s.id), delta, reason })
  Object.entries(got.totals || {}).forEach(([k, v]) => (points[k] = v))
  decorate()
  ElMessage({
    type: delta > 0 ? 'success' : 'warning',
    message: `${list.length} 位同学各 ${delta > 0 ? '+' : ''}${delta} 分${reason ? `（${reason}）` : ''}`
  })
}
function onMenuPoints(delta) {
  return menu.mode === 'batch' ? addPointsBulk(delta) : addPoints(delta)
}

// ---- 设备故障：座位标成不可入座，一键排座、拖动换座都跳过它 ----
async function markBroken(cells) {
  const list = cells.filter(n => broken[n] === undefined)
  if (!list.length) return
  const seated = list
    .map(n => parseCell(n))
    .map(p => studentAt(p[0], p[1]))
    .filter(Boolean)
  const { value } = await ElMessageBox.prompt(
    `${list.length === 1 ? list[0] : `${list.length} 个座位`}标成设备故障、不可入座。可以写一句是什么问题（显示在格子里）：` +
      (seated.length ? `\n\n上面坐着 ${seated.map(s => s.name).join('、')}，会先请他们离开这个座位。` : ''),
    '设备故障',
    { inputPlaceholder: '如：显示器不亮、键盘坏了', inputValue: '', confirmButtonText: '标成故障' }
  )
  for (const n of list) {
    const p = parseCell(n)
    if (studentAt(p[0], p[1])) ws.setValueFromCoords(p[0], p[1], '', true)
    broken[n] = String(value || '').trim().slice(0, 20)
  }
  dirty.value = true
  ElMessage.success(`已标 ${list.length} 个座位设备故障，排座位时会跳过`)
}
function clearBroken(cells) {
  const list = cells.filter(n => broken[n] !== undefined)
  list.forEach(n => delete broken[n])
  if (list.length) {
    dirty.value = true
    ElMessage.success(`${list.length} 个座位修好了，可以坐人`)
  }
}
/** 工具栏按钮：选中的格子里有没标的就标故障，全都标了就取消 */
function toggleBrokenSel() {
  if (!lastSel.value) return ElMessage.info('先在表格上框选座位（座位号右边的格子），再点「设备故障」')
  const cells = expandRanges(lastSel.value)
  if (cells.every(n => broken[n] !== undefined)) return clearBroken(cells)
  return markBroken(cells)
}

async function loadPoints() {
  try {
    const got = await api.classPoints(props.cls.id)
    Object.keys(points).forEach(k => delete points[k])
    Object.entries(got.totals || {}).forEach(([k, v]) => (points[k] = v))
    decorate()
  } catch {
    /* 没权限就不显示分数 */
  }
}

async function addPoints(delta, reason = '', who = menu.student) {
  const got = await api.classPointAdd(props.cls.id, { student_id: who.id, delta, reason })
  points[who.id] = got.total
  decorate()
  ElMessage({
    type: delta > 0 ? 'success' : 'warning',
    message: `${who.name} ${delta > 0 ? '+' : ''}${delta} 分${reason ? `（${reason}）` : ''}，现在 ${got.total} 分`
  })
}

async function customPoints() {
  const who = menu.student
  const batch = menu.mode === 'batch' ? menu.batch : null
  const { value } = await ElMessageBox.prompt(
    '先写分值，后面可以跟原因，如「+3 回答问题」「-2 上课说话」',
    batch ? `给选中的 ${batch.length} 位同学一起加减分` : `给 ${who.name} 加减分`,
    {
      inputPlaceholder: '+3 回答问题',
      inputValidator: v => /^\s*[+\-－]?\d{1,3}(\s|$)/.test(v || '') || '开头写分值，如 +3 或 -2'
    }
  )
  const m = /^\s*([+\-－]?)(\d{1,3})\s*(.*)$/.exec(value)
  const delta = (m[1] === '-' || m[1] === '－' ? -1 : 1) * Number(m[2])
  if (!delta) return ElMessage.warning('分值不能是 0')
  if (Math.abs(delta) > 100) return ElMessage.warning('一次最多加减 100 分')
  if (batch) return addPointsBulk(delta, m[3].slice(0, 64), batch)
  await addPoints(delta, m[3].slice(0, 64), who)
}

const hist = reactive({ open: false, student: null, rows: [], loading: false })
async function openHistory() {
  Object.assign(hist, { open: true, student: menu.student, rows: [], loading: true })
  try {
    const got = await api.classPoints(props.cls.id)
    hist.rows = (got.recent || []).filter(r => r.student_id === hist.student.id)
  } finally {
    hist.loading = false
  }
}
async function undoPoint(row) {
  const got = await api.classPointUndo(props.cls.id, row.id)
  points[got.student_id] = got.total
  hist.rows = hist.rows.filter(r => r.id !== row.id)
  decorate()
  ElMessage.success(`已撤销，${hist.student.name} 现在 ${got.total} 分`)
}

async function setRole(role) {
  const who = menu.student
  await api.studentUpdate(who.id, { class_role: role })
  if (role === '班长') students.value.forEach(s => s.class_role === '班长' && (s.class_role = ''))
  who.class_role = role
  decorate()
  emit('roles')
  ElMessage.success(role ? `已设 ${who.name} 为${role}` : `已取消 ${who.name} 的班干部`)
}

const groupDlg = ref(false)
function setGroup(gid) {
  if (gid === '__manage') return (groupDlg.value = true)
  if (menu.mode === 'batch') {
    menu.batch.forEach(s => (gid ? (groupOf[s.id] = String(gid)) : delete groupOf[s.id]))
    dirty.value = true
    const g = groups.find(x => String(x.id) === String(gid))
    return ElMessage.success(`${menu.batch.length} 位同学${g ? `分到「${g.name}」` : '不分组了'}`)
  }
  const who = menu.student
  if (gid) groupOf[who.id] = String(gid)
  else delete groupOf[who.id]
  dirty.value = true
  const g = groups.find(x => String(x.id) === String(gid))
  ElMessage.success(g ? `${who.name} 分到「${g.name}」` : `${who.name} 不分组了`)
}
function selectedStudents() {
  const seen = new Map()
  for (const name of expandRanges(lastSel.value)) {
    const p = parseCell(name)
    const st = p && studentAt(p[0], p[1])
    if (st) seen.set(st.id, st)
  }
  return [...seen.values()]
}
function removeFromSeat() {
  const [x, y] = menu.cell
  ws.setValueFromCoords(x, y, '', true)
  dirty.value = true
  decorate()
}

/** 小组一览：每组几个人、组长、组内总分 */
const groupStats = computed(() =>
  groups.map(g => {
    const list = students.value.filter(s => String(groupOf[s.id] || '') === String(g.id))
    return {
      ...g,
      n: list.length,
      leader: list
        .filter(s => s.class_role === '组长')
        .map(s => s.name)
        .join('、'),
      pts: list.reduce((n, s) => n + (points[s.id] || 0), 0)
    }
  })
)

let detachDrag = null
let ro = null
onMounted(() => {
  ro = new ResizeObserver(() => fitHeight())
  if (host.value) {
    ro.observe(host.value)
    host.value.addEventListener('contextmenu', onContext, true)
    host.value.addEventListener('mousedown', onRightDown, true)
    detachDrag = attachLongPressDrag(host.value, {
      canStart: td => canEdit.value && !ws?.edition && !!studentAt(...xy(td)),
      onDrop,
      label: td => studentAt(...xy(td))?.name || ''
    })
  }
  groupStyle = document.createElement('style')
  document.head.appendChild(groupStyle)
  load()
})
onBeforeUnmount(() => {
  ro?.disconnect()
  detachDrag?.()
  host.value?.removeEventListener('contextmenu', onContext, true)
  host.value?.removeEventListener('mousedown', onRightDown, true)
  groupStyle?.remove()
  clearTimeout(decoFrame)
  destroy()
})
defineExpose({ dirty, save, students })
</script>

<template>
  <div class="seat-sheet" :class="{ wide }" :data-uid="uid" v-loading="loading">
    <input ref="fileInput" type="file" accept=".xlsx" hidden @change="onExcel" />
    <div class="tools">
      <template v-if="canEdit">
        <el-button type="primary" size="small" @click="openPlan">一键导入本班学生</el-button>
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
        <el-button size="small" @click="groupDlg = true">🎨 小组</el-button>
        <el-button size="small" title="框选座位后点：标成设备故障、不可入座；再点一次取消" @click="toggleBrokenSel">🔧 设备故障</el-button>
        <el-divider direction="vertical" />
      </template>
      <el-button size="small" @click="exportExcel">导出 Excel</el-button>
      <el-button size="small" @click="printSheet">打印</el-button>
      <el-divider direction="vertical" />
      <div class="zoom" title="只改显示大小，不影响座次表本身；每个人自己的设置">
        <el-button size="small" :disabled="zoom <= ZOOMS[0]" @click="stepZoom(-1)">－</el-button>
        <el-select v-model="zoom" size="small" style="width: 84px" @change="applyZoom">
          <el-option v-for="z in zoomOptions" :key="z" :label="`${z}%`" :value="z" />
        </el-select>
        <el-button size="small" :disabled="zoom >= ZOOMS[ZOOMS.length - 1]" @click="stepZoom(1)">＋</el-button>
        <el-button size="small" link type="primary" @click="fitZoom">适应</el-button>
      </div>
      <div class="flex-1" />
      <span v-if="lastSel" class="sel">选中 <b>{{ lastSel }}</b></span>
      <el-button v-if="canEdit" type="success" size="small" :loading="saving" @click="save">
        {{ dirty ? '保存 *' : '保存' }}
      </el-button>
      <span v-if="!canEdit" class="muted">不是你带的班，只能看</span>
    </div>
    <p v-if="canEdit" class="hint">
      <b>长按学生拖到别的座位</b>（那里有人就互换）；<b>右键学生</b>加减分、设班长 / 组长、分小组；
      <b>框选几位再右键</b>一起加减分、分组；右键空座位标<b>设备故障</b>；双击格子改字；右键其他格子插入 / 删除行列。
    </p>
    <!-- 小组一览：颜色、人数、组长、组内总分 -->
    <div v-if="groupStats.length" class="legend">
      <button
        v-for="g in groupStats"
        :key="g.id"
        type="button"
        class="lg"
        :style="{ background: g.color }"
        :title="g.leader ? `组长 ${g.leader}` : '还没设组长'"
        @click="groupDlg = true"
      >
        <b>{{ g.name }}</b> {{ g.n }} 人
        <template v-if="g.leader"> · ⭐{{ g.leader }}</template>
        <template v-if="canEdit && g.pts"> · {{ g.pts > 0 ? '+' : '' }}{{ g.pts }} 分</template>
      </button>
    </div>
    <!-- 表格 + 右边一栏（课堂日志，由外面塞进 side 插槽）：挨着放、中间留一道空，不连在一起 -->
    <div class="body">
      <div ref="host" class="host" />
      <slot name="side" />
    </div>

    <SeatMenu
      :open="menu.open"
      :x="menu.x"
      :y="menu.y"
      :mode="menu.mode"
      :student="menu.student"
      :batch="menu.batch"
      :seat="menu.seat"
      :seat-broken="broken[menu.seat]"
      :total="menuTotal"
      :groups="groups"
      :group-id="menu.student ? groupOf[menu.student.id] || '' : ''"
      @close="menu.open = false"
      @points="onMenuPoints"
      @broken="markBroken([menu.seat])"
      @fixed="clearBroken([menu.seat])"
      @custom="customPoints"
      @history="openHistory"
      @role="setRole"
      @group="setGroup"
      @remove="removeFromSeat"
    />
    <SeatGroups
      v-model="groupDlg"
      :groups="groups"
      :group-of="groupOf"
      :students="students"
      :selection="lastSel"
      :selected-students="selectedStudents"
      @changed="dirty = true"
    />
    <el-dialog v-model="hist.open" :title="`${hist.student?.name || ''} 的得分记录`" width="460px" append-to-body>
      <div v-loading="hist.loading">
        <p class="muted">现在 <b>{{ hist.student ? points[hist.student.id] || 0 : 0 }}</b> 分。点错了可以撤销那一笔。</p>
        <el-empty v-if="!hist.loading && !hist.rows.length" :image-size="50" description="还没有加减过分" />
        <div v-for="r in hist.rows" :key="r.id" class="hrow">
          <b :class="r.delta > 0 ? 'up' : 'down'">{{ r.delta > 0 ? '+' : '' }}{{ r.delta }}</b>
          <span class="hreason">{{ r.reason || '—' }}</span>
          <span class="muted">{{ r.author_name }} · {{ String(r.created_at).replace('T', ' ').slice(5, 16) }}</span>
          <el-button link size="small" type="danger" @click="undoPoint(r)">撤销</el-button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="dlg" title="一键导入本班学生" width="560px" append-to-body>
      <el-form label-width="96px" size="small">
        <el-form-item label="放在哪些格子">
          <el-input v-model="form.ranges" type="textarea" :rows="2" placeholder="如 B2:B15, A4:H4, A1:D5（可以写好几段、不连续）" />
          <div class="row">
            <el-button size="small" type="primary" plain @click="autoSeats()">🪑 自动识别座位</el-button>
            <span class="muted">
              认表里的座位号（A1、B12…）右边那格，按 A1→A16、B1… 的顺序排<template v-if="detected">，认出 {{ detected }} 个</template>；设备故障的座位自动跳过
            </span>
          </div>
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
/* 整个组件填满面板剩下的高度；表格区（host）的高度由外面定，不跟内容走，
   ResizeObserver 量它再把表格滚动区设成一样高 —— 面板多大表格就多大，不会撑出去 */
.seat-sheet {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.body {
  flex: 1 1 0;
  min-height: 160px;
  display: flex;
  gap: 14px;
}
/* 面板全屏：表格和课堂日志拉开一些，间距、日志栏宽度都跟着窗口宽度走 */
.seat-sheet.wide .body {
  gap: clamp(24px, 3vw, 64px);
}
.seat-sheet.wide .body > :deep(.logs) {
  flex-basis: clamp(330px, 24vw, 440px);
}
.zoom {
  display: flex;
  align-items: center;
  gap: 4px;
}
/* 设备故障的座位：灰色斜纹 + 说明，排座位、拖动换座都跳过 */
.host :deep(td[data-broken]) {
  position: relative;
  background-image: repeating-linear-gradient(45deg, rgba(245, 108, 108, 0.16) 0 6px, transparent 6px 12px) !important;
}
.host :deep(td[data-broken])::after {
  content: '🔧 ' attr(data-broken);
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 2px;
  font: 700 11px/1.2 sans-serif;
  color: #c45656;
  text-align: center;
  pointer-events: none;
}
/* 表格区宽度跟着表格走（不撑满），右边的日志栏就紧挨着表格；表格太宽时收窄、横向滚动 */
.host {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
}
.host :deep(.jss_container) {
  max-width: 100%;
}
.host :deep(.jss_content) {
  max-width: 100%;
}
/* ---- 座位板：学生格子上的角标（班干部、分数），靠 data-* 显示，不进座次表样式 ---- */
.host :deep(td[data-sid]) {
  position: relative;
  cursor: grab;
}
.host :deep(td[data-role])::before {
  position: absolute;
  top: 0;
  left: 1px;
  font: 9px/12px sans-serif;
  pointer-events: none;
}
/* 班干部用小图标，窄格子里也不挡名字；悬停格子 title 里有全称 */
.host :deep(td[data-role='班长'])::before {
  content: '👑';
}
.host :deep(td[data-role='组长'])::before {
  content: '⭐';
}
/* 分数角标放右下角、班干部图标放左上角：名字在格子正中，两个角是空的，不挡名字 */
.host :deep(td[data-pts])::after {
  content: attr(data-pts);
  position: absolute;
  right: 1px;
  bottom: 1px;
  padding: 0 3px;
  border-radius: 6px;
  font: 700 9px/12px sans-serif;
  background: #67c23a;
  color: #fff;
  pointer-events: none;
}
.host :deep(td[data-pts^='-'])::after {
  background: #f56c6c;
}
.host :deep(td.seat-drag-from) {
  opacity: 0.45;
  outline: 2px dashed var(--el-color-primary);
  outline-offset: -2px;
}
.host :deep(td.seat-drop) {
  outline: 3px solid var(--el-color-primary);
  outline-offset: -3px;
  box-shadow: inset 0 0 0 999px rgba(64, 158, 255, 0.12);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}
.lg {
  padding: 3px 10px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  font-size: 12px;
  color: #303133;
  cursor: pointer;
}
.hrow {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
}
.hrow .up {
  color: #529b2e;
  width: 34px;
}
.hrow .down {
  color: #c45656;
  width: 34px;
}
.hreason {
  flex: 1;
}
</style>

<style>
/* 拖动时跟着鼠标走的「学生名牌」，挂在 body 上，不能 scoped */
.seat-ghost {
  position: fixed;
  left: 0;
  top: 0;
  z-index: 4000;
  padding: 6px 14px;
  border-radius: 8px;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.25);
  pointer-events: none;
}
body.seat-dragging,
body.seat-dragging * {
  cursor: grabbing !important;
  user-select: none !important;
}
</style>

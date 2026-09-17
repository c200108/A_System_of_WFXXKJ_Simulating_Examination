<script setup>
/**
 * WPS 文字仿真（3.0 照着 WPS Office 的界面重做）。
 *
 * ## 文档模型：格式挂在段落上
 *
 *     { paras: [{ text, font, size, bold, align, indent, line, bullet, style… }],
 *       page: { left, right, top, bottom, orient }, header, footer, columns }
 *
 * 真 Word 的格式挂在「字符游程」上（同一段里可以半句楷体半句宋体）。这里刻意
 * 简化成按段落记 —— 中考的 WPS 题九成是「把标题设成楷体二号加粗居中」「把
 * 某段设成首行缩进 2 字符」，都是整段操作；按段落记既够用，判分断言也写得清楚。
 *
 * 代价：考「把文中某几个字设成红色」这类题它做不了。真要考，得把模型升级成
 * 游程，判分那边（services/sim.py 的 _check_wps）同步改。
 *
 * ## 界面
 *
 * 顶栏、选项卡、功能区的分组和按钮位置都照着 WPS 的「开始」选项卡摆。
 * 非「开始」的选项卡只画出来不做功能 —— 中考考的操作都在开始选项卡里，
 * 画出来是为了让学生找得到北，点进去会提示"这一栏本题用不到"。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps({
  env: { type: Object, required: true },
  modelValue: { type: Object, default: null },
  readonly: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'log'])

const TABS = ['开始', '插入', '页面', '引用', '审阅', '视图', '工具']
const FONTS = ['宋体', '黑体', '楷体', '仿宋', '微软雅黑', '隶书', '幼圆', '华文中宋',
               'Times New Roman', 'Arial', 'Calibri']
// 中文字号对应的磅值。判分那边有一份一样的表（services/sim.py 的 SIZE_ALIASES），
// 所以老师写「二号」还是写 22，两边都认得。
const SIZES = {
  初号: 42, 小初: 36, 一号: 26, 小一: 24, 二号: 22, 小二: 18, 三号: 16, 小三: 15,
  四号: 14, 小四: 12, 五号: 10.5, 小五: 9, 六号: 7.5, 小六: 6.5, 七号: 5.5, 八号: 5
}
const ALIGNS = [
  { v: 'left', t: '左对齐', i: '≡', c: 'l' },
  { v: 'center', t: '居中对齐', i: '≡', c: 'c' },
  { v: 'right', t: '右对齐', i: '≡', c: 'r' },
  { v: 'justify', t: '两端对齐', i: '≡', c: 'j' },
  { v: 'distribute', t: '分散对齐', i: '≡', c: 'd' }
]
// 样式：选中之后连字体字号一起套上，和 WPS 的「样式」一个意思
const STYLES = {
  正文: { font: '宋体', size: '五号', bold: false },
  标题1: { font: '黑体', size: '三号', bold: true },
  标题2: { font: '黑体', size: '四号', bold: true },
  标题3: { font: '黑体', size: '小四', bold: true }
}
const HIGHLIGHTS = ['', '#ffff00', '#00ff00', '#00ffff', '#ff00ff', '#c0c0c0']

const DEFAULT_PARA = {
  font: '宋体', size: '五号', bold: false, italic: false, underline: false,
  strike: false, sup: false, sub: false, color: '', highlight: '', shading: '',
  border: false, bullet: 'none', style: '正文',
  align: 'left', indent: 0, line: null, before: 0, after: 0
}

const doc = ref({ paras: [], page: {}, header: '', footer: '', columns: 1, name: '' })
const picked = ref([0])
const tab = ref('开始')
const marks = ref(false)          // 显示段落标记
const brush = ref(null)           // 格式刷吸到的格式
const paraClip = ref(null)        // 段落剪贴板

function boot() {
  const src = props.modelValue && props.modelValue.paras ? props.modelValue : props.env
  const copy = JSON.parse(JSON.stringify(src || {}))
  doc.value = {
    name: copy.name || '文档.wps',
    paras: (copy.paras || []).map(p => ({ ...DEFAULT_PARA, ...p })),
    page: { left: 3.18, right: 3.18, top: 2.54, bottom: 2.54, orient: 'portrait', ...(copy.page || {}) },
    header: copy.header || '',
    footer: copy.footer || '',
    columns: copy.columns || 1
  }
  if (!doc.value.paras.length) doc.value.paras = [{ text: '', ...DEFAULT_PARA }]
  picked.value = [0]
}
boot()
watch(() => props.env, boot)

function push(action) {
  emit('update:modelValue', JSON.parse(JSON.stringify(doc.value)))
  if (action) emit('log', { at: Date.now(), ...action })
}

// ---------- 选择 ----------
function select(i, e) {
  if (e && e.shiftKey && picked.value.length) {
    const from = picked.value[0]
    const [a, b] = from <= i ? [from, i] : [i, from]
    picked.value = Array.from({ length: b - a + 1 }, (_, k) => a + k)
  } else {
    picked.value = [i]
  }
  // 格式刷：吸了格式之后，点哪一段就刷哪一段，刷完自动松开
  if (brush.value && !props.readonly) {
    const patch = { ...brush.value }
    brush.value = null
    apply(patch, '格式刷')
  }
}
const cur = computed(() => doc.value.paras[picked.value[0]] || DEFAULT_PARA)

function apply(patch, name) {
  if (props.readonly) return
  picked.value.forEach(i => {
    if (doc.value.paras[i]) Object.assign(doc.value.paras[i], patch)
  })
  push({ op: 'format', paras: [...picked.value], patch, name })
}

function onInput(i, e) {
  if (props.readonly) return
  doc.value.paras[i].text = e.target.innerText.replace(/\n+$/, '')
  push()
}

// ---------- 功能区按钮 ----------
function pickBrush() {
  if (props.readonly) return
  const { text, ...fmt } = cur.value
  brush.value = fmt
}
function clearFormat() {
  apply({ ...DEFAULT_PARA, text: undefined }, '清除格式')
}
function indentStep(step) {
  if (props.readonly) return
  picked.value.forEach(i => {
    const p = doc.value.paras[i]
    if (p) p.indent = Math.max(0, Math.round(((p.indent || 0) + step) * 10) / 10)
  })
  push({ op: 'indent', step })
}
function setStyle(name) {
  const s = STYLES[name]
  if (s) apply({ ...s, style: name }, '样式')
}
function copyPara() {
  paraClip.value = picked.value.map(i => JSON.parse(JSON.stringify(doc.value.paras[i]))).filter(Boolean)
}
function cutPara() {
  if (props.readonly) return
  copyPara()
  delPara()
}
function pastePara() {
  if (props.readonly || !paraClip.value?.length) return
  const at = picked.value[picked.value.length - 1] + 1
  doc.value.paras.splice(at, 0, ...JSON.parse(JSON.stringify(paraClip.value)))
  picked.value = [at]
  push({ op: 'para-paste', at })
}

// ---------- 段落增删与移动 ----------
function addPara() {
  if (props.readonly) return
  const at = picked.value[picked.value.length - 1] + 1
  doc.value.paras.splice(at, 0, { text: '', ...DEFAULT_PARA })
  picked.value = [at]
  push({ op: 'para-add', at })
}
function delPara() {
  if (props.readonly || doc.value.paras.length <= 1) return
  const sorted = [...picked.value].sort((a, b) => b - a)
  sorted.forEach(i => doc.value.paras.splice(i, 1))
  picked.value = [Math.max(0, sorted[sorted.length - 1] - 1)]
  push({ op: 'para-del' })
}
function move(step) {
  if (props.readonly) return
  const i = picked.value[0]
  const j = i + step
  if (j < 0 || j >= doc.value.paras.length) return
  const [p] = doc.value.paras.splice(i, 1)
  doc.value.paras.splice(j, 0, p)
  picked.value = [j]
  push({ op: 'para-move', from: i, to: j })
}
/** 直接挪到末尾。「将第四段移动到文章末尾」这类要求，一步到位省得点十几次 */
function moveEnd() {
  if (props.readonly) return
  const i = picked.value[0]
  const [p] = doc.value.paras.splice(i, 1)
  doc.value.paras.push(p)
  picked.value = [doc.value.paras.length - 1]
  push({ op: 'para-move-end', from: i })
}

// ---------- 对话框 ----------
const dlg = ref('')
const form = ref({})

function openDlg(which) {
  const p = cur.value
  if (which === 'para') {
    form.value = {
      indent: p.indent || 0,
      lineType: p.line ? p.line.type : 'single',
      lineValue: p.line ? p.line.value : 1,
      before: p.before || 0,
      after: p.after || 0,
      align: p.align || 'left'
    }
  } else if (which === 'page') {
    form.value = { ...doc.value.page }
  } else if (which === 'head') {
    form.value = { header: doc.value.header, footer: doc.value.footer }
  } else if (which === 'find') {
    form.value = { from: '', to: '', done: 0 }
  }
  dlg.value = which
}

function saveDlg() {
  const f = form.value
  if (dlg.value === 'para') {
    apply({
      align: f.align,
      indent: Number(f.indent) || 0,
      before: Number(f.before) || 0,
      after: Number(f.after) || 0,
      line: f.lineType === 'single' ? null : { type: f.lineType, value: Number(f.lineValue) || 0 }
    }, '段落')
  } else if (dlg.value === 'page') {
    doc.value.page = {
      left: Number(f.left) || 0, right: Number(f.right) || 0,
      top: Number(f.top) || 0, bottom: Number(f.bottom) || 0,
      orient: f.orient || 'portrait'
    }
    push({ op: 'page' })
  } else if (dlg.value === 'head') {
    doc.value.header = f.header || ''
    doc.value.footer = f.footer || ''
    push({ op: 'header-footer' })
  }
  dlg.value = ''
}

function replaceAll() {
  if (props.readonly) return
  const { from, to } = form.value
  if (!from) return
  let n = 0
  doc.value.paras.forEach(p => {
    const parts = String(p.text).split(from)
    n += parts.length - 1
    p.text = parts.join(to || '')
  })
  form.value.done = n
  push({ op: 'replace', from, to, n })
}

// ---------- 渲染 ----------
function styleOf(p) {
  const pt = SIZES[p.size] || Number(p.size) || 10.5
  const deco = [p.underline && 'underline', p.strike && 'line-through'].filter(Boolean).join(' ')
  const css = {
    fontFamily: p.font || '宋体',
    fontSize: pt + 'pt',
    fontWeight: p.bold ? '700' : '400',
    fontStyle: p.italic ? 'italic' : 'normal',
    textDecoration: deco || 'none',
    textAlign: p.align === 'distribute' ? 'justify' : p.align || 'left',
    textIndent: (p.indent || 0) + 'em',
    marginTop: (p.before || 0) * 12 + 'px',
    marginBottom: (p.after || 0) * 12 + 'px'
  }
  if (p.color) css.color = p.color
  if (p.highlight) css.background = p.highlight
  if (p.shading) css.background = p.shading
  if (p.border) { css.border = '1px solid #333'; css.padding = '2px 4px' }
  if (p.sup) { css.verticalAlign = 'super'; css.fontSize = pt * 0.75 + 'pt' }
  if (p.sub) { css.verticalAlign = 'sub'; css.fontSize = pt * 0.75 + 'pt' }
  if (p.line) css.lineHeight = p.line.type === 'multiple' ? String(p.line.value) : p.line.value + 'pt'
  return css
}

function bulletOf(p, i) {
  if (p.bullet === 'dot') return '●'
  if (p.bullet === 'number') {
    const n = doc.value.paras.slice(0, i + 1).filter(x => x.bullet === 'number').length
    return n + '.'
  }
  return ''
}

const pageStyle = computed(() => ({
  paddingLeft: doc.value.page.left * 11 + 'px',
  paddingRight: doc.value.page.right * 11 + 'px',
  paddingTop: doc.value.page.top * 11 + 'px',
  paddingBottom: doc.value.page.bottom * 11 + 'px',
  columnCount: doc.value.columns > 1 ? doc.value.columns : 'auto',
  width: doc.value.page.orient === 'landscape' ? '780px' : '580px'
}))

const tip = ref('')
function notYet(name) {
  tab.value = '开始'
  tip.value = `「${name}」这一栏本题用不到，需要的操作都在「开始」里。`
  setTimeout(() => (tip.value = ''), 2600)
}
</script>

<template>
  <div class="wps">
    <!-- ======================= 顶栏 ======================= -->
    <div class="topbar">
      <span class="file">☰ 文件</span>
      <span class="auto"><i class="sw" /> 自动保存</span>
      <span class="qbtns"><i>🖫</i><i>⎙</i><i>🔍</i><i>↶</i><i>↷</i></span>
      <nav class="tabs">
        <button
          v-for="t in TABS"
          :key="t"
          :class="{ on: tab === t }"
          @click="t === '开始' ? (tab = t) : notYet(t)"
        >{{ t }}</button>
        <button class="ai" @click="notYet('WPS AI')">✦ WPS AI</button>
      </nav>
      <span class="doc-name">{{ doc.name }}</span>
    </div>

    <!-- ======================= 功能区（开始） ======================= -->
    <div class="ribbon">
      <div class="grp">
        <button class="big" :class="{ on: brush }" :disabled="readonly" title="格式刷：先选好格式，再点要刷的段落" @click="pickBrush">
          <i>🖌</i><span>格式刷</span>
        </button>
        <div class="col">
          <button :disabled="readonly" title="剪切段落" @click="cutPara">✂</button>
          <button :disabled="readonly" title="复制段落" @click="copyPara">⧉</button>
          <button :disabled="readonly || !paraClip" title="粘贴段落" @click="pastePara">📋</button>
        </div>
      </div>

      <div class="grp wide">
        <div class="row">
          <select class="font" :value="cur.font" :disabled="readonly" @change="apply({ font: $event.target.value }, '字体')">
            <option v-for="f in FONTS" :key="f" :value="f">{{ f }}</option>
          </select>
          <select class="size" :value="cur.size" :disabled="readonly" @change="apply({ size: $event.target.value }, '字号')">
            <option v-for="(pt, name) in SIZES" :key="name" :value="name">{{ name }}</option>
          </select>
          <button :disabled="readonly" title="增大字号" @click="apply({ size: Object.keys(SIZES)[Math.max(0, Object.keys(SIZES).indexOf(cur.size) - 1)] }, '增大字号')">A⁺</button>
          <button :disabled="readonly" title="减小字号" @click="apply({ size: Object.keys(SIZES)[Math.min(Object.keys(SIZES).length - 1, Object.keys(SIZES).indexOf(cur.size) + 1)] }, '减小字号')">A⁻</button>
          <button :disabled="readonly" title="清除格式" @click="clearFormat">🧹</button>
        </div>
        <div class="row">
          <button :class="{ on: cur.bold }" :disabled="readonly" title="加粗" @click="apply({ bold: !cur.bold }, '加粗')"><b>B</b></button>
          <button :class="{ on: cur.italic }" :disabled="readonly" title="倾斜" @click="apply({ italic: !cur.italic }, '倾斜')"><i>I</i></button>
          <button :class="{ on: cur.underline }" :disabled="readonly" title="下划线" @click="apply({ underline: !cur.underline }, '下划线')"><u>U</u></button>
          <button :class="{ on: cur.strike }" :disabled="readonly" title="删除线" @click="apply({ strike: !cur.strike }, '删除线')"><s>ab</s></button>
          <button :class="{ on: cur.sup }" :disabled="readonly" title="上标" @click="apply({ sup: !cur.sup, sub: false }, '上标')">x²</button>
          <button :class="{ on: cur.sub }" :disabled="readonly" title="下标" @click="apply({ sub: !cur.sub, sup: false }, '下标')">x₂</button>
          <label class="pick" title="突出显示">
            <span class="sw hl" :style="{ background: cur.highlight || '#fff' }" />
            <select :value="cur.highlight" :disabled="readonly" @change="apply({ highlight: $event.target.value }, '突出显示')">
              <option v-for="h in HIGHLIGHTS" :key="h || 'none'" :value="h">{{ h ? h : '无' }}</option>
            </select>
          </label>
          <label class="pick" title="字体颜色">
            <span class="sw" :style="{ background: cur.color || '#000' }" />
            <input type="color" :value="cur.color || '#000000'" :disabled="readonly" @change="apply({ color: $event.target.value }, '字体颜色')" />
          </label>
          <label class="pick" title="字符底纹">
            <span class="sw" :style="{ background: cur.shading || '#fff' }" />
            <input type="color" :value="cur.shading || '#ffffff'" :disabled="readonly" @change="apply({ shading: $event.target.value }, '字符底纹')" />
          </label>
        </div>
      </div>

      <div class="grp wide">
        <div class="row">
          <button :class="{ on: cur.bullet === 'dot' }" :disabled="readonly" title="项目符号" @click="apply({ bullet: cur.bullet === 'dot' ? 'none' : 'dot' }, '项目符号')">•≡</button>
          <button :class="{ on: cur.bullet === 'number' }" :disabled="readonly" title="编号" @click="apply({ bullet: cur.bullet === 'number' ? 'none' : 'number' }, '编号')">1≡</button>
          <button :disabled="readonly" title="减少缩进" @click="indentStep(-1)">⇤</button>
          <button :disabled="readonly" title="增加缩进" @click="indentStep(1)">⇥</button>
          <button :class="{ on: marks }" title="显示/隐藏段落标记" @click="marks = !marks">¶</button>
        </div>
        <div class="row">
          <button
            v-for="a in ALIGNS"
            :key="a.v"
            :class="['al-' + a.c, { on: cur.align === a.v }]"
            :disabled="readonly"
            :title="a.t"
            @click="apply({ align: a.v }, '对齐')"
          >{{ a.i }}</button>
          <select class="line" :disabled="readonly" :value="cur.line ? cur.line.value : 1"
                  title="行距"
                  @change="apply({ line: Number($event.target.value) === 1 ? null : { type: 'multiple', value: Number($event.target.value) } }, '行距')">
            <option :value="1">1.0</option><option :value="1.15">1.15</option>
            <option :value="1.5">1.5</option><option :value="2">2.0</option>
          </select>
          <button :class="{ on: cur.border }" :disabled="readonly" title="边框" @click="apply({ border: !cur.border }, '边框')">▢</button>
        </div>
      </div>

      <div class="grp">
        <select class="style" :value="cur.style" :disabled="readonly" title="样式" @change="setStyle($event.target.value)">
          <option v-for="(v, k) in STYLES" :key="k" :value="k">{{ k }}</option>
        </select>
        <button class="big" :disabled="readonly" title="段落设置" @click="openDlg('para')"><i>¶</i><span>段落</span></button>
      </div>

      <div class="grp">
        <button class="big" :disabled="readonly" @click="openDlg('find')"><i>🔍</i><span>查找替换</span></button>
        <button class="big" :disabled="readonly" @click="openDlg('page')"><i>▤</i><span>页面设置</span></button>
        <button class="big" :disabled="readonly" @click="openDlg('head')"><i>⌐</i><span>页眉页脚</span></button>
        <select class="cols" :value="doc.columns" :disabled="readonly" title="分栏"
                @change="doc.columns = Number($event.target.value); push({ op: 'columns' })">
          <option :value="1">一栏</option><option :value="2">两栏</option><option :value="3">三栏</option>
        </select>
      </div>
    </div>

    <!-- 段落级操作：真 WPS 靠鼠标选区，这里用按钮代替，好判分也好操作 -->
    <div class="subbar">
      <span class="hint">选中段落后：</span>
      <button :disabled="readonly" @click="addPara">插入段落</button>
      <button :disabled="readonly" @click="delPara">删除段落</button>
      <button :disabled="readonly" @click="move(-1)">上移</button>
      <button :disabled="readonly" @click="move(1)">下移</button>
      <button :disabled="readonly" @click="moveEnd">移到末尾</button>
      <span class="grow" />
      <span class="hint">第 {{ picked[0] + 1 }} 段 / 共 {{ doc.paras.length }} 段</span>
    </div>

    <!-- ======================= 纸张 ======================= -->
    <div class="sheet-wrap">
      <div class="sheet" :style="pageStyle">
        <i class="mark tl" /><i class="mark tr" /><i class="mark bl" /><i class="mark br" />
        <div v-if="doc.header" class="hf">{{ doc.header }}</div>
        <div v-for="(p, i) in doc.paras" :key="i" class="pline" :class="{ on: picked.includes(i) }">
          <span v-if="p.bullet !== 'none'" class="bul" :style="{ fontSize: (SIZES[p.size] || 10.5) + 'pt' }">
            {{ bulletOf(p, i) }}
          </span>
          <p
            class="para"
            :style="styleOf(p)"
            :contenteditable="!readonly"
            @click="select(i, $event)"
            @focus="select(i, null)"
            @input="onInput(i, $event)"
            v-text="p.text"
          />
          <span v-if="marks" class="pmark">¶</span>
        </div>
        <div v-if="doc.footer" class="hf foot">{{ doc.footer }}</div>
      </div>
    </div>

    <div class="statusbar">
      <span>页面 1/1</span><span>{{ doc.paras.reduce((n, p) => n + p.text.length, 0) }} 字</span>
      <span>{{ doc.page.orient === 'landscape' ? '横向' : '纵向' }}</span>
      <span v-if="doc.columns > 1">{{ doc.columns }} 栏</span>
      <span class="grow" />
      <span v-if="brush" class="brush-on">格式刷已吸取，点段落即可刷格式</span>
    </div>

    <p v-if="tip" class="tip">{{ tip }}</p>

    <!-- ======================= 对话框 ======================= -->
    <div v-if="dlg === 'para'" class="modal" @click.self="dlg = ''">
      <div class="dlg">
        <header>段落</header>
        <div class="pad">
          <label>对齐方式
            <select v-model="form.align">
              <option v-for="a in ALIGNS" :key="a.v" :value="a.v">{{ a.t }}</option>
            </select>
          </label>
          <label>首行缩进 <input v-model.number="form.indent" type="number" step="1" min="0" /> 字符</label>
          <label>行距
            <select v-model="form.lineType">
              <option value="single">单倍行距</option>
              <option value="multiple">多倍行距</option>
              <option value="fixed">固定值</option>
              <option value="least">最小值</option>
            </select>
            <input v-if="form.lineType !== 'single'" v-model.number="form.lineValue" type="number" step="0.5" />
            <span v-if="form.lineType === 'fixed' || form.lineType === 'least'">磅</span>
            <span v-else-if="form.lineType === 'multiple'">倍</span>
          </label>
          <label>段前间距 <input v-model.number="form.before" type="number" step="0.5" min="0" /> 行</label>
          <label>段后间距 <input v-model.number="form.after" type="number" step="0.5" min="0" /> 行</label>
        </div>
        <footer><button @click="dlg = ''">取消</button><button class="ok" @click="saveDlg">确定</button></footer>
      </div>
    </div>

    <div v-if="dlg === 'page'" class="modal" @click.self="dlg = ''">
      <div class="dlg">
        <header>页面设置</header>
        <div class="pad">
          <label>上边距 <input v-model.number="form.top" type="number" step="0.1" /> 厘米</label>
          <label>下边距 <input v-model.number="form.bottom" type="number" step="0.1" /> 厘米</label>
          <label>左边距 <input v-model.number="form.left" type="number" step="0.1" /> 厘米</label>
          <label>右边距 <input v-model.number="form.right" type="number" step="0.1" /> 厘米</label>
          <label>纸张方向
            <select v-model="form.orient"><option value="portrait">纵向</option><option value="landscape">横向</option></select>
          </label>
        </div>
        <footer><button @click="dlg = ''">取消</button><button class="ok" @click="saveDlg">确定</button></footer>
      </div>
    </div>

    <div v-if="dlg === 'head'" class="modal" @click.self="dlg = ''">
      <div class="dlg">
        <header>页眉和页脚</header>
        <div class="pad">
          <label>页眉 <input v-model="form.header" type="text" /></label>
          <label>页脚 <input v-model="form.footer" type="text" /></label>
        </div>
        <footer><button @click="dlg = ''">取消</button><button class="ok" @click="saveDlg">确定</button></footer>
      </div>
    </div>

    <div v-if="dlg === 'find'" class="modal" @click.self="dlg = ''">
      <div class="dlg">
        <header>查找和替换</header>
        <div class="pad">
          <label>查找内容 <input v-model="form.from" type="text" /></label>
          <label>替换为 <input v-model="form.to" type="text" /></label>
          <p v-if="form.done" class="done">已完成 {{ form.done }} 处替换。</p>
        </div>
        <footer>
          <button @click="dlg = ''">关闭</button>
          <button class="ok" :disabled="readonly" @click="replaceAll">全部替换</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wps {
  border: 1px solid #c9ced8;
  border-radius: 6px;
  background: #f5f6f8;
  color: #20242c;
  font: 12.5px/1.5 "Microsoft YaHei", sans-serif;
  overflow: hidden;
}

/* ---------------- 顶栏 ---------------- */
.topbar {
  display: flex; align-items: center; gap: 12px; padding: 5px 10px;
  background: #fff; border-bottom: 1px solid #eceef2;
}
.file { color: #3a3f4a; }
.auto { display: flex; align-items: center; gap: 5px; color: #6b7280; font-size: 12px; }
.sw { width: 24px; height: 13px; border-radius: 7px; background: #d5d9e0; display: inline-block; position: relative; }
.sw::after { content: ''; position: absolute; left: 2px; top: 2px; width: 9px; height: 9px; border-radius: 50%; background: #fff; }
.qbtns { display: flex; gap: 8px; color: #7b818c; }
.qbtns i { font-style: normal; cursor: default; }
.tabs { display: flex; gap: 2px; margin-left: 6px; }
.tabs button {
  border: none; background: none; padding: 4px 11px; border-radius: 4px 4px 0 0;
  font: inherit; color: #4a5361; cursor: pointer;
}
.tabs button:hover { background: #f0f2f6; }
.tabs button.on { color: #c8433a; font-weight: 600; box-shadow: inset 0 -2px 0 #c8433a; }
.tabs .ai { color: #2b6ee0; }
.doc-name { margin-left: auto; color: #9aa1ac; font-size: 12px; }

/* ---------------- 功能区 ---------------- */
.ribbon {
  display: flex; align-items: stretch; gap: 0; padding: 6px 8px;
  background: #fff; border-bottom: 1px solid #e3e6eb; overflow-x: auto;
}
.grp {
  display: flex; align-items: center; gap: 4px; padding: 0 8px;
  border-right: 1px solid #eceef2;
}
.grp.wide { flex-direction: column; justify-content: center; gap: 3px; }
.grp .row { display: flex; align-items: center; gap: 3px; }
.grp .col { display: flex; flex-direction: column; gap: 1px; }
.ribbon button {
  min-width: 25px; height: 23px; padding: 0 6px; border: 1px solid transparent;
  background: none; border-radius: 3px; cursor: pointer; font: inherit; color: #20242c;
}
.ribbon button:hover:not(:disabled) { background: #eef3fd; border-color: #cfdcf5; }
.ribbon button.on { background: #dceafc; border-color: #9dbef0; }
.ribbon button:disabled { color: #b3b8c0; cursor: default; }
.ribbon button.big {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 1px; height: 46px; min-width: 46px; font-size: 11px; line-height: 1.2;
}
.ribbon button.big i { font-style: normal; font-size: 15px; }
.ribbon select {
  height: 23px; border: 1px solid #d5d9e0; border-radius: 3px; background: #fff;
  font: inherit; font-size: 12px; padding: 0 2px;
}
.ribbon select.font { width: 96px; }
.ribbon select.size { width: 58px; }
.ribbon select.line { width: 58px; }
.ribbon select.style { width: 76px; }
.ribbon select.cols { width: 66px; }
.pick { display: inline-flex; flex-direction: column; align-items: center; position: relative; width: 26px; }
.pick .sw { width: 18px; height: 4px; border-radius: 1px; border: 1px solid #c9ced8; }
.pick .sw.hl { height: 5px; }
.pick select, .pick input[type='color'] {
  width: 26px; height: 14px; border: none; padding: 0; background: none; cursor: pointer;
}
.al-c { text-align: center; } .al-r { text-align: right; }
.al-j, .al-d { letter-spacing: 1px; }

.subbar {
  display: flex; align-items: center; gap: 6px; padding: 4px 12px;
  background: #fafbfd; border-bottom: 1px solid #e3e6eb;
}
.subbar button {
  border: 1px solid #d5d9e0; background: #fff; border-radius: 3px; padding: 2px 9px;
  font: inherit; font-size: 12px; cursor: pointer;
}
.subbar button:hover:not(:disabled) { border-color: #9dbef0; background: #eef3fd; }
.subbar button:disabled { color: #b3b8c0; cursor: default; }
.hint { color: #8a919c; font-size: 12px; }
.grow { flex: 1; }

/* ---------------- 纸张 ---------------- */
.sheet-wrap { padding: 18px; max-height: 420px; overflow: auto; background: #eceef2; }
.sheet {
  position: relative; margin: 0 auto; background: #fff;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.16); min-height: 320px;
}
/* 页边距的四个直角标记，WPS 上就是这样 */
.mark { position: absolute; width: 14px; height: 14px; border-color: #b9c0cc; border-style: solid; border-width: 0; }
.mark.tl { left: 12px; top: 12px; border-left-width: 1px; border-top-width: 1px; }
.mark.tr { right: 12px; top: 12px; border-right-width: 1px; border-top-width: 1px; }
.mark.bl { left: 12px; bottom: 12px; border-left-width: 1px; border-bottom-width: 1px; }
.mark.br { right: 12px; bottom: 12px; border-right-width: 1px; border-bottom-width: 1px; }
.hf { color: #9aa1ac; font-size: 11px; border-bottom: 1px dashed #e3e6eb; padding-bottom: 3px; margin-bottom: 8px; }
.hf.foot { border-bottom: none; border-top: 1px dashed #e3e6eb; padding: 3px 0 0; margin: 10px 0 0; }
.pline { display: flex; align-items: flex-start; gap: 4px; }
.pline.on { background: #eaf2ff; }
.bul { flex: none; line-height: 1.6; color: #333; }
.para {
  flex: 1; margin: 0; padding: 1px 3px; outline: none; border: 1px solid transparent;
  min-height: 1.4em; white-space: pre-wrap; word-break: break-word;
}
.pline.on .para { border-color: #b9d4ff; }
.pmark { color: #7ba7e8; flex: none; }

.statusbar {
  display: flex; align-items: center; gap: 14px; padding: 3px 12px;
  background: #fff; border-top: 1px solid #e3e6eb; color: #8a919c; font-size: 11.5px;
}
.brush-on { color: #c8433a; }
.tip {
  position: absolute; left: 50%; transform: translateX(-50%); margin-top: -34px;
  background: #fffbe6; border: 1px solid #f0d48a; color: #8a5a00;
  padding: 5px 14px; border-radius: 4px; font-size: 12px;
}

/* ---------------- 对话框 ---------------- */
.modal { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.28); display: flex; align-items: center; justify-content: center; z-index: 40; }
.dlg { background: #fff; border-radius: 6px; min-width: 330px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3); overflow: hidden; }
.dlg header { padding: 9px 14px; background: #f5f6f8; font-weight: 600; border-bottom: 1px solid #e3e6eb; }
.dlg .pad { padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.dlg label { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.dlg input[type='number'] { width: 70px; }
.dlg input[type='text'] { flex: 1; }
.dlg input, .dlg select { border: 1px solid #d5d9e0; border-radius: 3px; padding: 3px 6px; font: inherit; }
.dlg .done { margin: 0; color: #1a7f37; font-size: 12px; }
.dlg footer { display: flex; justify-content: flex-end; gap: 8px; padding: 9px 14px; background: #fafbfd; border-top: 1px solid #e3e6eb; }
.dlg footer button { min-width: 72px; padding: 4px 10px; border: 1px solid #d5d9e0; background: #fff; border-radius: 3px; cursor: pointer; font: inherit; }
.dlg footer .ok { background: #c8433a; border-color: #c8433a; color: #fff; }
</style>

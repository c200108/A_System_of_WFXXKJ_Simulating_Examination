<script setup>
/**
 * WPS 文字仿真。
 *
 * ## 文档模型：格式挂在段落上
 *
 *     { paras: [{ text, font, size, bold, align, indent, line, before, after }],
 *       page: { left, right, top, bottom, orient }, header, footer, columns }
 *
 * 真 Word 的格式挂在「字符游程」上（同一段里可以半句楷体半句宋体）。这里刻意
 * 简化成按段落记 —— 中考的 WPS 题九成是「把标题设成楷体二号加粗居中」「把
 * 某段设成首行缩进 2 字符」，都是整段操作；按段落记既够用，判分断言也写得清楚。
 *
 * 代价：考「把文中某几个字设成红色」这类题它做不了。真要考，得把模型升级成
 * 游程，判分那边同步改。
 *
 * ## 做了什么
 *
 * 字体、字号、加粗/倾斜/下划线、颜色、四种对齐、首行缩进、行距、段前段后、
 * 页边距、纸张方向、页眉页脚、分栏、查找替换、段落上下移动、插入删除段落。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps({
  env: { type: Object, required: true },
  modelValue: { type: Object, default: null },
  readonly: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'log'])

const FONTS = ['宋体', '黑体', '楷体', '仿宋', '微软雅黑', '隶书', '幼圆', 'Times New Roman', 'Arial']
// 中文字号对应的磅值。判分那边有一份一样的表（services/sim.py 的 SIZE_ALIASES），
// 所以老师写「二号」还是写 22，两边都认得。
const SIZES = {
  初号: 42, 小初: 36, 一号: 26, 小一: 24, 二号: 22, 小二: 18, 三号: 16, 小三: 15,
  四号: 14, 小四: 12, 五号: 10.5, 小五: 9, 六号: 7.5, 小六: 6.5, 七号: 5.5, 八号: 5
}
const ALIGNS = [
  { v: 'left', t: '左对齐', i: '⬅' },
  { v: 'center', t: '居中', i: '⬌' },
  { v: 'right', t: '右对齐', i: '➡' },
  { v: 'justify', t: '两端对齐', i: '☰' }
]

const DEFAULT_PARA = {
  font: '宋体', size: '五号', bold: false, italic: false, underline: false,
  color: '', align: 'left', indent: 0, line: null, before: 0, after: 0
}

const doc = ref({ paras: [], page: {}, header: '', footer: '', columns: 1, name: '' })
const picked = ref([0])          // 选中的段落序号

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
}
const cur = computed(() => doc.value.paras[picked.value[0]] || DEFAULT_PARA)

/** 把一个格式改动套到所有选中的段落上 */
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
const dlg = ref('')            // para / page / head / find
const form = ref({})

function openDlg(which) {
  const p = cur.value
  if (which === 'para') {
    form.value = {
      indent: p.indent || 0,
      lineType: p.line ? p.line.type : 'single',
      lineValue: p.line ? p.line.value : 1,
      before: p.before || 0,
      after: p.after || 0
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
  const css = {
    fontFamily: p.font || '宋体',
    fontSize: pt + 'pt',
    fontWeight: p.bold ? '700' : '400',
    fontStyle: p.italic ? 'italic' : 'normal',
    textDecoration: p.underline ? 'underline' : 'none',
    textAlign: p.align || 'left',
    textIndent: (p.indent || 0) + 'em',
    marginTop: (p.before || 0) * 12 + 'px',
    marginBottom: (p.after || 0) * 12 + 'px'
  }
  if (p.color) css.color = p.color
  if (p.line) {
    css.lineHeight = p.line.type === 'multiple' ? String(p.line.value) : p.line.value + 'pt'
  }
  return css
}

const pageStyle = computed(() => ({
  paddingLeft: doc.value.page.left * 10 + 'px',
  paddingRight: doc.value.page.right * 10 + 'px',
  paddingTop: doc.value.page.top * 10 + 'px',
  paddingBottom: doc.value.page.bottom * 10 + 'px',
  columnCount: doc.value.columns > 1 ? doc.value.columns : 'auto',
  width: doc.value.page.orient === 'landscape' ? '760px' : '560px'
}))
</script>

<template>
  <div class="wps">
    <!-- 工具栏 -->
    <div class="ribbon">
      <select :value="cur.font" :disabled="readonly" @change="apply({ font: $event.target.value }, '字体')">
        <option v-for="f in FONTS" :key="f" :value="f">{{ f }}</option>
      </select>
      <select :value="cur.size" :disabled="readonly" @change="apply({ size: $event.target.value }, '字号')">
        <option v-for="(pt, name) in SIZES" :key="name" :value="name">{{ name }}</option>
      </select>
      <span class="sep" />
      <button :class="{ on: cur.bold }" :disabled="readonly" title="加粗" @click="apply({ bold: !cur.bold }, '加粗')"><b>B</b></button>
      <button :class="{ on: cur.italic }" :disabled="readonly" title="倾斜" @click="apply({ italic: !cur.italic }, '倾斜')"><i>I</i></button>
      <button :class="{ on: cur.underline }" :disabled="readonly" title="下划线" @click="apply({ underline: !cur.underline }, '下划线')"><u>U</u></button>
      <input type="color" :value="cur.color || '#000000'" :disabled="readonly" title="字体颜色"
             @change="apply({ color: $event.target.value }, '颜色')" />
      <span class="sep" />
      <button v-for="a in ALIGNS" :key="a.v" :class="{ on: cur.align === a.v }" :disabled="readonly"
              :title="a.t" @click="apply({ align: a.v }, '对齐')">{{ a.i }}</button>
      <span class="sep" />
      <button :disabled="readonly" @click="openDlg('para')">段落…</button>
      <button :disabled="readonly" @click="openDlg('page')">页面设置…</button>
      <button :disabled="readonly" @click="openDlg('head')">页眉页脚…</button>
      <button :disabled="readonly" @click="openDlg('find')">查找替换…</button>
      <select :value="doc.columns" :disabled="readonly"
              @change="doc.columns = Number($event.target.value); push({ op: 'columns' })">
        <option :value="1">一栏</option>
        <option :value="2">两栏</option>
        <option :value="3">三栏</option>
      </select>
    </div>

    <div class="ribbon second">
      <span class="tip">选中段落后操作：</span>
      <button :disabled="readonly" @click="addPara">插入段落</button>
      <button :disabled="readonly" @click="delPara">删除段落</button>
      <button :disabled="readonly" @click="move(-1)">上移</button>
      <button :disabled="readonly" @click="move(1)">下移</button>
      <button :disabled="readonly" @click="moveEnd">移到末尾</button>
      <span class="grow" />
      <span class="tip">第 {{ picked[0] + 1 }} 段，共 {{ doc.paras.length }} 段</span>
    </div>

    <!-- 纸 -->
    <div class="sheet-wrap">
      <div class="sheet" :style="pageStyle">
        <div v-if="doc.header" class="hf">{{ doc.header }}</div>
        <p
          v-for="(p, i) in doc.paras"
          :key="i"
          class="para"
          :class="{ on: picked.includes(i) }"
          :style="styleOf(p)"
          :contenteditable="!readonly"
          @click="select(i, $event)"
          @focus="select(i, null)"
          @input="onInput(i, $event)"
          v-text="p.text"
        />
        <div v-if="doc.footer" class="hf foot">{{ doc.footer }}</div>
      </div>
    </div>

    <!-- 段落 -->
    <div v-if="dlg === 'para'" class="modal" @click.self="dlg = ''">
      <div class="dlg">
        <header>段落</header>
        <div class="pad">
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

    <!-- 页面设置 -->
    <div v-if="dlg === 'page'" class="modal" @click.self="dlg = ''">
      <div class="dlg">
        <header>页面设置</header>
        <div class="pad">
          <label>上边距 <input v-model.number="form.top" type="number" step="0.1" /> 厘米</label>
          <label>下边距 <input v-model.number="form.bottom" type="number" step="0.1" /> 厘米</label>
          <label>左边距 <input v-model.number="form.left" type="number" step="0.1" /> 厘米</label>
          <label>右边距 <input v-model.number="form.right" type="number" step="0.1" /> 厘米</label>
          <label>纸张方向
            <select v-model="form.orient">
              <option value="portrait">纵向</option>
              <option value="landscape">横向</option>
            </select>
          </label>
        </div>
        <footer><button @click="dlg = ''">取消</button><button class="ok" @click="saveDlg">确定</button></footer>
      </div>
    </div>

    <!-- 页眉页脚 -->
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

    <!-- 查找替换 -->
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
  border: 1px solid #9aa3b0;
  border-radius: 6px;
  background: #f3f4f7;
  color: #1f2430;
  font-size: 13px;
  overflow: hidden;
}
.ribbon {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  padding: 6px 8px;
  background: linear-gradient(#fdfdff, #eef1f7);
  border-bottom: 1px solid #ccd4e0;
}
.ribbon.second { background: #f8fafd; }
.ribbon select, .ribbon input[type='color'] {
  height: 24px;
  border: 1px solid #ccd4e0;
  border-radius: 3px;
  background: #fff;
  font-size: 12px;
}
.ribbon input[type='color'] { width: 30px; padding: 1px; }
.ribbon button {
  min-width: 26px;
  height: 24px;
  padding: 0 8px;
  border: 1px solid #ccd4e0;
  background: #fff;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}
.ribbon button:hover:not(:disabled) { background: #eef4ff; border-color: #7aa7e0; }
.ribbon button.on { background: #cfe3ff; border-color: #6c9bdc; }
.ribbon button:disabled { color: #aab; cursor: default; }
.sep { width: 1px; height: 18px; background: #dde3ec; margin: 0 2px; }
.grow { flex: 1; }
.tip { color: #6b7480; font-size: 12px; }
.sheet-wrap {
  padding: 16px;
  max-height: 430px;
  overflow: auto;
  background: #dfe3ea;
}
.sheet {
  margin: 0 auto;
  background: #fff;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.14);
  min-height: 300px;
}
.hf {
  color: #8a93a3;
  font-size: 11px;
  border-bottom: 1px dashed #dde3ec;
  padding-bottom: 3px;
  margin-bottom: 8px;
}
.hf.foot { border-bottom: none; border-top: 1px dashed #dde3ec; padding: 3px 0 0; margin: 10px 0 0; }
.para {
  margin: 0;
  padding: 1px 3px;
  outline: none;
  border: 1px solid transparent;
  min-height: 1.4em;
  white-space: pre-wrap;
  word-break: break-word;
}
.para.on { background: #eaf2ff; border-color: #b9d4ff; }
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.28);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 40;
}
.dlg {
  background: #fff;
  border-radius: 6px;
  min-width: 320px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}
.dlg header {
  padding: 8px 12px;
  background: linear-gradient(#e8edf5, #dbe3ee);
  font-weight: 600;
  border-bottom: 1px solid #ccd4e0;
}
.dlg .pad { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.dlg label { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.dlg input[type='number'] { width: 70px; }
.dlg input[type='text'] { flex: 1; }
.dlg input, .dlg select {
  border: 1px solid #ccd4e0;
  border-radius: 3px;
  padding: 3px 6px;
  font: inherit;
}
.dlg .done { margin: 0; color: #1a7f37; font-size: 12px; }
.dlg footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 12px;
  background: #f6f8fb;
  border-top: 1px solid #e3e8f0;
}
.dlg footer button {
  min-width: 68px;
  padding: 4px 10px;
  border: 1px solid #ccd4e0;
  background: #fff;
  border-radius: 3px;
  cursor: pointer;
}
.dlg footer .ok { background: #2c6fd1; border-color: #2c6fd1; color: #fff; }
</style>

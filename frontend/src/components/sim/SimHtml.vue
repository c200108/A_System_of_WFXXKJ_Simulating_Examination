<script setup>
/**
 * 网页编程题：学生写真代码，右边看效果。
 *
 * 状态就是一组文件：{ files: { 'index.html': '…', 'style.css': '…' } }。
 * 判分在服务端把 HTML 解析成树，断言标签、属性、标题（services/sim.py）——
 * **不是**按字符串比对，所以学生的缩进、引号用单用双、属性顺序都不影响得分。
 *
 * 预览用 iframe 的 srcdoc，加 sandbox 关掉脚本：预览区里的代码是学生写的，
 * 让它能跑脚本就等于让学生在同一个页面里随便执行 JS，考试页不该给这个口子。
 * 由此带来的限制：网页题考不了 JS 效果，只考结构和样式。
 */
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  env: { type: Object, required: true },
  modelValue: { type: Object, default: null },
  readonly: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'log'])

const files = ref({})
const active = ref('index.html')
const preview = ref('')
const wrap = ref(true)

function boot() {
  const src = props.modelValue && props.modelValue.files ? props.modelValue : props.env
  files.value = JSON.parse(JSON.stringify(src.files || { 'index.html': '' }))
  active.value = Object.keys(files.value)[0] || 'index.html'
  run()
}
boot()
watch(() => props.env, boot)

const names = computed(() => Object.keys(files.value))

function onInput(e) {
  if (props.readonly) return
  files.value[active.value] = e.target.value
  emit('update:modelValue', { files: JSON.parse(JSON.stringify(files.value)) })
}

/** Tab 键插入两个空格而不是跳到下一个控件 —— 写代码时这个太常用了 */
function onTab(e) {
  if (props.readonly) return
  const el = e.target
  const s = el.selectionStart
  const v = el.value
  el.value = v.slice(0, s) + '  ' + v.slice(el.selectionEnd)
  el.selectionStart = el.selectionEnd = s + 2
  onInput({ target: el })
}

/**
 * 拼预览用的 HTML。<link rel=stylesheet href=style.css> 会被换成内联的
 * <style>，因为 srcdoc 里没有真正的文件系统，相对路径取不到东西。
 */
function buildPreview() {
  // 这里刻意不用下面那个 names 计算属性：boot() 在组件初始化时就会调到
  // buildPreview，那时 names 还没初始化，用了会直接抛 ReferenceError
  const all = Object.keys(files.value)
  let html = String(files.value[all.find(n => n.endsWith('.html'))] || '')
  for (const name of all) {
    if (!name.endsWith('.css')) continue
    const css = String(files.value[name] || '')
    const tag = new RegExp(`<link[^>]*href=["']?${name}["']?[^>]*>`, 'i')
    if (tag.test(html)) html = html.replace(tag, `<style>\n${css}\n</style>`)
    else html = html.replace(/<\/head>/i, `<style>\n${css}\n</style>\n</head>`)
  }
  return html
}

function run() {
  preview.value = buildPreview()
  emit('log', { at: Date.now(), op: 'preview' })
}

// ---------- 插入代码片段 ----------
// 初中的网页题多半卡在"标签怎么写"上，给几个按钮直接插进去，
// 让学生把注意力放在结构和样式上，而不是背尖括号。
const HTML_SNIPS = [
  ['标题', '<h1>标题文字</h1>\n'],
  ['段落', '<p>段落文字</p>\n'],
  ['超链接', '<a href="http://www.moe.gov.cn">链接文字</a>\n'],
  ['图片', '<img src="logo.png" alt="说明文字">\n'],
  ['列表', '<ul>\n  <li>第一项</li>\n  <li>第二项</li>\n</ul>\n'],
  ['表格', '<table border="1">\n  <tr><td>一</td><td>二</td></tr>\n</table>\n'],
  ['加粗', '<b>加粗文字</b>'],
  ['换行', '<br>\n']
]
const CSS_SNIPS = [
  ['文字颜色', 'h1 {\n  color: red;\n}\n'],
  ['字号', 'p {\n  font-size: 16px;\n}\n'],
  ['居中', 'h1 {\n  text-align: center;\n}\n'],
  ['背景色', 'body {\n  background-color: #eef5ff;\n}\n'],
  ['边框', 'table {\n  border: 1px solid #333;\n}\n']
]
const snips = computed(() => (active.value.endsWith('.css') ? CSS_SNIPS : HTML_SNIPS))

const editor = ref(null)
function insert(text) {
  if (props.readonly) return
  const el = editor.value
  const v = String(files.value[active.value] || '')
  const at = el ? el.selectionStart : v.length
  files.value[active.value] = v.slice(0, at) + text + v.slice(el ? el.selectionEnd : v.length)
  emit('update:modelValue', { files: JSON.parse(JSON.stringify(files.value)) })
  // 光标落到插入内容的末尾，接着往下写
  nextTick(() => {
    if (!el) return
    el.focus()
    el.selectionStart = el.selectionEnd = at + text.length
  })
}
</script>

<template>
  <div class="html">
    <div class="tabs">
      <button
        v-for="n in names"
        :key="n"
        class="tab"
        :class="{ on: n === active }"
        @click="active = n"
      >{{ n }}</button>
      <span class="grow" />
      <label class="chk"><input v-model="wrap" type="checkbox" /> 自动换行</label>
      <button class="run" @click="run">▶ 运行</button>
    </div>

    <div class="snipbar">
      <span class="lab">{{ active.endsWith('.css') ? '常用样式' : '插入标签' }}</span>
      <button v-for="[label, code] in snips" :key="label" :disabled="readonly" @click="insert(code)">
        {{ label }}
      </button>
    </div>

    <div class="split">
      <textarea
        ref="editor"
        class="code"
        :class="{ nowrap: !wrap }"
        :value="files[active]"
        :readonly="readonly"
        spellcheck="false"
        placeholder="在这里写代码，写完点右上角「运行」看效果"
        @input="onInput"
        @keydown.tab.prevent="onTab"
      />
      <div class="view">
        <div class="vhead">预览</div>
        <!-- sandbox 不带 allow-scripts：预览区跑的是学生写的代码 -->
        <iframe :srcdoc="preview" sandbox="" title="预览" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.html {
  border: 1px solid #9aa3b0;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
  font-size: 13px;
}
.tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 8px;
  background: linear-gradient(#fdfdff, #eef1f7);
  border-bottom: 1px solid #ccd4e0;
}
.tab {
  border: 1px solid transparent;
  background: none;
  padding: 3px 12px;
  border-radius: 3px 3px 0 0;
  cursor: pointer;
  font: inherit;
  color: #4a5361;
}
.tab.on { background: #fff; border-color: #ccd4e0; border-bottom-color: #fff; color: #1f2430; font-weight: 600; }
.grow { flex: 1; }
.chk { font-size: 12px; color: #6b7480; display: flex; align-items: center; gap: 4px; }
.run {
  border: 1px solid #2c6fd1;
  background: #2c6fd1;
  color: #fff;
  border-radius: 3px;
  padding: 3px 12px;
  cursor: pointer;
  font: inherit;
}
.snipbar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 5px;
  padding: 5px 8px; background: #fafbfd; border-bottom: 1px solid #e3e8f0;
}
.snipbar .lab { font-size: 12px; color: #6b7480; margin-right: 2px; }
.snipbar button {
  border: 1px solid #ccd4e0; background: #fff; border-radius: 3px;
  padding: 2px 9px; font: inherit; font-size: 12px; cursor: pointer;
}
.snipbar button:hover:not(:disabled) { border-color: #7aa7e0; background: #eef4ff; }
.snipbar button:disabled { color: #aab; cursor: default; }
.split { display: flex; min-height: 320px; }
.code {
  flex: 1;
  min-width: 0;
  border: none;
  border-right: 1px solid #e3e8f0;
  padding: 10px 12px;
  font: 13px/1.7 Consolas, 'Courier New', monospace;
  resize: none;
  outline: none;
  tab-size: 2;
  background: #fbfcfe;
}
.code.nowrap { white-space: pre; overflow-x: auto; }
.view { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.vhead {
  padding: 4px 10px;
  font-size: 12px;
  color: #6b7480;
  background: #f6f8fb;
  border-bottom: 1px solid #e3e8f0;
}
.view iframe { flex: 1; width: 100%; border: none; background: #fff; }
@media (max-width: 720px) {
  .split { flex-direction: column; }
  .code { border-right: none; border-bottom: 1px solid #e3e8f0; min-height: 200px; }
}
</style>

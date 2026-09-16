<script setup>
/**
 * Windows 文件管理仿真。
 *
 * 学生在这里新建、改名、移动、删除文件和文件夹，做完之后整个「虚拟文件系统」
 * 交到服务端按检查点判分（见 backend/app/services/sim.py）。
 *
 * ## 文件系统为什么是一张平表
 *
 *     { "C:/EXAM": {type:'dir'}, "C:/EXAM/会徽/冬梦.txt": {type:'file', content:''} }
 *
 * 嵌套结构写起来顺眼，但判分要断言的是「某个路径在不在、是什么」，平表一句
 * 就查完了；出题时拿初始环境和终态做差集也是平表最省事。代价是改名和移动要
 * 自己处理子路径，都收在 rekey() 一个函数里。
 *
 * ## 没做的事
 *
 * 拖拽、多选、搜索、共享、快捷方式 —— 中考的文件管理题考不到，先不做。
 * 删除一律进回收站（回收站里能还原），Shift+Delete 那种彻底删除也没做。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps({
  env: { type: Object, required: true },   // 初始环境
  modelValue: { type: Object, default: null },  // 当前状态（接着做时传进来）
  readonly: { type: Boolean, default: false }   // 老师回看答卷时不让改
})
const emit = defineEmits(['update:modelValue', 'log'])

const ROOT = 'C:'

// ---------- 状态 ----------
const fs = ref({})
const recycle = ref({})
const cwd = ref(ROOT)
const selected = ref('')
const clip = ref(null)          // { path, cut:true/false }

function boot() {
  const src = props.modelValue && props.modelValue.fs ? props.modelValue : props.env
  fs.value = JSON.parse(JSON.stringify(src.fs || { [ROOT]: { type: 'dir' } }))
  recycle.value = JSON.parse(JSON.stringify(src.recycle || {}))
  // 只有整个文件系统都空的时候才补一个盘符节点。环境里已经有 C:/EXAM 却硬塞一个
  // C: 进去的话，出题时拿前后状态做差集会凭空多出一条「新建文件夹 C:」的检查点
  if (!Object.keys(fs.value).length) fs.value[ROOT] = { type: 'dir' }
  // 打开时停在第一个有东西的文件夹，省得学生自己一层层点进去
  const dirs = Object.keys(fs.value).filter(p => fs.value[p].type === 'dir')
  cwd.value = dirs.find(p => children(p).length) || dirs[0] || ROOT
}
boot()
watch(() => props.env, boot)

function push(action) {
  emit('update:modelValue', {
    fs: JSON.parse(JSON.stringify(fs.value)),
    recycle: JSON.parse(JSON.stringify(recycle.value))
  })
  if (action) emit('log', { at: Date.now(), ...action })
}

// ---------- 路径 ----------
const join = (dir, name) => (dir === '' ? name : `${dir}/${name}`)
const baseOf = p => p.slice(p.lastIndexOf('/') + 1)
const parentOf = p => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '')

/** 某个文件夹的直接子项（不含孙子） */
function children(dir) {
  const prefix = dir + '/'
  return Object.keys(fs.value)
    .filter(p => p.startsWith(prefix) && !p.slice(prefix.length).includes('/'))
    .sort((a, b) => {
      const ta = fs.value[a].type === 'dir' ? 0 : 1
      const tb = fs.value[b].type === 'dir' ? 0 : 1
      return ta - tb || a.localeCompare(b, 'zh')
    })
}

const list = computed(() => children(cwd.value).map(p => ({ path: p, name: baseOf(p), ...fs.value[p] })))

/** 左侧树：所有文件夹按层级列出来 */
const tree = computed(() =>
  Object.keys(fs.value)
    .filter(p => fs.value[p].type === 'dir')
    .sort((a, b) => a.localeCompare(b, 'zh'))
    .map(p => ({ path: p, name: baseOf(p) || p, depth: p.split('/').length - 1 }))
)

const crumbs = computed(() => {
  const parts = cwd.value.split('/')
  return parts.map((name, i) => ({ name, path: parts.slice(0, i + 1).join('/') }))
})

function exists(path) {
  return Object.prototype.hasOwnProperty.call(fs.value, path)
}

/** 同名时自动加序号，和 Windows 一个意思 */
function freeName(dir, name) {
  if (!exists(join(dir, name))) return name
  const dot = name.lastIndexOf('.')
  const stem = dot > 0 ? name.slice(0, dot) : name
  const ext = dot > 0 ? name.slice(dot) : ''
  for (let i = 2; i < 100; i++) {
    const tryName = `${stem} (${i})${ext}`
    if (!exists(join(dir, tryName))) return tryName
  }
  return `${stem}-${Date.now()}${ext}`
}

/** 把 from 这棵子树整体挪到 to（改名和移动都走这里） */
function rekey(from, to, { copy = false } = {}) {
  const next = {}
  for (const [path, node] of Object.entries(fs.value)) {
    if (path === from || path.startsWith(from + '/')) {
      next[to + path.slice(from.length)] = JSON.parse(JSON.stringify(node))
      if (!copy) continue
    }
    next[path] = node
  }
  fs.value = next
}

// ---------- 操作 ----------
const err = ref('')
function fail(msg) {
  err.value = msg
  setTimeout(() => (err.value = ''), 2600)
}

function newFolder() {
  if (props.readonly) return
  const name = freeName(cwd.value, '新建文件夹')
  fs.value[join(cwd.value, name)] = { type: 'dir' }
  push({ op: 'mkdir', path: join(cwd.value, name) })
  startRename(join(cwd.value, name))
}

function newFile() {
  if (props.readonly) return
  const name = freeName(cwd.value, '新建文本文档.txt')
  fs.value[join(cwd.value, name)] = { type: 'file', content: '' }
  push({ op: 'touch', path: join(cwd.value, name) })
  startRename(join(cwd.value, name))
}

function open(row) {
  if (row.type === 'dir') {
    cwd.value = row.path
    selected.value = ''
  } else {
    editing.value = { path: row.path, text: String(fs.value[row.path].content || '') }
  }
}

function remove(path) {
  if (props.readonly || !path) return
  const gone = {}
  for (const [p, node] of Object.entries(fs.value)) {
    if (p === path || p.startsWith(path + '/')) gone[p] = node
  }
  Object.assign(recycle.value, gone)
  for (const p of Object.keys(gone)) delete fs.value[p]
  selected.value = ''
  push({ op: 'delete', path })
}

function restore(path) {
  if (props.readonly) return
  for (const [p, node] of Object.entries(recycle.value)) {
    if (p === path || p.startsWith(path + '/')) {
      fs.value[p] = node
      delete recycle.value[p]
    }
  }
  push({ op: 'restore', path })
}

function cut(path) { clip.value = { path, cut: true } }
function copy(path) { clip.value = { path, cut: false } }

function paste() {
  if (props.readonly || !clip.value) return
  const { path, cut: isCut } = clip.value
  if (!exists(path)) return fail('要粘贴的东西已经不在了')
  if (cwd.value === path || cwd.value.startsWith(path + '/')) {
    return fail('不能把文件夹粘贴到它自己里面')
  }
  const name = freeName(cwd.value, baseOf(path))
  rekey(path, join(cwd.value, name), { copy: !isCut })
  if (isCut) clip.value = null
  push({ op: isCut ? 'move' : 'copy', from: path, to: join(cwd.value, name) })
}

// ---------- 改名 ----------
const renaming = ref(null)     // { path, name }
function startRename(path) {
  if (props.readonly) return
  renaming.value = { path, name: baseOf(path) }
}
function commitRename() {
  const r = renaming.value
  renaming.value = null
  if (!r) return
  const name = (r.name || '').trim()
  if (!name || name === baseOf(r.path)) return
  if (/[\\/:*?"<>|]/.test(name)) return fail('文件名里不能有 \\ / : * ? " < > |')
  const target = join(parentOf(r.path), name)
  if (exists(target)) return fail(`「${name}」已经存在了`)
  rekey(r.path, target)
  push({ op: 'rename', from: r.path, to: target })
}

// ---------- 记事本 ----------
const editing = ref(null)      // { path, text }
function saveText() {
  const e = editing.value
  if (e && !props.readonly && fs.value[e.path]) {
    fs.value[e.path].content = e.text
    push({ op: 'write', path: e.path })
  }
  editing.value = null
}

// ---------- 属性 ----------
const props2 = ref(null)       // { path, readonly, hidden }
function openProps(path) {
  const node = fs.value[path]
  if (node) props2.value = { path, readonly: !!node.readonly, hidden: !!node.hidden }
}
function saveProps() {
  const p = props2.value
  if (p && !props.readonly && fs.value[p.path]) {
    fs.value[p.path].readonly = p.readonly
    fs.value[p.path].hidden = p.hidden
    push({ op: 'attr', path: p.path })
  }
  props2.value = null
}

// ---------- 右键菜单 ----------
const menu = ref(null)         // { x, y, path }
function openMenu(e, path) {
  if (props.readonly) return
  menu.value = { x: e.offsetX + 8, y: e.offsetY + 8, path }
}
const closeMenu = () => (menu.value = null)

const inRecycle = ref(false)
const recycleList = computed(() =>
  Object.keys(recycle.value)
    .filter(p => !Object.keys(recycle.value).some(q => p !== q && p.startsWith(q + '/')))
    .map(p => ({ path: p, name: baseOf(p), ...recycle.value[p] }))
)
</script>

<template>
  <div class="win" @click="closeMenu">
    <!-- 地址栏 -->
    <div class="bar">
      <button class="nav" :disabled="cwd === ROOT || inRecycle" @click="cwd = parentOf(cwd) || ROOT">↑</button>
      <div class="addr">
        <template v-if="!inRecycle">
          <span v-for="(c, i) in crumbs" :key="c.path">
            <a @click="cwd = c.path">{{ c.name }}</a>
            <i v-if="i < crumbs.length - 1"> › </i>
          </span>
        </template>
        <span v-else>回收站</span>
      </div>
      <button class="nav" :class="{ on: inRecycle }" @click="inRecycle = !inRecycle">
        🗑 回收站<em v-if="recycleList.length">{{ recycleList.length }}</em>
      </button>
    </div>

    <!-- 工具栏 -->
    <div class="tools" v-if="!inRecycle">
      <button :disabled="readonly" @click="newFolder">新建文件夹</button>
      <button :disabled="readonly" @click="newFile">新建文本文档</button>
      <span class="sep" />
      <button :disabled="readonly || !selected" @click="cut(selected)">剪切</button>
      <button :disabled="readonly || !selected" @click="copy(selected)">复制</button>
      <button :disabled="readonly || !clip" @click="paste">粘贴</button>
      <span class="sep" />
      <button :disabled="readonly || !selected" @click="startRename(selected)">重命名</button>
      <button :disabled="readonly || !selected" @click="remove(selected)">删除</button>
      <button :disabled="!selected" @click="openProps(selected)">属性</button>
    </div>

    <div class="body">
      <!-- 文件夹树 -->
      <aside class="tree">
        <div
          v-for="t in tree"
          :key="t.path"
          class="tnode"
          :class="{ on: !inRecycle && t.path === cwd }"
          :style="{ paddingLeft: 8 + t.depth * 12 + 'px' }"
          @click="inRecycle = false; cwd = t.path"
        >
          📁 {{ t.name }}
        </div>
      </aside>

      <!-- 文件列表 -->
      <main class="files" @contextmenu.prevent="openMenu($event, '')" @click.self="selected = ''">
        <template v-if="!inRecycle">
          <div
            v-for="row in list"
            :key="row.path"
            class="item"
            :class="{ on: selected === row.path, hidden: row.hidden }"
            @click.stop="selected = row.path"
            @dblclick="open(row)"
            @contextmenu.prevent.stop="selected = row.path; openMenu($event, row.path)"
          >
            <span class="ico">{{ row.type === 'dir' ? '📁' : '📄' }}</span>
            <input
              v-if="renaming && renaming.path === row.path"
              v-model="renaming.name"
              class="rename"
              autofocus
              @keyup.enter="commitRename"
              @keyup.esc="renaming = null"
              @blur="commitRename"
              @click.stop
            />
            <span v-else class="name">{{ row.name }}</span>
            <span v-if="row.readonly" class="flag">只读</span>
          </div>
          <p v-if="!list.length" class="empty">这个文件夹是空的。右键空白处可以新建。</p>
        </template>

        <template v-else>
          <div v-for="row in recycleList" :key="row.path" class="item">
            <span class="ico">{{ row.type === 'dir' ? '📁' : '📄' }}</span>
            <span class="name">{{ row.name }}</span>
            <button class="mini" :disabled="readonly" @click="restore(row.path)">还原</button>
          </div>
          <p v-if="!recycleList.length" class="empty">回收站是空的。</p>
        </template>
      </main>
    </div>

    <!-- 右键菜单 -->
    <ul v-if="menu" class="menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" @click.stop="closeMenu">
      <template v-if="menu.path">
        <li @click="open(list.find(r => r.path === menu.path) || {})">打开</li>
        <li @click="cut(menu.path)">剪切</li>
        <li @click="copy(menu.path)">复制</li>
        <li class="line" />
        <li @click="startRename(menu.path)">重命名</li>
        <li @click="remove(menu.path)">删除</li>
        <li class="line" />
        <li @click="openProps(menu.path)">属性</li>
      </template>
      <template v-else>
        <li @click="newFolder">新建 › 文件夹</li>
        <li @click="newFile">新建 › 文本文档</li>
        <li class="line" />
        <li :class="{ dim: !clip }" @click="paste">粘贴</li>
      </template>
    </ul>

    <!-- 记事本 -->
    <div v-if="editing" class="modal" @click.self="editing = null">
      <div class="dlg wide">
        <header>{{ baseOf(editing.path) }} — 记事本</header>
        <textarea v-model="editing.text" :readonly="readonly" spellcheck="false" />
        <footer>
          <button @click="editing = null">取消</button>
          <button class="ok" :disabled="readonly" @click="saveText">保存</button>
        </footer>
      </div>
    </div>

    <!-- 属性 -->
    <div v-if="props2" class="modal" @click.self="props2 = null">
      <div class="dlg">
        <header>{{ baseOf(props2.path) }} 属性</header>
        <div class="pad">
          <p class="path">{{ props2.path }}</p>
          <label><input v-model="props2.readonly" type="checkbox" :disabled="readonly" /> 只读</label>
          <label><input v-model="props2.hidden" type="checkbox" :disabled="readonly" /> 隐藏</label>
        </div>
        <footer>
          <button @click="props2 = null">取消</button>
          <button class="ok" :disabled="readonly" @click="saveProps">确定</button>
        </footer>
      </div>
    </div>

    <p v-if="err" class="err">{{ err }}</p>
  </div>
</template>

<style scoped>
.win {
  position: relative;
  border: 1px solid #9aa3b0;
  border-radius: 6px;
  background: #fff;
  color: #1f2430;
  font-size: 13px;
  user-select: none;
  overflow: hidden;
}
.bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: linear-gradient(#f6f8fb, #e8edf5);
  border-bottom: 1px solid #ccd4e0;
}
.addr {
  flex: 1;
  padding: 3px 8px;
  background: #fff;
  border: 1px solid #ccd4e0;
  border-radius: 3px;
  min-height: 22px;
  overflow: hidden;
  white-space: nowrap;
}
.addr a { color: #14508c; cursor: pointer; }
.addr a:hover { text-decoration: underline; }
.addr i { color: #8a93a3; font-style: normal; }
.nav {
  border: 1px solid #ccd4e0;
  background: #fff;
  border-radius: 3px;
  padding: 3px 9px;
  cursor: pointer;
  font-size: 12px;
}
.nav.on { background: #dceaff; border-color: #7aa7e0; }
.nav em { font-style: normal; margin-left: 4px; color: #c0392b; }
.tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid #e3e8f0;
  background: #fbfcfe;
}
.tools button {
  border: 1px solid #ccd4e0;
  background: #fff;
  border-radius: 3px;
  padding: 3px 9px;
  cursor: pointer;
  font-size: 12px;
}
.tools button:disabled { color: #aab; cursor: default; }
.tools button:not(:disabled):hover { background: #eef4ff; border-color: #7aa7e0; }
.sep { width: 1px; height: 16px; background: #dde3ec; }
.body { display: flex; min-height: 260px; }
.tree {
  width: 150px;
  border-right: 1px solid #e3e8f0;
  background: #fafbfd;
  padding: 6px 0;
  overflow: auto;
}
.tnode { padding: 4px 8px; cursor: pointer; white-space: nowrap; }
.tnode:hover { background: #eef4ff; }
.tnode.on { background: #dceaff; }
.files {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 4px;
  min-height: 260px;
}
.item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 168px;
  padding: 5px 7px;
  border: 1px solid transparent;
  border-radius: 3px;
  cursor: default;
}
.item:hover { background: #f1f6ff; }
.item.on { background: #cfe3ff; border-color: #7aa7e0; }
.item.hidden { opacity: 0.45; }
.item .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .ico { font-size: 15px; }
.item .flag { font-size: 11px; color: #8a93a3; }
.rename { width: 110px; font: inherit; border: 1px solid #7aa7e0; padding: 1px 3px; }
.mini { margin-left: auto; font-size: 11px; padding: 1px 6px; cursor: pointer; }
.empty { color: #8a93a3; padding: 10px; width: 100%; }
.menu {
  position: absolute;
  z-index: 30;
  min-width: 150px;
  margin: 0;
  padding: 4px 0;
  list-style: none;
  background: #fff;
  border: 1px solid #b9c2d0;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
  border-radius: 4px;
}
.menu li { padding: 5px 14px; cursor: pointer; }
.menu li:hover { background: #dceaff; }
.menu li.line { height: 1px; padding: 0; margin: 4px 0; background: #e3e8f0; cursor: default; }
.menu li.dim { color: #aab; }
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
  min-width: 300px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}
.dlg.wide { width: min(620px, 92vw); }
.dlg header {
  padding: 8px 12px;
  background: linear-gradient(#e8edf5, #dbe3ee);
  font-weight: 600;
  border-bottom: 1px solid #ccd4e0;
}
.dlg textarea {
  width: 100%;
  height: 240px;
  border: none;
  padding: 10px 12px;
  font: 13px/1.7 Consolas, monospace;
  resize: vertical;
  outline: none;
}
.dlg .pad { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.dlg .path { margin: 0 0 4px; color: #6b7480; font-size: 12px; word-break: break-all; }
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
.err {
  position: absolute;
  left: 50%;
  bottom: 12px;
  transform: translateX(-50%);
  margin: 0;
  padding: 6px 14px;
  border-radius: 4px;
  background: #fdecea;
  color: #b3261e;
  border: 1px solid #f5c6c0;
  font-size: 12px;
}
</style>

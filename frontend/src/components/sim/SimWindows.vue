<script setup>
/**
 * Windows 文件管理仿真（3.0 换成 XP 桌面样式）。
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
 * ## 3.0 加了什么
 *
 * - 桌面、任务栏、开始菜单、XP 蓝色标题栏和任务窗格，整体照着 XP 的样子做
 * - 认二十多种扩展名（见 fileTypes.js），图标、"新建"菜单、双击行为都按类型来
 * - 记事本能改内容，文档 / 图片 / 音视频 / 压缩包 / 数据库各有查看器；
 *   .exe .msi .bat 双击给「考试环境中不运行程序」的提示
 *
 * ## 没做的事
 *
 * 拖拽、多选、搜索、共享、快捷方式；窗口拖动和真正的多窗口管理也没做 ——
 * 中考的文件管理题考不到，做了只是徒增卡顿。删除一律进回收站。
 */
import { computed, ref, watch } from 'vue'
import { ICONS, NEW_MENU, fakeSize, typeOf } from './fileTypes.js'

const props = defineProps({
  env: { type: Object, required: true },
  modelValue: { type: Object, default: null },
  readonly: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'log'])

const ROOT = 'C:'
const DESKTOP_DIRS = ['C:/桌面', 'C:/Documents and Settings/Administrator/桌面']

// ---------- 状态 ----------
const fs = ref({})
const recycle = ref({})
const cwd = ref(ROOT)
const selected = ref('')
const clip = ref(null)
const view = ref('icons')          // icons 大图标 / details 详细信息
const winOpen = ref(true)          // 资源管理器窗口开着没
const inRecycle = ref(false)

function boot() {
  const src = props.modelValue && props.modelValue.fs ? props.modelValue : props.env
  fs.value = JSON.parse(JSON.stringify(src.fs || {}))
  recycle.value = JSON.parse(JSON.stringify(src.recycle || {}))
  // 只有整个文件系统都空的时候才补一个盘符节点。环境里已经有 C:/EXAM 却硬塞一个
  // C: 进去的话，出题时拿前后状态做差集会凭空多出一条「新建文件夹 C:」的检查点
  if (!Object.keys(fs.value).length) fs.value[ROOT] = { type: 'dir' }
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

function rowOf(path) {
  const node = fs.value[path] || recycle.value[path] || {}
  const t = node.type === 'dir' ? { name: '文件夹', icon: 'folder', cat: '文件夹' } : typeOf(path)
  return { path, name: baseOf(path), ...node, meta: t, size: fakeSize(path, node) }
}

const list = computed(() => children(cwd.value).map(rowOf))
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
const current = computed(() => (selected.value ? rowOf(selected.value) : null))

const desktopDir = computed(() => DESKTOP_DIRS.find(d => fs.value[d]) || '')
const desktopItems = computed(() => (desktopDir.value ? children(desktopDir.value).map(rowOf) : []))

const recycleList = computed(() =>
  Object.keys(recycle.value)
    .filter(p => !Object.keys(recycle.value).some(q => p !== q && p.startsWith(q + '/')))
    .map(rowOf)
)

function exists(path) {
  return Object.prototype.hasOwnProperty.call(fs.value, path)
}

function freeName(dir, name) {
  if (!exists(join(dir, name))) return name
  const dot = name.lastIndexOf('.')
  const stem = dot > 0 ? name.slice(0, dot) : name
  const ext = dot > 0 ? name.slice(dot) : ''
  for (let i = 2; i < 100; i++) {
    if (!exists(join(dir, `${stem} (${i})${ext}`))) return `${stem} (${i})${ext}`
  }
  return `${stem}-${Date.now()}${ext}`
}

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
  setTimeout(() => (err.value = ''), 2800)
}

/** 新建。item 来自 NEW_MENU：文件夹或某种扩展名的空文件 */
function create(item) {
  if (props.readonly) return
  const base = item.dir ? '新建文件夹' : `新建${item.label}.${item.ext}`
  const name = freeName(cwd.value, base)
  const path = join(cwd.value, name)
  fs.value[path] = item.dir ? { type: 'dir' } : { type: 'file', content: '' }
  push({ op: item.dir ? 'mkdir' : 'touch', path })
  startRename(path)
}

function open(row) {
  if (!row || !row.path) return
  if (row.type === 'dir') {
    cwd.value = row.path
    selected.value = ''
    inRecycle.value = false
    winOpen.value = true
    return
  }
  const how = row.meta.open
  if (how === 'notepad') {
    editing.value = { path: row.path, text: String(fs.value[row.path]?.content || '') }
  } else if (how === 'block') {
    fail(`「${row.name}」是${row.meta.name}，考试环境中不运行程序。`)
  } else {
    viewer.value = { path: row.path, row, how }
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

const cut = path => (clip.value = { path, cut: true })
const copy = path => (clip.value = { path, cut: false })

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
const renaming = ref(null)
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
  if (/[\\/:*?"<>|]/.test(name)) return fail('文件名不能包含 \\ / : * ? " < > | 这些字符')
  const target = join(parentOf(r.path), name)
  if (exists(target)) return fail(`「${name}」已经存在了`)
  rekey(r.path, target)
  push({ op: 'rename', from: r.path, to: target })
}

// ---------- 记事本 / 查看器 / 属性 ----------
const editing = ref(null)
function saveText() {
  const e = editing.value
  if (e && !props.readonly && fs.value[e.path]) {
    if (fs.value[e.path].readonly) {
      editing.value = null
      return fail('这个文件是只读的，不能保存修改。')
    }
    fs.value[e.path].content = e.text
    push({ op: 'write', path: e.path })
  }
  editing.value = null
}

const viewer = ref(null)
const attrs = ref(null)
function openProps(path) {
  const node = fs.value[path] || recycle.value[path]
  if (node) attrs.value = { path, readonly: !!node.readonly, hidden: !!node.hidden, row: rowOf(path) }
}
function saveProps() {
  const a = attrs.value
  if (a && !props.readonly && fs.value[a.path]) {
    fs.value[a.path].readonly = a.readonly
    fs.value[a.path].hidden = a.hidden
    push({ op: 'attr', path: a.path })
  }
  attrs.value = null
}

// ---------- 菜单 ----------
const menu = ref(null)             // 右键菜单 { x, y, path }
const startMenu = ref(false)
const newMenu = ref(false)

function openMenu(e, path) {
  if (props.readonly) return
  const box = e.currentTarget.getBoundingClientRect()
  menu.value = { x: e.clientX - box.left + 4, y: e.clientY - box.top + 4, path }
  startMenu.value = false
}
function closeAll() {
  menu.value = null
  startMenu.value = false
  newMenu.value = false
}

const clock = ref('')
function tick() {
  const d = new Date()
  clock.value = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
tick()
setInterval(tick, 20000)
</script>

<template>
  <div class="xp" @click="closeAll">
    <!-- ======================= 桌面 ======================= -->
    <div class="desk" @contextmenu.prevent>
      <button class="dicon" @dblclick="winOpen = true; inRecycle = false; cwd = ROOT">
        <span class="ico" v-html="ICONS.computer" />
        <span>我的电脑</span>
      </button>
      <button
        v-if="desktopDir"
        class="dicon"
        @dblclick="winOpen = true; inRecycle = false; cwd = desktopDir"
      >
        <span class="ico" v-html="ICONS.docs" />
        <span>桌面文件夹</span>
      </button>
      <button class="dicon" @dblclick="winOpen = true; inRecycle = true">
        <span class="ico" v-html="ICONS.recycle" />
        <span>回收站</span>
      </button>
      <button
        v-for="d in desktopItems"
        :key="d.path"
        class="dicon"
        @dblclick="open(d)"
      >
        <span class="ico" v-html="ICONS[d.meta.icon]" />
        <span>{{ d.name }}</span>
      </button>
    </div>

    <!-- ======================= 资源管理器 ======================= -->
    <div v-if="winOpen" class="window">
      <div class="title">
        <span class="tico" v-html="ICONS.folderOpen" />
        <span class="ttext">{{ inRecycle ? '回收站' : cwd }}</span>
        <span class="tbtns">
          <i class="tb min" @click="winOpen = false">–</i>
          <i class="tb max">□</i>
          <i class="tb close" @click="winOpen = false">✕</i>
        </span>
      </div>

      <div class="menubar">
        <span>文件(F)</span><span>编辑(E)</span><span>查看(V)</span>
        <span>收藏(A)</span><span>工具(T)</span><span>帮助(H)</span>
      </div>

      <div class="toolbar">
        <button :disabled="cwd === ROOT || inRecycle" @click="cwd = parentOf(cwd) || ROOT">
          ⬆ 向上
        </button>
        <span class="vsep" />
        <button :disabled="readonly || !selected" @click="cut(selected)">✂ 剪切</button>
        <button :disabled="readonly || !selected" @click="copy(selected)">⧉ 复制</button>
        <button :disabled="readonly || !clip" @click="paste">📋 粘贴</button>
        <span class="vsep" />
        <button :disabled="readonly || !selected" @click="remove(selected)">✖ 删除</button>
        <span class="grow" />
        <button :class="{ on: view === 'icons' }" @click="view = 'icons'">大图标</button>
        <button :class="{ on: view === 'details' }" @click="view = 'details'">详细信息</button>
      </div>

      <div class="addr">
        <span>地址</span>
        <div class="path">
          <span class="ico sm" v-html="ICONS.folderOpen" />
          <template v-if="!inRecycle">
            <span v-for="(c, i) in crumbs" :key="c.path">
              <a @click="cwd = c.path">{{ c.name }}</a><i v-if="i < crumbs.length - 1">\</i>
            </span>
          </template>
          <span v-else>回收站</span>
        </div>
      </div>

      <div class="body">
        <!-- XP 那块蓝色任务窗格 -->
        <aside class="pane">
          <section class="card">
            <h4>文件和文件夹任务</h4>
            <button :disabled="readonly || inRecycle" @click="create(NEW_MENU[0])">
              📁 创建一个新文件夹
            </button>
            <button :disabled="readonly || !selected" @click="startRename(selected)">
              ✎ 重命名这个项目
            </button>
            <button :disabled="readonly || !selected" @click="copy(selected)">⧉ 复制这个项目</button>
            <button :disabled="readonly || !selected" @click="cut(selected)">➦ 移动这个项目</button>
            <button :disabled="readonly || !selected" @click="remove(selected)">✖ 删除这个项目</button>
          </section>

          <section class="card">
            <h4>其它位置</h4>
            <button @click="inRecycle = false; cwd = ROOT">💻 我的电脑</button>
            <button v-if="desktopDir" @click="inRecycle = false; cwd = desktopDir">🗂 桌面</button>
            <button @click="inRecycle = true">🗑 回收站（{{ recycleList.length }}）</button>
          </section>

          <section class="card">
            <h4>详细信息</h4>
            <template v-if="current">
              <p class="big">{{ current.name }}</p>
              <p>{{ current.meta.name }}</p>
              <p v-if="current.size">大小：{{ current.size }}</p>
              <p v-if="current.readonly">属性：只读</p>
            </template>
            <p v-else class="dim">当前文件夹里有 {{ list.length }} 个项目</p>
          </section>

          <section class="card tree">
            <h4>文件夹</h4>
            <button
              v-for="t in tree"
              :key="t.path"
              class="tnode"
              :class="{ on: !inRecycle && t.path === cwd }"
              :style="{ paddingLeft: 8 + t.depth * 11 + 'px' }"
              @click="inRecycle = false; cwd = t.path"
            >📁 {{ t.name }}</button>
          </section>
        </aside>

        <!-- 文件列表 -->
        <main
          class="files"
          :class="view"
          @contextmenu.prevent.stop="openMenu($event, '')"
          @click.self="selected = ''"
        >
          <template v-if="!inRecycle">
            <div v-if="view === 'details'" class="head-row">
              <span class="c-name">名称</span><span class="c-size">大小</span><span class="c-type">类型</span>
            </div>
            <div
              v-for="row in list"
              :key="row.path"
              class="item"
              :class="{ on: selected === row.path, hide: row.hidden }"
              @click.stop="selected = row.path"
              @dblclick="open(row)"
              @contextmenu.prevent.stop="selected = row.path; openMenu($event, row.path)"
            >
              <span class="ico" v-html="ICONS[row.meta.icon]" />
              <input
                v-if="renaming && renaming.path === row.path"
                v-model="renaming.name"
                class="rename"
                @keyup.enter="commitRename"
                @keyup.esc="renaming = null"
                @blur="commitRename"
                @click.stop
              />
              <span v-else class="c-name">{{ row.name }}</span>
              <span class="c-size">{{ row.size }}</span>
              <span class="c-type">{{ row.meta.name }}</span>
            </div>
            <p v-if="!list.length" class="empty">这个文件夹是空的。在空白处点右键可以新建。</p>
          </template>

          <template v-else>
            <div v-for="row in recycleList" :key="row.path" class="item">
              <span class="ico" v-html="ICONS[row.meta.icon]" />
              <span class="c-name">{{ row.name }}</span>
              <button class="mini" :disabled="readonly" @click="restore(row.path)">还原</button>
            </div>
            <p v-if="!recycleList.length" class="empty">回收站是空的。</p>
          </template>
        </main>
      </div>

      <div class="status">
        <span>{{ inRecycle ? recycleList.length : list.length }} 个对象</span>
        <span v-if="current">　{{ current.meta.name }}<template v-if="current.size">　{{ current.size }}</template></span>
        <span class="grow" />
        <span>{{ clip ? (clip.cut ? '已剪切：' : '已复制：') + baseOf(clip.path) : '' }}</span>
      </div>
    </div>

    <!-- ======================= 任务栏 ======================= -->
    <div class="taskbar">
      <button class="start" @click.stop="startMenu = !startMenu">开始</button>
      <button v-if="winOpen" class="task on" @click="winOpen = true">
        <span class="ico sm" v-html="ICONS.folderOpen" />{{ inRecycle ? '回收站' : baseOf(cwd) || cwd }}
      </button>
      <button v-else class="task" @click="winOpen = true">
        <span class="ico sm" v-html="ICONS.folderOpen" />资源管理器
      </button>
      <span class="grow" />
      <span class="tray">{{ clock }}</span>
    </div>

    <ul v-if="startMenu" class="startmenu" @click.stop="startMenu = false">
      <li @click="winOpen = true; inRecycle = false; cwd = ROOT"><span v-html="ICONS.computer" />我的电脑</li>
      <li v-if="desktopDir" @click="winOpen = true; inRecycle = false; cwd = desktopDir">
        <span v-html="ICONS.docs" />桌面文件夹
      </li>
      <li @click="winOpen = true; inRecycle = true"><span v-html="ICONS.recycle" />回收站</li>
    </ul>

    <!-- ======================= 右键菜单 ======================= -->
    <ul v-if="menu" class="menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" @click.stop="closeAll">
      <template v-if="menu.path">
        <li class="b" @click="open(rowOf(menu.path))">打开</li>
        <li class="line" />
        <li @click="cut(menu.path)">剪切</li>
        <li @click="copy(menu.path)">复制</li>
        <li class="line" />
        <li @click="remove(menu.path)">删除</li>
        <li @click="startRename(menu.path)">重命名</li>
        <li class="line" />
        <li @click="openProps(menu.path)">属性</li>
      </template>
      <template v-else>
        <li :class="{ dim: !clip }" @click="paste">粘贴</li>
        <li class="line" />
        <li class="sub" @click.stop="newMenu = !newMenu">
          新建 ▸
          <ul v-if="newMenu" class="submenu">
            <li v-for="n in NEW_MENU" :key="n.label" @click.stop="closeAll(); create(n)">{{ n.label }}</li>
          </ul>
        </li>
      </template>
    </ul>

    <!-- ======================= 记事本 ======================= -->
    <div v-if="editing" class="modal" @click.self="editing = null">
      <div class="dlg wide">
        <div class="title sm">
          <span class="ttext">{{ baseOf(editing.path) }} － 记事本</span>
          <span class="tbtns"><i class="tb close" @click="editing = null">✕</i></span>
        </div>
        <div class="menubar"><span>文件(F)</span><span>编辑(E)</span><span>格式(O)</span><span>帮助(H)</span></div>
        <textarea v-model="editing.text" :readonly="readonly" spellcheck="false" />
        <footer>
          <button @click="editing = null">取消</button>
          <button class="ok" :disabled="readonly" @click="saveText">保存</button>
        </footer>
      </div>
    </div>

    <!-- ======================= 各类查看器 ======================= -->
    <div v-if="viewer" class="modal" @click.self="viewer = null">
      <div class="dlg wide">
        <div class="title sm">
          <span class="ttext">{{ viewer.row.name }} － {{ viewer.row.meta.name }}</span>
          <span class="tbtns"><i class="tb close" @click="viewer = null">✕</i></span>
        </div>

        <div class="vbody">
          <!-- 文档：有内容就显示内容，没有就说明这是个文档 -->
          <div v-if="viewer.how === 'doc'" class="doc">
            <pre v-if="fs[viewer.path] && fs[viewer.path].content">{{ fs[viewer.path].content }}</pre>
            <p v-else class="dim">这是一个{{ viewer.row.meta.name }}，内容在考试环境中不显示。</p>
          </div>

          <!-- 图片：画一张占位图，不去加载任何真实图片 -->
          <div v-else-if="viewer.how === 'image'" class="pic">
            <svg viewBox="0 0 320 200" class="ph">
              <rect width="320" height="200" fill="#dce6f2" />
              <circle cx="80" cy="60" r="22" fill="#f2c14e" />
              <path d="M20 170l80-80 55 55 45-35 100 60z" fill="#4f9d5a" />
            </svg>
            <p class="dim">{{ viewer.row.name }}　{{ viewer.row.size }}</p>
          </div>

          <!-- 音视频：一个不会真播放的播放器 -->
          <div v-else-if="viewer.how === 'media'" class="media">
            <div class="screen">
              <span class="ico big" v-html="ICONS[viewer.row.meta.icon]" />
            </div>
            <div class="bar"><span class="played" /></div>
            <p class="dim">{{ viewer.row.meta.name }}　{{ viewer.row.size }}　（仿真环境不实际播放）</p>
          </div>

          <!-- 压缩包：列出里面有什么（题目没给内容就说明是空包） -->
          <div v-else-if="viewer.how === 'archive'" class="doc">
            <p class="dim">压缩文件：{{ viewer.row.name }}　{{ viewer.row.size }}</p>
            <pre v-if="fs[viewer.path] && fs[viewer.path].content">{{ fs[viewer.path].content }}</pre>
            <p v-else class="dim">（仿真环境中不解压，需要解压的操作请按题目要求进行）</p>
          </div>

          <div v-else class="doc">
            <p class="dim">{{ viewer.row.meta.name }}，仿真环境中不打开。</p>
          </div>
        </div>
        <footer><button class="ok" @click="viewer = null">关闭</button></footer>
      </div>
    </div>

    <!-- ======================= 属性 ======================= -->
    <div v-if="attrs" class="modal" @click.self="attrs = null">
      <div class="dlg">
        <div class="title sm">
          <span class="ttext">{{ baseOf(attrs.path) }} 属性</span>
          <span class="tbtns"><i class="tb close" @click="attrs = null">✕</i></span>
        </div>
        <div class="pad">
          <div class="prow"><span class="ico" v-html="ICONS[attrs.row.meta.icon]" /><b>{{ attrs.row.name }}</b></div>
          <p class="kv"><span>类型：</span>{{ attrs.row.meta.name }}</p>
          <p class="kv"><span>位置：</span>{{ parentOf(attrs.path) }}</p>
          <p class="kv" v-if="attrs.row.size"><span>大小：</span>{{ attrs.row.size }}</p>
          <p class="kv"><span>属性：</span>
            <label><input v-model="attrs.readonly" type="checkbox" :disabled="readonly" /> 只读</label>
            <label><input v-model="attrs.hidden" type="checkbox" :disabled="readonly" /> 隐藏</label>
          </p>
        </div>
        <footer>
          <button @click="attrs = null">取消</button>
          <button class="ok" :disabled="readonly" @click="saveProps">确定</button>
        </footer>
      </div>
    </div>

    <p v-if="err" class="err">{{ err }}</p>
  </div>
</template>

<style scoped>
/* ---------------- 桌面 ---------------- */
.xp {
  position: relative;
  height: 520px;
  border: 1px solid #5a7fb5;
  border-radius: 4px;
  overflow: hidden;
  background: linear-gradient(#4a8fdc 0%, #6fb2e8 42%, #86c56b 60%, #5aa04c 100%);
  font: 12px/1.5 "Microsoft YaHei", "SimSun", sans-serif;
  color: #1f2430;
  user-select: none;
}
.desk { position: absolute; inset: 0 0 30px 0; padding: 10px; display: flex; flex-direction: column; flex-wrap: wrap; align-content: flex-start; gap: 4px; }
.dicon {
  width: 76px; padding: 6px 2px; border: 1px solid transparent; background: none;
  color: #fff; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6); cursor: default;
  display: flex; flex-direction: column; align-items: center; gap: 3px; font: inherit;
}
.dicon:hover { background: rgba(255, 255, 255, 0.16); border-color: rgba(255, 255, 255, 0.35); }
.ico { width: 32px; height: 32px; display: inline-block; flex: none; }
.ico :deep(svg) { width: 100%; height: 100%; display: block; }
.ico.sm { width: 16px; height: 16px; }
.ico.big { width: 64px; height: 64px; }

/* ---------------- 窗口 ---------------- */
.window {
  position: absolute; left: 24px; top: 16px; right: 24px; bottom: 44px;
  display: flex; flex-direction: column;
  background: #ece9d8; border: 3px solid #0054e3; border-top: none;
  border-radius: 8px 8px 2px 2px; box-shadow: 0 8px 26px rgba(0, 0, 0, 0.35);
}
.title {
  display: flex; align-items: center; gap: 6px; padding: 3px 4px 4px 7px;
  background: linear-gradient(#3f8ff5 0%, #1b5fdd 8%, #1550cf 45%, #2f79ea 92%, #0f47bf 100%);
  color: #fff; font-weight: 700; text-shadow: 1px 1px 1px rgba(0, 0, 0, 0.45);
  border-radius: 6px 6px 0 0; margin: -0 -0 0 -0;
}
.title.sm { border-radius: 4px 4px 0 0; }
.tico { width: 18px; height: 18px; }
.tico :deep(svg) { width: 100%; height: 100%; }
.ttext { flex: 1; font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tbtns { display: flex; gap: 2px; }
.tb {
  width: 20px; height: 18px; line-height: 17px; text-align: center; font-style: normal;
  font-size: 11px; border: 1px solid #ffffff88; border-radius: 3px;
  background: linear-gradient(#5b9bf8, #1b5fdd); cursor: pointer;
}
.tb.close { background: linear-gradient(#f08b6a, #c93b12); }
.menubar { display: flex; gap: 14px; padding: 3px 10px; background: #ece9d8; border-bottom: 1px solid #d6d2c0; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 4px; padding: 4px 8px; background: linear-gradient(#fbfaf5, #ece9d8); border-bottom: 1px solid #d6d2c0; }
.toolbar button, .addr button {
  border: 1px solid transparent; background: none; padding: 2px 8px; border-radius: 3px;
  cursor: pointer; font: inherit;
}
.toolbar button:hover:not(:disabled) { border-color: #a8bcd8; background: #e3edfb; }
.toolbar button:disabled { color: #a0a0a0; cursor: default; }
.toolbar button.on { border-color: #a8bcd8; background: #d6e6fb; }
.vsep { width: 1px; height: 16px; background: #cfcbb8; margin: 0 3px; }
.grow { flex: 1; }
.addr { display: flex; align-items: center; gap: 6px; padding: 3px 8px; background: #ece9d8; border-bottom: 1px solid #d6d2c0; }
.addr .path { flex: 1; display: flex; align-items: center; gap: 4px; background: #fff; border: 1px solid #7f9db9; padding: 2px 6px; height: 20px; overflow: hidden; white-space: nowrap; }
.addr a { color: #14508c; cursor: pointer; }
.addr a:hover { text-decoration: underline; }
.addr i { color: #8a93a3; font-style: normal; margin: 0 2px; }

.body { flex: 1; display: flex; min-height: 0; background: #fff; }
.pane {
  width: 168px; flex: none; overflow: auto; padding: 8px 6px;
  background: linear-gradient(#7ba7e8, #a7c4ee 40%, #cfe0f7);
  border-right: 1px solid #b9c8e0;
}
.card { background: #fff; border-radius: 5px; margin-bottom: 8px; overflow: hidden; }
.card h4 {
  margin: 0; padding: 4px 8px; font-size: 12px; color: #1c3f94;
  background: linear-gradient(#f4f8ff, #dbe7fb); border-bottom: 1px solid #cbd9f0;
}
.card button {
  display: block; width: 100%; text-align: left; border: none; background: none;
  padding: 4px 8px; font: inherit; color: #14508c; cursor: pointer;
}
.card button:hover:not(:disabled) { background: #eaf2ff; text-decoration: underline; }
.card button:disabled { color: #9aa7b8; cursor: default; }
.card p { margin: 0; padding: 2px 8px; font-size: 11.5px; color: #4a5361; }
.card p.big { font-weight: 700; color: #1f2430; padding-top: 5px; }
.card .dim { color: #8a93a3; padding-bottom: 5px; }
.card.tree { max-height: 150px; overflow: auto; }
.tnode { white-space: nowrap; }
.tnode.on { background: #cfe3ff; }

.files { flex: 1; padding: 8px; overflow: auto; }
.files.icons { display: flex; flex-wrap: wrap; align-content: flex-start; gap: 2px; }
.files.icons .item {
  width: 96px; flex-direction: column; text-align: center; gap: 3px; padding: 6px 3px;
}
.files.icons .c-size, .files.icons .c-type, .files.icons .head-row { display: none; }
.item {
  display: flex; align-items: center; gap: 7px; padding: 3px 6px;
  border: 1px solid transparent; border-radius: 2px; cursor: default;
}
.item:hover { background: #eef5ff; }
.item.on { background: #316ac5; color: #fff; }
.item.hide { opacity: 0.45; }
.item .c-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head-row { display: flex; gap: 7px; padding: 2px 6px; border-bottom: 1px solid #d6d2c0; color: #4a5361; font-weight: 600; }
.head-row .c-name, .item .c-name { flex: 1; min-width: 0; }
.head-row .c-size, .item .c-size { width: 74px; text-align: right; color: inherit; }
.head-row .c-type, .item .c-type { width: 120px; }
.rename { flex: 1; min-width: 60px; font: inherit; border: 1px solid #316ac5; padding: 0 3px; }
.mini { margin-left: auto; font: inherit; font-size: 11px; padding: 0 6px; cursor: pointer; }
.empty { color: #8a93a3; padding: 12px; width: 100%; }
.status { display: flex; align-items: center; gap: 4px; padding: 2px 8px; background: #ece9d8; border-top: 1px solid #d6d2c0; font-size: 11.5px; color: #4a5361; }

/* ---------------- 任务栏 ---------------- */
.taskbar {
  position: absolute; left: 0; right: 0; bottom: 0; height: 30px;
  display: flex; align-items: center; gap: 5px; padding-right: 6px;
  background: linear-gradient(#3f8ff5 0%, #245edb 9%, #1f57d0 88%, #1c4fbe 100%);
  border-top: 1px solid #66a3f5;
}
.start {
  height: 26px; margin: 2px 6px 2px 0; padding: 0 20px 0 12px; border: none;
  border-radius: 0 12px 12px 0; cursor: pointer; font: 700 13px "Microsoft YaHei";
  color: #fff; text-shadow: 1px 1px 2px #1c4a1c;
  background: linear-gradient(#6cc04a 0%, #3f9b21 45%, #2f8416 100%);
}
.task {
  display: flex; align-items: center; gap: 5px; height: 22px; padding: 0 10px;
  border: 1px solid #3c74d4; border-radius: 3px; color: #fff; font: inherit; cursor: pointer;
  background: linear-gradient(#4a8ae8, #2b65cf); max-width: 200px;
}
.task.on { background: linear-gradient(#2255b8, #3e7ddd); }
.tray { color: #fff; font-size: 12px; padding: 0 6px; border-left: 1px solid #5b8fe0; }
.startmenu {
  position: absolute; left: 4px; bottom: 32px; z-index: 40; margin: 0; padding: 5px;
  list-style: none; min-width: 178px; background: #fff; border: 2px solid #1550cf;
  border-radius: 5px; box-shadow: 0 8px 22px rgba(0, 0, 0, 0.4);
}
.startmenu li { display: flex; align-items: center; gap: 8px; padding: 5px 8px; cursor: pointer; }
.startmenu li:hover { background: #316ac5; color: #fff; }
.startmenu li :deep(svg) { width: 20px; height: 20px; }

/* ---------------- 菜单 ---------------- */
.menu {
  position: absolute; z-index: 45; min-width: 142px; margin: 0; padding: 2px;
  list-style: none; background: #fff; border: 1px solid #9aa7b8;
  box-shadow: 2px 3px 8px rgba(0, 0, 0, 0.3);
}
.menu li { padding: 4px 22px 4px 14px; cursor: pointer; position: relative; }
.menu li:hover { background: #316ac5; color: #fff; }
.menu li.b { font-weight: 700; }
.menu li.line { height: 1px; padding: 0; margin: 3px 2px; background: #d6d2c0; }
.menu li.line:hover { background: #d6d2c0; }
.menu li.dim { color: #a0a0a0; }
.submenu {
  position: absolute; left: 100%; top: -2px; margin: 0; padding: 2px; min-width: 150px;
  list-style: none; background: #fff; border: 1px solid #9aa7b8; color: #1f2430;
  box-shadow: 2px 3px 8px rgba(0, 0, 0, 0.3);
}

/* ---------------- 对话框 ---------------- */
.modal { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.25); display: flex; align-items: center; justify-content: center; z-index: 50; }
.dlg { background: #ece9d8; border: 3px solid #0054e3; border-top: none; border-radius: 8px 8px 3px 3px; min-width: 300px; box-shadow: 0 10px 34px rgba(0, 0, 0, 0.4); overflow: hidden; }
.dlg.wide { width: min(600px, 92%); }
.dlg textarea { width: 100%; height: 230px; border: none; border-top: 1px solid #d6d2c0; padding: 8px 10px; font: 13px/1.7 "SimSun", Consolas, monospace; resize: vertical; outline: none; }
.dlg .pad { padding: 12px; background: #ece9d8; }
.prow { display: flex; align-items: center; gap: 8px; padding-bottom: 8px; border-bottom: 1px solid #d6d2c0; margin-bottom: 8px; }
.kv { margin: 4px 0; display: flex; align-items: center; gap: 6px; }
.kv > span:first-child { width: 48px; color: #4a5361; }
.kv label { display: flex; align-items: center; gap: 3px; margin-right: 12px; }
.vbody { background: #fff; min-height: 200px; max-height: 320px; overflow: auto; padding: 12px; }
.doc pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 13px/1.8 "SimSun", serif; }
.dim { color: #8a93a3; }
.pic { text-align: center; }
.pic .ph { width: min(320px, 100%); border: 1px solid #ccd4e0; }
.media { text-align: center; }
.media .screen { background: #1c1f26; padding: 26px; display: flex; justify-content: center; }
.media .bar { height: 6px; background: #d6d2c0; margin: 10px 0 6px; }
.media .played { display: block; width: 0; height: 100%; background: #4a90d9; }
.dlg footer { display: flex; justify-content: flex-end; gap: 8px; padding: 8px 12px; background: #ece9d8; border-top: 1px solid #d6d2c0; }
.dlg footer button { min-width: 72px; padding: 3px 12px; border: 1px solid #7f9db9; border-radius: 3px; background: linear-gradient(#fdfdfd, #e6e6e6); cursor: pointer; font: inherit; }
.dlg footer .ok { border-color: #2c6fd1; background: linear-gradient(#5b9bf8, #2c6fd1); color: #fff; }
.err {
  position: absolute; left: 50%; bottom: 40px; transform: translateX(-50%); z-index: 60;
  margin: 0; padding: 7px 16px; border-radius: 4px; background: #fffbe6;
  color: #8a5a00; border: 1px solid #f0d48a; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
}

@media (max-width: 720px) {
  .xp { height: 460px; }
  .window { left: 6px; right: 6px; top: 6px; }
  .pane { display: none; }
}
</style>

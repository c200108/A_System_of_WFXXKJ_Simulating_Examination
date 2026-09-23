<script setup>
/**
 * 拖拽题：流程图补全、结构图热区、设备归类、程序填空 / 排序、本机 IP 查询。
 *
 * 图是服务端按原题重画的结构（backend/app/services/drag.py），**桌面端用同一份
 * 数据画 Tk 画布**（desktop/client/dragboard.py），两边长一个样、交上去的也是同一
 * 种终态：
 *
 *     { placed: { A: ['i1'], B: ['i3'] } }     热区 → 放进去的卡片
 *     { ip: '192.168.1.108' }                   IP 查询：仿真命令行里查到的地址
 *
 * 图用 SVG 画（viewBox 跟着页面缩放）；热区是叠在 SVG 上的一层透明 div，
 * 用原生的 HTML5 拖放 —— 放卡片、换位置、拖回素材区都是同一套事件。
 */
import { computed, ref } from 'vue'

const props = defineProps({
  env: { type: Object, required: true },
  modelValue: { type: Object, default: null },
  readonly: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'log'])

const mode = computed(() => props.env.mode || 'diagram')
const W = computed(() => props.env.w || 720)
const H = computed(() => props.env.h || 400)
const items = computed(() => props.env.items || [])
const slots = computed(() => props.env.slots || [])
const slotById = computed(() => Object.fromEntries(slots.value.map((s) => [s.id, s])))
const itemById = computed(() => Object.fromEntries(items.value.map((i) => [i.id, i])))

// ---------------------------------------------------------------- 状态
const placed = ref(clone(props.modelValue?.placed || {}))
const ip = ref(props.modelValue?.ip || '')

function clone(obj) {
  return JSON.parse(JSON.stringify(obj || {}))
}

function whereIs(iid) {
  for (const [sid, got] of Object.entries(placed.value)) if (got.includes(iid)) return sid
  return ''
}

const loose = computed(() => items.value.filter((it) => !whereIs(it.id)))

/** 把卡片放进热区（sid 为空就是拿回素材区）。一张卡片同一时刻只在一个地方。 */
function place(iid, sid) {
  if (props.readonly) return
  const next = clone(placed.value)
  for (const k of Object.keys(next)) next[k] = next[k].filter((x) => x !== iid)
  if (sid) {
    const cap = slotById.value[sid]?.cap || 1
    const here = next[sid] || []
    while (here.length >= cap) here.shift()   // 满了：最早放进去的那张退回素材区
    here.push(iid)
    next[sid] = here
  }
  for (const k of Object.keys(next)) if (!next[k].length) delete next[k]
  placed.value = next
  emit('update:modelValue', { placed: next })
  emit('log', { t: Date.now(), act: sid ? 'place' : 'remove', item: iid, slot: sid })
}

// ---------------------------------------------------------------- 拖放
const dragging = ref('')
const over = ref('')
// **每块作答区一个暗号，拖放时带在数据里。** 一张卷子上有好几道拖拽题，每道题的
// 卡片都叫 i1、i2……—— 不认暗号的话，把第 2 题的卡片拖过第 1 题，第 1 题会把它
// 当成自己的 i1 收下（或者从自己的热区里拿掉），学生的作答就被悄悄改了。
// 联调时真撞上过：拖第 2 题，第 1 题的两张卡片被退回了素材区。
const board = Math.random().toString(36).slice(2, 10)

function onDragStart(e, iid) {
  if (props.readonly) return e.preventDefault()
  dragging.value = iid
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', `${board}:${iid}`)
}
function onDrop(e, sid) {
  const [from, iid] = (e.dataTransfer.getData('text/plain') || '').split(':')
  over.value = ''
  dragging.value = ''
  if (from !== board) return               // 别的题的卡片：不收，也不动自己的
  if (iid && itemById.value[iid]) place(iid, sid)
}

// ---------------------------------------------------------------- 画图的小工具
const pct = (v, total) => `${(v / total) * 100}%`
function slotStyle(s) {
  return { left: pct(s.x, W.value), top: pct(s.y, H.value),
           width: pct(s.w, W.value), height: pct(s.h, H.value) }
}
function polyPoints(s) {
  const { x, y, w, h } = s
  if (s.shape === 'diamond') return `${x + w / 2},${y} ${x + w},${y + h / 2} ${x + w / 2},${y + h} ${x},${y + h / 2}`
  const k = Math.min(14, w / 6)                      // para：平行四边形
  return `${x + k},${y} ${x + w},${y} ${x + w - k},${y + h} ${x},${y + h}`
}
const FILL = { device: '#f4f6fa', note: '#fffbe8', cloud: '#e8f1ff', circle: '#f1f7ff' }
function lines(text) {
  return String(text || '').split('\n')
}

// ---------------------------------------------------------------- 仿真命令行（IP 题）
const term = ref([
  'Microsoft Windows [版本 6.1.7601]',
  '版权所有 (c) 2009 Microsoft Corporation。保留所有权利。',
  ''
])
const cmd = ref('')
const PROMPT = 'C:\\Users\\student>'
function run() {
  const c = cmd.value.trim()
  const out = [PROMPT + c]
  const low = c.toLowerCase()
  if (low === 'ipconfig' || low === 'ipconfig /all') {
    out.push('', 'Windows IP 配置', '', '',
      '以太网适配器 本地连接:', '',
      '   连接特定的 DNS 后缀 . . . . . . . :',
      `   IPv4 地址 . . . . . . . . . . . . : ${props.env.sim_ip || ''}`,
      `   子网掩码  . . . . . . . . . . . . : ${props.env.mask || '255.255.255.0'}`,
      `   默认网关. . . . . . . . . . . . . : ${props.env.gateway || ''}`, '')
  } else if (low === 'hostname') {
    out.push(props.env.host || 'STUDENT-PC', '')
  } else if (low === 'cls') {
    term.value = []
    cmd.value = ''
    return
  } else if (c) {
    out.push(`'${c}' 不是内部或外部命令，也不是可运行的程序`, '或批处理文件。', '')
  }
  term.value = [...term.value, ...out].slice(-120)
  cmd.value = ''
  emit('log', { t: Date.now(), act: 'cmd', text: c })
}
const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/
const ipOk = computed(() => IPV4.test(ip.value.trim()))
function onIp() {
  if (props.readonly) return
  emit('update:modelValue', { ip: ip.value.trim() })
}
</script>

<template>
  <div class="drag">
    <p v-if="env.tip" class="tip">{{ env.tip }}</p>

    <!-- ============================== IP 查询 ============================== -->
    <template v-if="mode === 'ip'">
      <div class="term" @click="$refs.cmdBox?.focus()">
        <div v-for="(l, i) in term" :key="i" class="tl">{{ l || ' ' }}</div>
        <div class="tl">
          <span>{{ PROMPT }}</span>
          <input ref="cmdBox" v-model="cmd" class="tin" :disabled="readonly" spellcheck="false"
                 @keydown.enter="run" />
        </div>
      </div>
      <label class="ipline">
        查到的 IPv4 地址：
        <input v-model="ip" class="ipbox" :disabled="readonly" placeholder="例如 192.168.1.23"
               @input="onIp" />
        <span v-if="ip && !ipOk" class="bad">格式不对：四组 0～255 的数字，用点隔开</span>
        <span v-else-if="ip" class="ok">格式正确，交卷时一起提交</span>
      </label>
    </template>

    <template v-else>
      <!-- ============================== 素材区 ============================== -->
      <div class="palette" :class="{ over: over === '__palette' }"
           @dragover.prevent="over = '__palette'" @dragleave="over = ''"
           @drop.prevent="onDrop($event, '')">
        <span class="plabel">素材区</span>
        <span v-for="it in loose" :key="it.id" class="chip"
              :class="[{ diamond: it.shape === 'diamond', code: mode === 'code' }]"
              :draggable="!readonly" @dragstart="onDragStart($event, it.id)"
              @dragend="dragging = ''">{{ it.text }}</span>
        <span v-if="!loose.length" class="empty">卡片都放上去了。要改的话，把卡片拖回这里</span>
      </div>

      <!-- ============================== 程序 ============================== -->
      <div v-if="mode === 'code'" class="code">
        <div v-for="(row, r) in env.rows" :key="r" class="crow">
          <template v-for="(seg, k) in row" :key="k">
            <span v-if="typeof seg === 'string'" class="ctext">{{ seg }}</span>
            <span v-else class="cslot" :class="{ over: over === seg.slot }"
                  :style="{ minWidth: (slotById[seg.slot]?.w || 110) + 'px' }"
                  @dragover.prevent="over = seg.slot" @dragleave="over = ''"
                  @drop.prevent="onDrop($event, seg.slot)">
              <span v-for="iid in placed[seg.slot] || []" :key="iid" class="chip code in"
                    :draggable="!readonly" @dragstart="onDragStart($event, iid)"
                    @dblclick="place(iid, '')">{{ itemById[iid]?.text }}</span>
              <span v-if="!(placed[seg.slot] || []).length" class="slabel">
                {{ slotById[seg.slot]?.label || seg.slot }}
              </span>
            </span>
          </template>
        </div>
      </div>

      <!-- ============================== 结构图 ============================== -->
      <div v-else class="board" :style="{ maxWidth: W + 'px', aspectRatio: `${W} / ${H}` }">
        <svg :viewBox="`0 0 ${W} ${H}`" class="svg">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"
                    markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#555" />
            </marker>
          </defs>
          <template v-for="(s, i) in env.shapes" :key="i">
            <g v-if="s.t === 'line'">
              <polyline :points="s.pts.map((p) => p.join(',')).join(' ')" fill="none"
                        stroke="#555" stroke-width="1.5" :stroke-dasharray="s.dash ? '5 3' : null"
                        :marker-end="s.arrow ? 'url(#arrow)' : null" />
              <text v-if="s.text" :x="(s.pts[0][0] + s.pts[1][0]) / 2 + 10"
                    :y="(s.pts[0][1] + s.pts[1][1]) / 2 - 6" class="lt">{{ s.text }}</text>
            </g>
            <g v-else-if="s.t === 'zone'">
              <rect :x="s.x" :y="s.y" :width="s.w" :height="s.h" fill="none" stroke="#6b7a99"
                    stroke-dasharray="4 3" />
              <text :x="s.x + 6" :y="s.y + 15" class="zt">{{ s.text }}</text>
            </g>
            <g v-else-if="s.t === 'box'">
              <ellipse v-if="s.shape === 'cloud' || s.shape === 'circle'" :cx="s.x + s.w / 2"
                       :cy="s.y + s.h / 2" :rx="s.w / 2" :ry="s.h / 2" :fill="FILL[s.shape]"
                       stroke="#555" stroke-width="1.5" />
              <polygon v-else-if="s.shape === 'diamond' || s.shape === 'para'" :points="polyPoints(s)"
                       fill="#fff" stroke="#555" stroke-width="1.5" />
              <rect v-else :x="s.x" :y="s.y" :width="s.w" :height="s.h"
                    :rx="s.shape === 'round' ? 12 : 0" :fill="FILL[s.shape] || '#fff'" stroke="#555"
                    stroke-width="1.5" />
              <text :x="s.x + s.w / 2" :y="s.y + s.h / 2 - (lines(s.text).length - 1) * 8"
                    class="bt" text-anchor="middle" dominant-baseline="middle">
                <tspan v-for="(l, k) in lines(s.text)" :key="k" :x="s.x + s.w / 2"
                       :dy="k ? 16 : 0">{{ l }}</tspan>
              </text>
            </g>
          </template>
          <!-- 热区的虚线框画在 SVG 里（菱形热区也是菱形），接收拖放的是上面那层 div -->
          <template v-for="s in slots" :key="'s' + s.id">
            <polygon v-if="s.shape === 'diamond'" :points="polyPoints(s)" class="sbox"
                     :class="{ over: over === s.id }" />
            <rect v-else :x="s.x" :y="s.y" :width="s.w" :height="s.h" class="sbox"
                  :class="{ over: over === s.id }" />
          </template>
        </svg>

        <div v-for="s in slots" :key="'d' + s.id" class="drop"
             :class="{ many: (s.cap || 1) > 1 }" :style="slotStyle(s)"
             @dragover.prevent="over = s.id" @dragleave="over = ''"
             @drop.prevent="onDrop($event, s.id)">
          <span v-if="!(placed[s.id] || []).length || (s.cap || 1) > 1" class="slabel"
                :class="{ top: (s.cap || 1) > 1 }">{{ s.label || s.id }}</span>
          <span v-for="iid in placed[s.id] || []" :key="iid" class="chip in"
                :draggable="!readonly" title="拖出去可以拿回素材区，双击也行"
                @dragstart="onDragStart($event, iid)" @dblclick="place(iid, '')">
            {{ itemById[iid]?.text }}
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.drag { display: flex; flex-direction: column; gap: 10px; }
.tip { margin: 0; color: #7a828e; font-size: 13px; }

.palette {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  min-height: 48px; padding: 10px 12px; border: 1px solid #d8dfea; border-radius: 6px;
  background: #fafcff;
}
.palette.over { border-color: #2c6fd1; background: #f0f6ff; }
.plabel { color: #7a828e; font-size: 12px; margin-right: 4px; }
.empty { color: #b9c2d0; font-size: 12px; }

.chip {
  display: inline-block; padding: 5px 14px; border: 1px solid #8fb0e6; border-radius: 6px;
  background: #eef4ff; color: #1d3557; font-size: 14px; cursor: grab; user-select: none;
  white-space: nowrap;
}
.chip:active { cursor: grabbing; }
.chip.diamond { clip-path: polygon(50% 0, 100% 50%, 50% 100%, 0 50%); padding: 10px 30px; }
.chip.code { font-family: 'NSimSun', 'SimSun', Consolas, monospace; white-space: pre; text-align: left; }
.chip.in { font-size: 13px; padding: 3px 10px; }

.board { position: relative; width: 100%; border: 1px solid #d8dfea; border-radius: 6px;
         background: #fff; }
.svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.bt { font-size: 13px; fill: #222; }
.lt { font-size: 12px; fill: #333; }
.zt { font-size: 12px; fill: #6b7a99; }
.sbox { fill: #f6fbf7; stroke: #2e9e5b; stroke-width: 2; stroke-dasharray: 5 3; }
.sbox.over { fill: #e3f5e9; }

.drop { position: absolute; display: flex; align-items: center; justify-content: center;
        flex-wrap: wrap; gap: 6px; overflow: hidden; }
.drop.many { align-content: flex-start; justify-content: flex-start; padding: 26px 8px 8px; }
.slabel { color: #2e9e5b; font-weight: 600; font-size: 13px; pointer-events: none; }
.slabel.top { position: absolute; left: 8px; top: 4px; font-size: 12px; }

.code { border: 1px solid #d8dfea; border-radius: 6px; padding: 10px 16px; background: #fff;
        font-family: 'NSimSun', 'SimSun', Consolas, monospace; font-size: 15px; }
.crow { display: flex; align-items: center; min-height: 34px; }
.ctext { white-space: pre; }
.cslot { display: inline-flex; align-items: center; justify-content: flex-start;
         min-height: 28px; padding: 0 3px; border: 2px dashed #2e9e5b; background: #f6fbf7;
         border-radius: 4px; }
.cslot.over { background: #e3f5e9; }
.cslot .slabel { margin: 0 auto; }

.term { background: #0c0c0c; color: #cccccc; font-family: Consolas, 'NSimSun', monospace;
        font-size: 14px; padding: 10px 12px; border-radius: 4px; height: 260px;
        overflow-y: auto; overflow-x: hidden; cursor: text; }
.tl { white-space: pre-wrap; word-break: break-all; line-height: 1.45; display: flex; }
.tin { flex: 1; background: transparent; border: none; outline: none; color: #cccccc;
       font: inherit; padding: 0; }
.ipline { font-size: 14px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ipbox { font-family: Consolas, monospace; font-size: 15px; padding: 4px 8px; width: 180px;
         border: 1px solid #c4cdda; border-radius: 4px; }
.ok { color: #2e9e5b; font-size: 12px; }
.bad { color: #c8433a; font-size: 12px; }
</style>

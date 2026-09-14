<script setup>
/**
 * 按钮条 + 下拉面板。一个页面里放几个相关功能，默认都收着，点按钮才展开。
 *
 * 为什么做成组件而不是每页各写一遍：考试页要放「考试 / 打字学情 / 练习文本」，
 * 题库页要放「题库 / 导入」，以后还会加。抽出来之后加一个功能只是往
 * panels 数组里加一项，布局、响应式、记忆展开状态这些都不用重写。
 *
 * 布局上刻意避开的几个坑：
 * - 按钮条用 flex-wrap，窄屏自动换行，**不会挤成一团或者互相盖住**；
 * - 面板是文档流里的普通块，不用绝对定位，所以永远不会和下面的内容重叠；
 * - 组件只在第一次展开时才创建，收起后用 v-show 保留，
 *   这样打开过的面板不会每次重新请求数据，没打开的也不会白白拉一遍。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({
  /**
   * [{ key, label, icon, desc?, component, badge? }]
   * component 传 defineAsyncComponent 或直接的组件对象都行。
   */
  panels: { type: Array, required: true },
  /** 展开状态记在本机的键名；同一页固定一个 */
  storageKey: { type: String, required: true },
  /** 默认展开哪一个，留空则全收起 */
  defaultKey: { type: String, default: '' }
})

const route = useRoute()
const router = useRouter()

const open = ref(new Set())
/** 已经创建过的面板。收起不销毁，避免反复请求 */
const mounted = ref(new Set())

const STORE = `panels:${props.storageKey}`

function persist() {
  try {
    localStorage.setItem(STORE, JSON.stringify([...open.value]))
  } catch {
    /* 隐私模式下写不了就算了，不影响使用 */
  }
}

function expand(key) {
  open.value.add(key)
  mounted.value.add(key)
  // Set 原地改不会触发更新，换个新的
  open.value = new Set(open.value)
  mounted.value = new Set(mounted.value)
}

function toggle(key) {
  if (open.value.has(key)) {
    open.value.delete(key)
    open.value = new Set(open.value)
  } else {
    expand(key)
  }
  persist()
}

onMounted(() => {
  // 地址里带 ?panel=xxx 优先（老菜单地址会重定向过来，带着要打开哪个）
  const wanted = String(route.query.panel || '')
  if (wanted && props.panels.some(p => p.key === wanted)) {
    expand(wanted)
    // 打开之后把 query 去掉，免得刷新或前进后退时又被强行展开
    router.replace({ path: route.path, query: {} })
    return
  }

  let saved = null
  try {
    saved = JSON.parse(localStorage.getItem(STORE) || 'null')
  } catch {
    saved = null
  }
  const keys = Array.isArray(saved) ? saved : props.defaultKey ? [props.defaultKey] : []
  keys.filter(k => props.panels.some(p => p.key === k)).forEach(expand)
})

// 面板配置变了（比如按权限多出一项），把已经不存在的键清掉
watch(
  () => props.panels.map(p => p.key).join(','),
  () => {
    const valid = new Set(props.panels.map(p => p.key))
    open.value = new Set([...open.value].filter(k => valid.has(k)))
    mounted.value = new Set([...mounted.value].filter(k => valid.has(k)))
  }
)

const openCount = computed(() => open.value.size)

function collapseAll() {
  open.value = new Set()
  persist()
}
</script>

<template>
  <div class="pg">
    <div class="bar" role="tablist">
      <button
        v-for="p in panels"
        :key="p.key"
        type="button"
        class="pbtn"
        :class="{ on: open.has(p.key) }"
        :aria-expanded="open.has(p.key)"
        @click="toggle(p.key)"
      >
        <span class="ico" aria-hidden="true">{{ p.icon }}</span>
        <span class="txt">
          <span class="label">{{ p.label }}</span>
          <span v-if="p.desc" class="desc">{{ p.desc }}</span>
        </span>
        <span v-if="p.badge" class="badge">{{ p.badge }}</span>
        <span class="caret" aria-hidden="true">{{ open.has(p.key) ? '▴' : '▾' }}</span>
      </button>

      <button v-if="openCount > 1" type="button" class="pbtn plain" @click="collapseAll">
        全部收起
      </button>
    </div>

    <p v-if="!openCount" class="empty">点上面的按钮展开对应的功能。</p>

    <!-- 面板按 panels 的顺序排，和按钮条一一对应，展开顺序不会乱 -->
    <section
      v-for="p in panels"
      v-show="open.has(p.key)"
      :key="p.key"
      class="panel"
    >
      <div class="phead">
        <span class="ico" aria-hidden="true">{{ p.icon }}</span>
        <h3>{{ p.label }}</h3>
        <span class="grow" />
        <button type="button" class="close" @click="toggle(p.key)">收起</button>
      </div>
      <div class="pbody">
        <component :is="p.component" v-if="mounted.has(p.key)" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.pg {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ---------- 按钮条 ---------- */
.bar {
  display: flex;
  flex-wrap: wrap;          /* 窄屏自动换行，绝不挤成一团 */
  gap: 10px;
}
.pbtn {
  display: flex;
  align-items: center;
  gap: 10px;
  /* 基准宽度 + 可伸缩：一行放得下就并排，放不下就换行后各自铺开 */
  flex: 1 1 210px;
  max-width: 320px;
  min-width: 0;             /* 没有这条，长文字会把按钮撑出容器 */
  padding: 12px 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  font-family: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}
.pbtn:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 10px rgba(64, 100, 220, 0.1);
}
.pbtn.on {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.pbtn.plain {
  flex: 0 0 auto;
  justify-content: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 12px 16px;
}
.pbtn .ico {
  font-size: 19px;
  line-height: 1;
  flex: none;
}
.pbtn .txt {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;             /* 允许内部文字省略，不撑破按钮 */
  flex: 1;
}
.pbtn .label {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pbtn .desc {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pbtn.on .desc {
  color: var(--el-color-primary);
  opacity: 0.75;
}
.pbtn .badge {
  flex: none;
  min-width: 20px;
  padding: 1px 7px;
  border-radius: 10px;
  background: var(--el-color-danger);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}
.pbtn .caret {
  flex: none;
  font-size: 11px;
  opacity: 0.5;
}

.empty {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* ---------- 面板 ---------- */
.panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color);
  overflow: hidden;         /* 面板内的宽表格不会溢出圆角 */
}
.phead {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 16px;
  background: var(--el-fill-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.phead h3 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
}
.phead .ico {
  font-size: 16px;
  line-height: 1;
}
.phead .grow {
  flex: 1;
}
.close {
  border: none;
  background: none;
  color: var(--el-text-color-secondary);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  padding: 3px 8px;
  border-radius: 6px;
}
.close:hover {
  background: var(--el-fill-color);
  color: var(--el-color-primary);
}
.pbody {
  padding: 16px;
  /* 里面塞的是整页级别的组件，宽表格自己横向滚动，不撑破布局 */
  overflow-x: auto;
}

/* 手机上按钮各占一行，描述文字留出空间 */
@media (max-width: 560px) {
  .pbtn {
    flex: 1 1 100%;
    max-width: none;
  }
  .pbody {
    padding: 12px 10px;
  }
}
</style>

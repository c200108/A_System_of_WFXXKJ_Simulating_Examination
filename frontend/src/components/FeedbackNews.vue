<script setup>
/**
 * 教师端每个页面顶上的黄条：管理员在「需求反馈」里**置顶**的反馈（2.23.2，最多 5 条）。
 *
 * 2.23.0 是自动显示最近 24 小时的最新消息，只在组卷页；现在改成只显示置顶的，放在教师端布局里，
 * 每个页面都看得到。置顶可以不限期，也可以 1～30 天，到期服务端就不再给了。
 * 点 × 关掉的只是这一条（记在本浏览器）；同一条取消后再置顶会重新提醒。
 * 切页面时顺手刷新一下（最多一分钟一次），管理员刚置顶的不用等刷新整页。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const route = useRoute()
const items = ref([])
const closed = ref(new Set())
const KEY = 'feedback-pins-closed'
let lastLoad = 0

function readClosed() {
  try {
    const got = JSON.parse(localStorage.getItem(KEY) || '[]')
    return new Set(Array.isArray(got) ? got : [])
  } catch {
    return new Set()
  }
}

async function load() {
  lastLoad = Date.now()
  try {
    const res = await api.feedbackNews()
    items.value = Array.isArray(res?.items) ? res.items : []
  } catch {
    // 老服务器没有这个接口、没网：不提醒就是了
  }
}

const shown = computed(() => items.value.filter(n => !closed.value.has(n.id)))

// 管理员在反馈页置顶 / 取消置顶后发这个事件，黄条马上跟着变
onMounted(() => {
  closed.value = readClosed()
  load()
  window.addEventListener('feedback-pins-changed', load)
})
onUnmounted(() => window.removeEventListener('feedback-pins-changed', load))

watch(
  () => route.path,
  () => {
    if (Date.now() - lastLoad > 60000) load()
  }
)

function close(n) {
  const next = new Set(closed.value)
  next.add(n.id)
  closed.value = next
  try {
    // 只留还在置顶的那几条的记录，不然越存越多
    const live = new Set(items.value.map(x => x.id))
    localStorage.setItem(KEY, JSON.stringify([...next].filter(id => live.has(id))))
  } catch {
    // 隐私模式存不了：这次关掉，下次进来还会提醒
  }
}

function go() {
  if (route.path !== '/js/feedback') router.push('/js/feedback')
}

function until(t) {
  if (!t) return ''
  return `置顶到 ${String(t).replace('T', ' ').slice(5, 16)}`
}
</script>

<template>
  <div v-if="shown.length" class="fbpins">
    <div v-for="n in shown" :key="n.id" class="fbnews" role="status">
      <span class="tag">置顶</span>
      <span class="body" @click="go">
        <b>{{ n.author }}</b>
        <span class="cat">【{{ n.category }}】</span>{{ n.text }}
        <span v-if="n.last_reply" class="reply">
          · {{ n.last_reply.author }}{{ n.last_reply.is_admin ? '（管理员）' : '' }}回复：{{ n.last_reply.text }}
        </span>
        <span v-if="n.pinned_until" class="time">{{ until(n.pinned_until) }}</span>
      </span>
      <a class="go" @click="go">去看看</a>
      <button class="x" type="button" aria-label="关掉这条提醒" @click="close(n)">×</button>
    </div>
  </div>
</template>

<style scoped>
.fbpins {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 0 12px;
}
.fbnews {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-5);
  color: var(--el-text-color-primary);
  font-size: 13.5px;
}
.tag {
  flex: none;
  padding: 1px 8px;
  border-radius: 4px;
  background: var(--el-color-warning);
  color: #fff;
  font-size: 12px;
}
.body {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.cat {
  color: var(--el-text-color-secondary);
}
.reply {
  color: var(--el-text-color-regular);
}
.time {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.go {
  flex: none;
  color: var(--el-color-primary);
  cursor: pointer;
}
.x {
  flex: none;
  border: 0;
  background: none;
  font-size: 18px;
  line-height: 1;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
@media print {
  .fbpins {
    display: none;
  }
}
</style>

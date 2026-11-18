<script setup>
/**
 * 组卷页（教师端首页）顶上的黄条：需求反馈区最近 24 小时里的最新一条消息（2.23.0）。
 *
 * 最新消息 = 一条反馈审核通过公开出来，或者公开的反馈下面来了新回复（后端 /feedback/news）。
 * 从消息出来起挂一天，过了自动不显示；点 × 关掉的只是这一条，下一条新消息照样提醒（记在本浏览器）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const news = ref(null)
const KEY = 'feedback-news-closed'

function closedId() {
  try {
    return localStorage.getItem(KEY) || ''
  } catch {
    return ''
  }
}

onMounted(async () => {
  try {
    const { news: n } = await api.feedbackNews()
    if (!n || n.id === closedId()) return
    if (n.until && new Date(String(n.until).replace(' ', 'T')) < new Date()) return
    news.value = n
  } catch {
    // 老服务器没有这个接口、没网：不提醒就是了
  }
})

function close() {
  try {
    localStorage.setItem(KEY, news.value.id)
  } catch {
    // 隐私模式存不了：这次关掉，下次进来还会提醒
  }
  news.value = null
}

function when(t) {
  const s = String(t || '').replace('T', ' ')
  return s.slice(5, 16)
}
</script>

<template>
  <div v-if="news" class="fbnews" role="status">
    <span class="tag">需求反馈新消息</span>
    <span class="body" @click="router.push('/js/feedback')">
      <template v-if="news.kind === 'reply'">
        <b>{{ news.author }}</b>{{ news.is_admin ? '（管理员）' : '' }} 回复了「{{ news.about }}」：{{ news.text }}
      </template>
      <template v-else>
        <b>{{ news.author }}</b> 提了一条{{ news.category }}：{{ news.text }}
      </template>
      <span class="time">{{ when(news.at) }}</span>
    </span>
    <a class="go" @click="router.push('/js/feedback')">去看看</a>
    <button class="x" type="button" aria-label="关掉这条提醒" @click="close">×</button>
  </div>
</template>

<style scoped>
.fbnews {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 12px;
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
  .fbnews {
    display: none;
  }
}
</style>

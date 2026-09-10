<script setup>
/**
 * 需求反馈（公开提交、公开展示）。
 *
 * 权限分三档：
 *   未登录  —— 提交、浏览、看回复
 *   老师    —— 再多出「回复」和「点赞」
 *   管理员  —— 再多出「下架」「删除」，以及看联系方式
 * 界面上藏起来只是顺手，真正拦人的是后端：下架和删除挂的是 require_admin。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { currentUser } from '../auth'

const CATEGORIES = ['建议', '问题', '表扬', '其他']
const CAT_TYPE = { 建议: 'primary', 问题: 'warning', 表扬: 'success', 其他: 'info' }

// 常用表情，按用得上的场景挑的，不求全
const EMOJI = [
  '😀', '😄', '🙂', '😊', '🥳', '🤔', '😅', '😣', '😭', '😡',
  '👍', '👎', '👏', '🙏', '💪', '🎉', '✨', '🔥', '❤️', '💡',
  '✅', '❌', '⚠️', '❓', '❗', '📝', '📚', '⌨️', '🖥️', '🌙'
]

const list = ref([])
const loading = ref(false)
const submitting = ref(false)
const filter = ref('')

const form = reactive({ author: '', contact: '', category: '建议', content: '' })
const contentRef = ref(null)

// 正在回复哪一条：{ [反馈id]: 输入中的文字 }
const replyDraft = reactive({})
const replyOpen = ref(null)
const replyRef = ref(null)

const me = currentUser
const isTeacher = computed(() => !!me.value)
const isAdmin = computed(() => me.value?.role === 'admin')

// 管理员视角要看到已下架的和联系方式，走另一个接口
const manageRows = ref([])

async function load() {
  loading.value = true
  try {
    list.value = await api.feedbackList(filter.value ? { category: filter.value } : {})
    if (isAdmin.value) manageRows.value = await api.feedbackAll()
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  try {
    const saved = JSON.parse(localStorage.getItem('feedbackWho') || 'null')
    if (saved) {
      form.author = saved.a || ''
      form.contact = saved.c || ''
    }
  } catch {
    /* 存过脏值就当没有 */
  }
  // 老师登录后称呼默认填自己的名字，省得每次都打
  if (me.value && !form.author) form.author = me.value.name || me.value.username
  load()
})

/** 把表情插到光标处，而不是无脑追加到末尾 */
function insertEmoji(target, emoji) {
  const el = target?.textarea || target?.$el?.querySelector('textarea')
  if (!el) return null
  const start = el.selectionStart ?? el.value.length
  const end = el.selectionEnd ?? start
  const next = el.value.slice(0, start) + emoji + el.value.slice(end)
  // 插完把光标放到表情后面，接着打字不用重新点
  requestAnimationFrame(() => {
    el.focus()
    el.setSelectionRange(start + emoji.length, start + emoji.length)
  })
  return next
}

function addEmojiToForm(e) {
  const next = insertEmoji(contentRef.value, e)
  form.content = next === null ? form.content + e : next
}

function addEmojiToReply(fid, e) {
  // 回复框在 v-for 里，Vue 会把 ref 收成数组；同时只开一个，取第一个就行
  const t = Array.isArray(replyRef.value) ? replyRef.value[0] : replyRef.value
  const next = insertEmoji(t, e)
  replyDraft[fid] = next === null ? (replyDraft[fid] || '') + e : next
}

async function submit() {
  if (!form.author.trim()) return ElMessage.warning('请填写您的称呼')
  if (form.content.trim().length < 5) return ElMessage.warning('说得再具体一点吧，至少 5 个字')

  submitting.value = true
  try {
    await api.feedbackCreate({ ...form })
    localStorage.setItem(
      'feedbackWho',
      JSON.stringify({ a: form.author.trim(), c: form.contact.trim() })
    )
    form.content = ''
    await load()
    ElMessage.success('已提交，感谢反馈')
  } finally {
    submitting.value = false
  }
}

// ---------- 老师：回复与点赞 ----------
function toggleReply(fid) {
  replyOpen.value = replyOpen.value === fid ? null : fid
  if (replyOpen.value && replyDraft[fid] === undefined) replyDraft[fid] = ''
}

async function sendReply(fid) {
  const text = (replyDraft[fid] || '').trim()
  if (!text) return ElMessage.warning('回复内容不能为空')
  await api.feedbackReply(fid, text)
  replyDraft[fid] = ''
  replyOpen.value = null
  await load()
  ElMessage.success('已回复')
}

async function removeReply(rid) {
  await ElMessageBox.confirm('撤回这条回复？', '提示', { type: 'warning' })
  await api.feedbackReplyDelete(rid)
  await load()
}

/** 能撤回的只有自己写的；管理员谁的都能撤 */
function canWithdraw(reply) {
  return isAdmin.value || reply.author === (me.value?.name || me.value?.username)
}

async function like(row) {
  const res = await api.feedbackLike(row.id)
  // 就地更新，不整页刷新，点起来跟手
  row.like_count = res.like_count
  row.liked_by_me = res.liked_by_me
}

// ---------- 管理员：下架与删除 ----------
// 分成两个动作而不是一个 toggle：公开列表里的 FeedbackOut **不含 is_public**
// （那是管理端字段），对它取反只会得到 true，等于点了「下架」却重新上架。
async function hide(row) {
  await ElMessageBox.confirm('下架后这条在公开列表里就看不到了，但记录仍然保留。', '确认下架', {
    type: 'warning'
  })
  await api.feedbackVisibility(row.id, false)
  await load()
  ElMessage.success('已下架')
}

async function restore(row) {
  await api.feedbackVisibility(row.id, true)
  await load()
  ElMessage.success('已重新展示')
}

async function remove(row) {
  await ElMessageBox.confirm('彻底删除这条反馈？连同下面的回复一起删掉，不可恢复。', '提示', {
    type: 'warning'
  })
  await api.feedbackDelete(row.id)
  await load()
  ElMessage.success('已删除')
}

const fmt = t => String(t).replace('T', ' ').slice(0, 16)
const hidden = computed(() => manageRows.value.filter(r => !r.is_public))
</script>

<template>
  <div class="page">
    <header class="hd">
      <h1>需求反馈</h1>
      <p class="sub">用着不顺手、想要什么新功能，都可以说。<b>不需要登录</b>，写完直接提交。</p>
    </header>

    <!-- 提交表单 -->
    <el-card shadow="never" class="form-card">
      <div class="row">
        <el-input v-model="form.author" placeholder="您的称呼 *" style="width: 160px" />
        <el-input v-model="form.contact" placeholder="联系方式（选填，不公开）" style="width: 220px" />
        <el-select v-model="form.category" style="width: 110px">
          <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
        </el-select>
      </div>
      <el-input
        ref="contentRef"
        v-model="form.content"
        type="textarea"
        :rows="3"
        maxlength="2000"
        show-word-limit
        placeholder="具体说说：想在哪个页面、做什么事、现在卡在哪里"
        class="ta"
      />
      <div class="acts">
        <el-popover placement="bottom-start" :width="330" trigger="click">
          <template #reference>
            <el-button size="small" class="emoji-btn">😀 表情</el-button>
          </template>
          <div class="emoji-grid">
            <button v-for="e in EMOJI" :key="e" class="emoji" @click="addEmojiToForm(e)">{{ e }}</button>
          </div>
        </el-popover>
        <span class="tip">提交的内容会公开展示，联系方式不会。</span>
        <span class="grow" />
        <el-button type="primary" :loading="submitting" @click="submit">提交反馈</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <div class="listhead">
      <h2>大家的反馈<span class="count">{{ list.length }}</span></h2>
      <el-select v-model="filter" placeholder="全部类型" clearable style="width: 130px" @change="load">
        <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
      </el-select>
    </div>

    <el-empty v-if="!list.length && !loading" description="还没有人提过，来做第一个吧" :image-size="80" />

    <div v-loading="loading" class="items">
      <article v-for="f in list" :key="f.id" class="item">
        <div class="meta">
          <span class="who">{{ f.author }}</span>
          <el-tag :type="CAT_TYPE[f.category] || 'info'" size="small" effect="light">
            {{ f.category }}
          </el-tag>
          <time>{{ fmt(f.created_at) }}</time>
          <span class="grow" />
          <!-- 管理员才有下架和删除 -->
          <template v-if="isAdmin">
            <el-button link type="warning" @click="hide(f)">下架</el-button>
            <el-button link type="danger" @click="remove(f)">删除</el-button>
          </template>
        </div>

        <p class="content">{{ f.content }}</p>

        <!-- 回复列表 -->
        <div v-if="f.replies?.length" class="replies">
          <div v-for="r in f.replies" :key="r.id" class="reply">
            <span class="rtag" :class="{ admin: r.is_admin }">
              {{ r.author }}{{ r.is_admin ? '（管理员）' : '' }}
            </span>
            <span class="rtext">{{ r.content }}</span>
            <time class="rtime">{{ fmt(r.created_at) }}</time>
            <el-button
              v-if="isTeacher && canWithdraw(r)"
              link
              type="info"
              class="rdel"
              @click="removeReply(r.id)"
            >撤回</el-button>
          </div>
        </div>

        <!-- 老师的操作条：点赞 + 回复 -->
        <div class="bar">
          <button
            class="likebtn"
            :class="{ on: f.liked_by_me, off: !isTeacher }"
            :title="isTeacher ? (f.liked_by_me ? '取消点赞' : '点赞') : '登录后可以点赞'"
            :disabled="!isTeacher"
            @click="like(f)"
          >
            <span class="thumb">👍</span>
            <span v-if="f.like_count">{{ f.like_count }}</span>
            <span v-else>赞同</span>
          </button>
          <el-button v-if="isTeacher" link type="primary" size="small" @click="toggleReply(f.id)">
            {{ replyOpen === f.id ? '收起' : '回复' }}
          </el-button>
          <span v-if="!isTeacher && f.like_count" class="anonlike">{{ f.like_count }} 位老师赞同</span>
        </div>

        <!-- 回复输入框 -->
        <div v-if="replyOpen === f.id" class="replybox">
          <el-input
            ref="replyRef"
            v-model="replyDraft[f.id]"
            type="textarea"
            :rows="2"
            maxlength="2000"
            placeholder="写给提交者看的，会公开显示，署你的名字"
          />
          <div class="replyacts">
            <el-popover placement="top-start" :width="330" trigger="click">
              <template #reference>
                <el-button size="small">😀 表情</el-button>
              </template>
              <div class="emoji-grid">
                <button
                  v-for="e in EMOJI"
                  :key="e"
                  class="emoji"
                  @click="addEmojiToReply(f.id, e)"
                >{{ e }}</button>
              </div>
            </el-popover>
            <span class="grow" />
            <el-button size="small" @click="replyOpen = null">取消</el-button>
            <el-button size="small" type="primary" @click="sendReply(f.id)">发布回复</el-button>
          </div>
        </div>
      </article>
    </div>

    <!-- 管理员：已下架的 -->
    <template v-if="isAdmin">
      <div class="listhead hidden-head">
        <h2>已下架<span class="count">{{ hidden.length }}</span></h2>
        <span class="onlyadmin">只有管理员看得到这一栏</span>
      </div>
      <el-empty v-if="!hidden.length" description="没有下架过任何反馈" :image-size="60" />
      <div class="items">
        <article v-for="f in hidden" :key="'h' + f.id" class="item off">
          <div class="meta">
            <span class="who">{{ f.author }}</span>
            <el-tag size="small" type="info">{{ f.category }}</el-tag>
            <span v-if="f.contact" class="contact">联系方式 {{ f.contact }}</span>
            <time>{{ fmt(f.created_at) }}</time>
            <span class="grow" />
            <el-button link type="success" @click="restore(f)">重新展示</el-button>
            <el-button link type="danger" @click="remove(f)">删除</el-button>
          </div>
          <p class="content">{{ f.content }}</p>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 820px;
  margin: 0 auto;
  padding: 8px 4px 60px;
}
.hd {
  margin-bottom: 20px;
}
h1 {
  font-size: 26px;
  font-weight: 650;
  margin: 0 0 6px;
}
.sub {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.form-card {
  margin-bottom: 28px;
}
.row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.ta :deep(textarea) {
  line-height: 1.7;
}
.acts {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.grow {
  flex: 1;
}

/* 表情面板 */
.emoji-grid {
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 2px;
}
.emoji {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 19px;
  line-height: 1;
  padding: 5px 0;
  border-radius: 6px;
}
.emoji:hover {
  background: var(--el-fill-color);
}

.listhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.hidden-head {
  margin-top: 34px;
}
.listhead h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 8px;
  font-family: ui-monospace, Consolas, monospace;
}
.onlyadmin {
  font-size: 12px;
  color: var(--el-color-warning);
}

.items {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.item {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px 16px;
}
.item.off {
  opacity: 0.6;
  border-style: dashed;
}
.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.who {
  font-weight: 600;
  font-size: 13.5px;
}
.meta time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, Consolas, monospace;
}
.contact {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.content {
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 回复 */
.replies {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.reply {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 12px;
  border-left: 3px solid var(--el-border-color);
  background: var(--el-fill-color-lighter);
  border-radius: 0 8px 8px 0;
  font-size: 13.5px;
  line-height: 1.75;
}
.rtag {
  font-weight: 600;
  color: var(--el-text-color-regular);
  flex: none;
}
.rtag.admin {
  color: var(--el-color-primary);
}
.rtext {
  white-space: pre-wrap;
  word-break: break-word;
}
.rtime {
  font-size: 11.5px;
  color: var(--el-text-color-placeholder);
  font-family: ui-monospace, Consolas, monospace;
}
.rdel {
  font-size: 12px;
  padding: 0;
}

/* 点赞 / 回复条 */
.bar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 11px;
}
.likebtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  color: var(--el-text-color-secondary);
  border-radius: 15px;
  padding: 4px 13px;
  font-size: 12.5px;
  cursor: pointer;
  transition: 0.15s;
}
.likebtn:hover:not(:disabled) {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.likebtn.on {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.likebtn:disabled {
  cursor: default;
  opacity: 0.55;
}
.thumb {
  font-size: 13px;
}
.anonlike {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.replybox {
  margin-top: 10px;
}
.replyacts {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
</style>

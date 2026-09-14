<script setup>
/**
 * 需求反馈（公开提交、公开展示）。
 *
 * **先审后发**：提交完是「待审核」，管理员审过才出现在公开区。
 *
 * 权限分三档：
 *   未登录  —— 提交、浏览、看回复
 *   老师    —— 再多出「回复」和「点赞」
 *   管理员  —— 再多出「审核」「删除」，以及看联系方式
 * 界面上藏起来只是顺手，真正拦人的是后端：审核和删除挂的是 require_admin。
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

// ---------- 配图 ----------
const MAX_IMAGES = 3
const images = ref([])        // 已选好的图片地址，本地上传和外链混在一起
const uploading = ref(false)
const urlInput = ref('')
const urlBox = ref(false)

async function uploadImage(opt) {
  if (images.value.length >= MAX_IMAGES) {
    return ElMessage.warning(`最多配 ${MAX_IMAGES} 张图`)
  }
  uploading.value = true
  try {
    const res = await api.feedbackUploadImage(opt.file)
    images.value.push(res.image_url)
    ElMessage.success('图片已上传')
  } catch (e) {
    // 走的是原生 upload，拦截器弹过一次了，这里不重复弹
    opt.onError?.(e)
  } finally {
    uploading.value = false
  }
}

function addUrl() {
  const url = urlInput.value.trim()
  if (!url) return
  if (!/^https?:\/\//i.test(url)) {
    return ElMessage.warning('网络图片要用 http:// 或 https:// 开头的完整地址')
  }
  if (images.value.length >= MAX_IMAGES) {
    return ElMessage.warning(`最多配 ${MAX_IMAGES} 张图`)
  }
  images.value.push(url)
  urlInput.value = ''
  urlBox.value = false
}

function dropImage(i) {
  images.value.splice(i, 1)
}

// 点开大图。**开关必须是独立的布尔量**：el-dialog 的 modelValue 声明成
// Boolean，Vue 对 Boolean 类型的 prop 会把空字符串强制转成 true，
// 直接 v-model 绑图片地址的话，地址为空时对话框反而是打开的。
const preview = ref('')
const previewOpen = ref(false)

function openPreview(src) {
  preview.value = src
  previewOpen.value = true
}

// 正在回复哪一条：{ [反馈id]: 输入中的文字 }
const replyDraft = reactive({})
const replyOpen = ref(null)
const replyRef = ref(null)

const me = currentUser
const isTeacher = computed(() => !!me.value)
const isAdmin = computed(() => me.value?.role === 'admin')

// 管理员视角要看到待审核的和联系方式，走另一个接口
const manageRows = ref([])
const pending = ref(0)
const picked = ref([])       // 批量审核勾中的

async function load() {
  loading.value = true
  try {
    list.value = await api.feedbackList(filter.value ? { category: filter.value } : {})
    if (isAdmin.value) manageRows.value = await api.feedbackAll()
    if (isTeacher.value) {
      pending.value = (await api.feedbackPendingCount()).pending
    }
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
    await api.feedbackCreate({ ...form, images: images.value })
    localStorage.setItem(
      'feedbackWho',
      JSON.stringify({ a: form.author.trim(), c: form.contact.trim() })
    )
    form.content = ''
    images.value = []
    await load()
    ElMessageBox.alert(
      '已提交，感谢反馈。\n\n内容要管理员审核通过后才会出现在下面的评论区，请稍等。',
      '提交成功',
      { confirmButtonText: '知道了' }
    )
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

// ---------- 管理员：审核与删除 ----------
async function review(row, status) {
  let note = ''
  if (status === 'rejected') {
    const res = await ElMessageBox.prompt(
      '拒绝后这条不会出现在公开区，内容仍然保留在管理端。\n可以写个原因，只有管理员看得到：',
      '拒绝这条反馈',
      { inputPlaceholder: '比如：内容不实 / 与平台无关', confirmButtonText: '确认拒绝' }
    )
    note = (res.value || '').trim()
  }
  await api.feedbackReview(row.id, status, note)
  picked.value = picked.value.filter(id => id !== row.id)
  await load()
  ElMessage.success({ approved: '已通过，评论区可见了', rejected: '已拒绝', pending: '已退回待审' }[status])
}

async function reviewPicked(status) {
  if (!picked.value.length) return ElMessage.warning('先勾选要审的条目')
  const res = await api.feedbackReviewBulk(picked.value, status)
  picked.value = []
  await load()
  ElMessage.success(`已${status === 'approved' ? '通过' : '拒绝'} ${res.affected} 条`)
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

const pendingRows = computed(() => manageRows.value.filter(r => r.status === 'pending'))
const rejectedRows = computed(() => manageRows.value.filter(r => r.status === 'rejected'))
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
      <!-- 已选的配图 -->
      <div v-if="images.length" class="shots">
        <div v-for="(src, i) in images" :key="src + i" class="shot">
          <img :src="src" alt="配图" @click="openPreview(src)" />
          <button class="drop" title="移除" @click="dropImage(i)">×</button>
        </div>
      </div>

      <div class="acts">
        <el-popover placement="bottom-start" :width="330" trigger="click">
          <template #reference>
            <el-button size="small" class="emoji-btn">😀 表情</el-button>
          </template>
          <div class="emoji-grid">
            <button v-for="e in EMOJI" :key="e" class="emoji" @click="addEmojiToForm(e)">{{ e }}</button>
          </div>
        </el-popover>

        <el-upload
          :http-request="uploadImage"
          :show-file-list="false"
          accept=".png,.jpg,.jpeg,.gif,.webp"
          :disabled="uploading || images.length >= MAX_IMAGES"
        >
          <el-button size="small" :loading="uploading" :disabled="images.length >= MAX_IMAGES">
            🖼 本地图片
          </el-button>
        </el-upload>

        <el-popover v-model:visible="urlBox" placement="bottom-start" :width="330" trigger="click">
          <template #reference>
            <el-button size="small" :disabled="images.length >= MAX_IMAGES">🔗 网络图片</el-button>
          </template>
          <div class="urlbox">
            <el-input
              v-model="urlInput"
              size="small"
              placeholder="粘贴图片网址，https:// 开头"
              @keyup.enter="addUrl"
            />
            <el-button size="small" type="primary" @click="addUrl">添加</el-button>
          </div>
        </el-popover>

        <span class="tip">
          最多 {{ MAX_IMAGES }} 张图。提交后<b>需管理员审核</b>才会公开展示，联系方式不公开。
        </span>
        <span class="grow" />
        <el-button type="primary" :loading="submitting" @click="submit">提交反馈</el-button>
      </div>
    </el-card>

    <!-- 点缩略图看大图 -->
    <el-dialog v-model="previewOpen" title="查看配图" width="min(90vw, 900px)" align-center>
      <img v-if="preview" :src="preview" class="bigpic" alt="配图" />
    </el-dialog>

    <!-- 列表 -->
    <div class="listhead">
      <h2>
        大家的反馈<span class="count">{{ list.length }}</span>
        <el-tag v-if="isTeacher && pending" size="small" type="warning" effect="light" class="pendtag">
          {{ pending }} 条待审核
        </el-tag>
      </h2>
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
          <!-- 管理员才有撤下和删除 -->
          <template v-if="isAdmin">
            <el-button link type="warning" @click="review(f, 'rejected')">撤下</el-button>
            <el-button link type="danger" @click="remove(f)">删除</el-button>
          </template>
        </div>

        <p class="content">{{ f.content }}</p>

        <div v-if="f.images?.length" class="pics">
          <img
            v-for="(src, i) in f.images"
            :key="src + i"
            :src="src"
            class="pic"
            alt="配图"
            loading="lazy"
            @click="openPreview(src)"
          />
        </div>

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

    <!-- 管理员：审核队列 -->
    <template v-if="isAdmin">
      <div class="listhead hidden-head">
        <h2>待审核<span class="count">{{ pendingRows.length }}</span></h2>
        <div class="bulkact">
          <template v-if="picked.length">
            <span class="picked">已选 {{ picked.length }} 条</span>
            <el-button size="small" type="success" @click="reviewPicked('approved')">批量通过</el-button>
            <el-button size="small" type="warning" @click="reviewPicked('rejected')">批量拒绝</el-button>
            <el-button size="small" link @click="picked = []">取消</el-button>
          </template>
          <span v-else class="onlyadmin">只有管理员看得到这一栏</span>
        </div>
      </div>

      <el-empty v-if="!pendingRows.length" description="没有待审核的反馈" :image-size="60" />
      <el-checkbox-group v-else v-model="picked" class="items">
        <article v-for="f in pendingRows" :key="'p' + f.id" class="item pend">
          <div class="meta">
            <el-checkbox :value="f.id" class="pick" />
            <span class="who">{{ f.author }}</span>
            <el-tag :type="CAT_TYPE[f.category] || 'info'" size="small" effect="light">
              {{ f.category }}
            </el-tag>
            <span v-if="f.contact" class="contact">联系方式 {{ f.contact }}</span>
            <time>{{ fmt(f.created_at) }}</time>
            <span class="grow" />
            <el-button link type="success" @click="review(f, 'approved')">通过</el-button>
            <el-button link type="warning" @click="review(f, 'rejected')">拒绝</el-button>
            <el-button link type="danger" @click="remove(f)">删除</el-button>
          </div>
          <p class="content">{{ f.content }}</p>
          <div v-if="f.images?.length" class="pics">
            <img
              v-for="(src, i) in f.images"
              :key="src + i"
              :src="src"
              class="pic"
              alt="配图"
              loading="lazy"
              @click="openPreview(src)"
            />
          </div>
        </article>
      </el-checkbox-group>

      <div class="listhead hidden-head">
        <h2>已拒绝<span class="count">{{ rejectedRows.length }}</span></h2>
      </div>
      <el-empty v-if="!rejectedRows.length" description="没有拒绝过任何反馈" :image-size="60" />
      <div class="items">
        <article v-for="f in rejectedRows" :key="'r' + f.id" class="item off">
          <div class="meta">
            <span class="who">{{ f.author }}</span>
            <el-tag size="small" type="info">{{ f.category }}</el-tag>
            <span v-if="f.review_note" class="note">原因：{{ f.review_note }}</span>
            <time>{{ fmt(f.created_at) }}</time>
            <span class="grow" />
            <el-button link type="success" @click="review(f, 'approved')">改为通过</el-button>
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

/* ---------- 配图 ---------- */
.shots {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}
/* 名字别太泛：点赞按钮里那个 👍 本来就叫 .thumb，撞了会被撑成方块 */
.shot {
  position: relative;
  width: 84px;
  height: 84px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
}
.shot img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  cursor: zoom-in;
  display: block;
}
.shot .drop {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}
.pics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 0;
}
.pic {
  width: 120px;
  height: 90px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  cursor: zoom-in;
  background: var(--el-fill-color-lighter);
}
.bigpic {
  display: block;
  max-width: 100%;
  max-height: 78vh;
  margin: 0 auto;
}
.urlbox {
  display: flex;
  gap: 8px;
}

/* ---------- 审核 ---------- */
.bulkact {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.picked {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
.pendtag {
  margin-left: 10px;
}
.item.pend {
  border-left: 3px solid var(--el-color-warning);
}
.pick {
  margin-right: 2px;
}
.note {
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

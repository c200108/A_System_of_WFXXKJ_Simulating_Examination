<script setup>
/**
 * 需求反馈（公开提交、公开展示）。
 *
 * 登录的老师会多出一栏管理操作：答复、下架、删除。
 * 联系方式只在管理端可见 —— 公开接口的响应模型里根本没有这个字段。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { currentUser } from '../auth'

const CATEGORIES = ['建议', '问题', '表扬', '其他']
const CAT_TYPE = { 建议: 'primary', 问题: 'warning', 表扬: 'success', 其他: 'info' }

const list = ref([])
const loading = ref(false)
const submitting = ref(false)
const filter = ref('')

const form = reactive({ author: '', contact: '', category: '建议', content: '' })

const isTeacher = computed(() => !!currentUser.value)
// 老师视角要看到已下架的和联系方式，走另一个接口
const manageRows = ref([])

async function load() {
  loading.value = true
  try {
    list.value = await api.feedbackList(filter.value ? { category: filter.value } : {})
    if (isTeacher.value) manageRows.value = await api.feedbackAll()
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
  load()
})

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

// ---------- 教师操作 ----------
async function reply(row) {
  const { value } = await ElMessageBox.prompt('答复内容（清空即撤销答复）', '答复反馈', {
    inputType: 'textarea',
    inputValue: row.reply || '',
    inputPlaceholder: '写给提交者看的，会公开显示'
  })
  await api.feedbackReply(row.id, (value || '').trim())
  await load()
  ElMessage.success('已保存')
}

async function toggle(row) {
  const to = !row.is_public
  if (!to) {
    await ElMessageBox.confirm('下架后这条在公开列表里就看不到了，但记录仍然保留。', '确认下架', {
      type: 'warning'
    })
  }
  await api.feedbackVisibility(row.id, to)
  await load()
  ElMessage.success(to ? '已重新展示' : '已下架')
}

async function remove(row) {
  await ElMessageBox.confirm('彻底删除这条反馈？不可恢复。', '提示', { type: 'warning' })
  await api.feedbackDelete(row.id)
  await load()
  ElMessage.success('已删除')
}

const fmt = t => String(t).replace('T', ' ').slice(0, 16)
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
        v-model="form.content"
        type="textarea"
        :rows="3"
        maxlength="2000"
        show-word-limit
        placeholder="具体说说：想在哪个页面、做什么事、现在卡在哪里"
        class="ta"
      />
      <div class="acts">
        <span class="tip">提交的内容会公开展示，联系方式不会。</span>
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

          <template v-if="isTeacher">
            <span class="grow" />
            <el-button link type="primary" @click="reply(f)">答复</el-button>
            <el-button link type="warning" @click="toggle(f)">下架</el-button>
            <el-button link type="danger" @click="remove(f)">删除</el-button>
          </template>
        </div>
        <p class="content">{{ f.content }}</p>
        <div v-if="f.reply" class="reply">
          <span class="rtag">管理员答复</span>
          <span>{{ f.reply }}</span>
        </div>
      </article>
    </div>

    <!-- 教师：已下架的 -->
    <template v-if="isTeacher">
      <div class="listhead hidden-head">
        <h2>已下架<span class="count">{{ manageRows.filter(r => !r.is_public).length }}</span></h2>
      </div>
      <div class="items">
        <article
          v-for="f in manageRows.filter(r => !r.is_public)"
          :key="'h' + f.id"
          class="item off"
        >
          <div class="meta">
            <span class="who">{{ f.author }}</span>
            <el-tag size="small" type="info">{{ f.category }}</el-tag>
            <span v-if="f.contact" class="contact">联系方式 {{ f.contact }}</span>
            <time>{{ fmt(f.created_at) }}</time>
            <span class="grow" />
            <el-button link type="success" @click="toggle(f)">重新展示</el-button>
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
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
.tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
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
.grow {
  flex: 1;
}
.content {
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}
.reply {
  margin-top: 10px;
  padding: 9px 12px;
  border-left: 3px solid var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 0 8px 8px 0;
  font-size: 13.5px;
  line-height: 1.75;
}
.rtag {
  color: var(--el-color-primary);
  font-weight: 600;
  margin-right: 8px;
}
</style>

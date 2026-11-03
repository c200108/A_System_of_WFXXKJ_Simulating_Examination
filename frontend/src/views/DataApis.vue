<script setup>
/**
 * API 板块首页：我建的 API 一张卡一个（2.16.0）。
 *
 * 老师建一个 API，拿到接收地址和写入密钥，自己做的答题网页、自评互评表往里送数据。
 * 各老师的 API 互不相通；管理员看全部，可按老师筛选。真正拦人的在后端（routers/data_apis.py）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { currentUser } from '../auth'

const router = useRouter()
const rows = ref([])
const templates = ref({})
const teachers = ref([])
const owner = ref(null)
const loading = ref(false)
const keyword = ref('')
const isAdmin = computed(() => currentUser.value?.role === 'admin')

const TEMPLATE_TIPS = {
  answer: '学生在网页上答题，回收每题作答、对错、得分',
  self_eval: '学生对自己的表现按几个维度打分、写反思',
  peer_eval: '学生给同组同学打分、写评语',
  survey: '课堂问卷、投票、意见收集',
  custom: '其他任何数据，原样收下'
}

async function load() {
  loading.value = true
  try {
    const res = await api.dataApis(owner.value ? { owner_id: owner.value } : {})
    rows.value = res.items
    templates.value = res.templates
    teachers.value = res.teachers || []
  } finally {
    loading.value = false
  }
}
onMounted(load)

const shown = computed(() => {
  const k = keyword.value.trim()
  return k ? rows.value.filter(r => r.name.includes(k) || (r.description || '').includes(k)) : rows.value
})

const dlg = ref(false)
const saving = ref(false)
const form = ref({ name: '', description: '', template: 'answer' })
function openCreate() {
  form.value = { name: '', description: '', template: 'answer' }
  dlg.value = true
}
async function create() {
  if (!form.value.name.trim()) return ElMessage.warning('请填 API 名称')
  saving.value = true
  try {
    const res = await api.dataApiCreate(form.value)
    dlg.value = false
    ElMessage.success('建好了，把下面的 AI 提示词交给 AI 就能做出接好数据的网页')
    router.push({ path: `/js/api/${res.id}`, query: { tab: 'connect', prompt: '1' } })
  } finally {
    saving.value = false
  }
}

function fmt(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '还没收到过'
}
</script>

<template>
  <div class="page">
    <div class="head">
      <div>
        <h2>API</h2>
        <p class="sub">
          建一个 API，把接收地址给你做的答题网页、自评互评表或问卷，学生提交的数据就收进来，
          在这里看数据表单和数据大图。名单里对得上的学生，数据还会汇总进他的「学情」。
        </p>
      </div>
      <div class="tools">
        <el-select v-if="isAdmin" v-model="owner" clearable placeholder="全部老师" style="width: 140px" @change="load">
          <el-option v-for="t in teachers" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-input v-model="keyword" placeholder="搜索名称、描述" clearable style="width: 180px" />
        <el-button type="primary" @click="openCreate">＋ 新建 API</el-button>
      </div>
    </div>

    <div v-loading="loading" class="grid">
      <el-empty v-if="!loading && !rows.length" description="还没有 API">
        <el-button type="primary" @click="openCreate">新建第一个 API</el-button>
      </el-empty>
      <el-card v-for="r in shown" :key="r.id" class="card" shadow="hover" @click="router.push(`/js/api/${r.id}`)">
        <div class="card-top">
          <span class="name">{{ r.name }}</span>
          <el-tag size="small" :type="r.status === 'active' ? 'success' : 'info'">
            {{ r.status === 'active' ? '接收中' : '已暂停' }}
          </el-tag>
        </div>
        <div class="desc">{{ r.description || '（没有描述）' }}</div>
        <div class="nums">
          <div><b>{{ r.record_count }}</b><span>总条数</span></div>
          <div><b>{{ r.today_count }}</b><span>今天</span></div>
          <div class="last"><b>{{ fmt(r.last_received_at) }}</b><span>最后收到</span></div>
        </div>
        <div class="foot">
          <el-tag size="small" effect="plain">{{ r.template_name }}</el-tag>
          <span v-if="isAdmin" class="owner">{{ r.owner_name }}</span>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="dlg" title="新建 API" width="520px">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="64" show-word-limit placeholder="如：第3课 网页答题回收" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="2000"
                    placeholder="用在哪节课、哪个网页，方便以后找" />
        </el-form-item>
        <el-form-item label="用途">
          <el-radio-group v-model="form.template" class="tpl">
            <el-radio v-for="(label, k) in templates" :key="k" :value="k">
              {{ label }}<span class="tip">{{ TEMPLATE_TIPS[k] }}</span>
            </el-radio>
          </el-radio-group>
          <div class="hint">用途只决定默认的图表和示例代码，不限制能收什么数据，以后也能改。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">建好</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { max-width: 1280px; margin: 0 auto; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.head h2 { margin: 0 0 6px; }
.sub { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; max-width: 720px; line-height: 1.6; }
.tools { display: flex; gap: 8px; flex-wrap: wrap; }
.grid { margin-top: 16px; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; min-height: 120px; }
.grid .el-empty { grid-column: 1 / -1; }
.card { cursor: pointer; }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.name { font-weight: 600; font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.desc { margin: 6px 0 12px; color: var(--el-text-color-secondary); font-size: 13px; height: 38px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.nums { display: flex; gap: 18px; }
.nums div { display: flex; flex-direction: column; }
.nums b { font-size: 18px; }
.nums .last b { font-size: 13px; font-weight: 500; line-height: 27px; }
.nums span { font-size: 12px; color: var(--el-text-color-secondary); }
.foot { margin-top: 10px; display: flex; justify-content: space-between; align-items: center; }
.owner { font-size: 12px; color: var(--el-text-color-secondary); }
.tpl { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.tip { margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; line-height: 1.5; }
</style>

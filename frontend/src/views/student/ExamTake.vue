<script setup>
/**
 * 学生平台里的答题页。
 *
 * 和 /take/:token 那个公开页最大的不同：**身份来自账号**，学生不用也不能
 * 填姓名班级 —— 交卷时后端直接按令牌里的学生写库，成绩不会张冠李戴。
 * 相同的一点：这个页面永远拿不到答案，取卷接口不下发，判分在后端做。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api'
import { currentStudent } from '../../auth'

const CN = ['一', '二', '三', '四', '五', '六']
const route = useRoute()
const router = useRouter()
const examId = route.params.id

const me = currentStudent
const paper = ref(null)
const loadError = ref('')
const loading = ref(true)
const submitting = ref(false)
const result = ref(null)
const answers = reactive({})

const numbering = computed(() => {
  const map = {}
  let n = 0
  ;(paper.value?.groups || []).forEach(g => g.items.forEach(q => (map[q.id] = ++n)))
  return map
})

const answered = computed(() => Object.values(answers).filter(v => String(v || '').trim()).length)

/** 交卷后按题号取回判分明细（老师开了「显示答案」才有） */
const detailOf = computed(() => {
  const map = {}
  ;(result.value?.detail || []).forEach(d => (map[d.id] = d))
  return map
})

onMounted(async () => {
  try {
    paper.value = await api.studentPaper(examId)
  } catch (e) {
    loadError.value = e.response?.data?.detail || '打不开这场考试，回列表看看还在不在'
  } finally {
    loading.value = false
  }
})

const asking = ref(false)

async function submit() {
  // 学生紧张时容易连点，挡住重复弹窗和重复提交
  if (asking.value || submitting.value || result.value) return

  const blank = paper.value.total - answered.value
  if (blank > 0) {
    asking.value = true
    try {
      await ElMessageBox.confirm(
        `还有 ${blank} 道题没做，确定要交卷吗？交卷后不能再改。`,
        '确认交卷',
        { type: 'warning', confirmButtonText: '确定交卷', cancelButtonText: '再检查一下' }
      )
    } catch {
      return
    } finally {
      asking.value = false
    }
  }

  submitting.value = true
  try {
    result.value = await api.studentSubmit(examId, answers)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } finally {
    submitting.value = false
  }
}

function back() {
  if (!result.value && answered.value > 0) {
    return ElMessageBox.confirm('还没交卷，现在离开这些作答就没了。确定要走吗？', '提示', {
      type: 'warning',
      confirmButtonText: '离开',
      cancelButtonText: '继续答题'
    }).then(() => router.push('/exam'))
  }
  router.push('/exam')
}
</script>

<template>
  <div class="wrap" v-loading="loading">
    <el-result v-if="loadError" icon="warning" title="无法进入考试" :sub-title="loadError">
      <template #extra>
        <el-button type="primary" @click="router.push('/exam')">返回考试列表</el-button>
      </template>
    </el-result>

    <template v-else-if="paper">
      <!-- 卷头 -->
      <div class="head">
        <h1>{{ paper.title }}</h1>
        <div class="meta">
          <span v-if="paper.school">{{ paper.school }}　·　</span>
          <span v-if="paper.duration">{{ paper.duration }} 分钟　·　</span>
          <span>{{ paper.code }}</span>
        </div>
        <!-- 身份从账号来，学生改不了，所以只显示不给编辑 -->
        <div class="who">
          <span class="idcard">{{ me?.name }}</span>
          <span class="idcard">{{ me?.student_class || '未分班' }}</span>
          <span class="idcard">学号 {{ me?.student_no }}</span>
        </div>
      </div>

      <!-- 交卷结果 -->
      <el-result
        v-if="result"
        :icon="result.score === undefined || result.score === null ? 'success' : result.score >= 60 ? 'success' : 'info'"
        :title="result.score === undefined || result.score === null ? '交卷成功' : `得分 ${result.score}`"
        :sub-title="
          result.score === undefined || result.score === null
            ? result.message
            : `客观题答对 ${result.right_count} / ${result.objective_count}${
                paper.groups.some(g => g.type === '操作题') ? '，操作题由老师评阅' : ''
              }`
        "
      >
        <template #extra>
          <el-button type="primary" @click="router.push('/exam')">返回考试列表</el-button>
        </template>
      </el-result>

      <!-- 题目 -->
      <template v-for="(g, gi) in paper.groups" :key="gi">
        <div class="sect">
          {{ CN[gi] }}、{{ g.type }}（共 {{ g.items.length }} 题）
          <span v-if="g.type === '操作题'" class="sd">这部分由老师评阅</span>
        </div>

        <div v-for="q in g.items" :key="q.id" class="q">
          <div class="stem">
            <span class="no">{{ numbering[q.id] }}.</span>{{ q.stem }}
            <span
              v-if="detailOf[q.id] && detailOf[q.id].scored"
              class="badge"
              :class="detailOf[q.id].ok ? 'b-ok' : 'b-no'"
            >{{ detailOf[q.id].ok ? '✓' : '✕' }}</span>
          </div>

          <img v-if="q.image_url" :src="q.image_url" class="img" alt="配图" />

          <div v-if="q.type === '操作题'" class="body">
            <el-input
              v-model="answers[q.id]"
              type="textarea"
              :rows="3"
              :disabled="!!result"
              placeholder="写下你的操作步骤"
            />
          </div>
          <div v-else class="body">
            <label
              v-for="o in q.options"
              :key="o.label"
              class="op"
              :class="{ picked: answers[q.id] === o.label, disabled: !!result }"
            >
              <input
                type="radio"
                :name="'q' + q.id"
                :value="o.label"
                :disabled="!!result"
                :checked="answers[q.id] === o.label"
                @change="answers[q.id] = o.label"
              />
              <span class="L">{{ o.label }}</span><span>{{ o.content }}</span>
            </label>
          </div>

          <div v-if="detailOf[q.id] && detailOf[q.id].scored && !detailOf[q.id].ok" class="key">
            正确答案：{{ detailOf[q.id].answer }}
          </div>
        </div>
      </template>

      <!-- 底部操作条 -->
      <div class="bar">
        <el-button link @click="back">← 返回列表</el-button>
        <span class="grow" />
        <template v-if="!result">
          <span class="prog">已作答 {{ answered }} / {{ paper.total }}</span>
          <el-button type="primary" size="large" :loading="submitting" @click="submit">
            交卷
          </el-button>
        </template>
        <span v-else class="prog">已交卷</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 880px;
  margin: 0 auto;
  padding: 24px 18px 110px;
  min-height: 100vh;
}
.head {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  padding: 22px;
  text-align: center;
}
.head h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-family: 'Heiti SC', 'SimHei', 'Microsoft YaHei', sans-serif;
  letter-spacing: 0.05em;
}
.meta {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.who {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 14px;
}
.sect {
  margin: 26px 0 8px;
  font-size: 17px;
  font-family: 'Heiti SC', 'SimHei', 'Microsoft YaHei', sans-serif;
}
.sd {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
  margin-left: 8px;
}
.q {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  padding: 15px 17px;
  margin-bottom: 10px;
}
.stem {
  white-space: pre-wrap;
  line-height: 1.8;
}
.no {
  font-weight: 600;
  margin-right: 5px;
}
.img {
  max-width: 100%;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  margin-top: 9px;
}
.body {
  margin-top: 6px;
}
label.op {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  padding: 6px 9px;
  border-radius: 7px;
  border: 1px solid transparent;
  cursor: pointer;
}
label.op:hover {
  background: var(--el-fill-color-light);
}
label.op.picked {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
label.op.disabled {
  cursor: default;
}
.L {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  min-width: 18px;
}
.key {
  margin-top: 10px;
  background: var(--el-color-danger-light-9);
  border-left: 3px solid var(--el-color-danger);
  border-radius: 0 7px 7px 0;
  padding: 7px 11px;
  font-size: 13.5px;
  color: var(--el-color-danger);
}
.badge {
  font-size: 12px;
  font-weight: 600;
  border-radius: 5px;
  padding: 1px 8px;
  margin-left: 8px;
}
.b-ok {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.b-no {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--el-bg-color);
  border-top: 1px solid var(--el-border-color-light);
  padding: 12px 18px;
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: center;
}
.prog {
  font-family: ui-monospace, Consolas, monospace;
  color: var(--el-text-color-regular);
}
.tip {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 4px 0;
}

/* 学生平台特有的几条：身份是只读的，底部条多了返回按钮 */
.idcard {
  display: inline-block;
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
.bar .grow {
  flex: 1;
}
</style>

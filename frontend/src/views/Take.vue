<script setup>
/**
 * 学生答题页。不需要登录，凭链接里的口令访问。
 * 这个页面永远拿不到答案——取卷接口不下发，判分在后端做。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const CN = ['一', '二', '三', '四', '五', '六']
const route = useRoute()
const token = route.params.token

const paper = ref(null)
const loadError = ref('')
const loading = ref(true)
const submitting = ref(false)
const result = ref(null)

const me = reactive({ student_name: '', student_class: '', student_no: '' })
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
    paper.value = await api.takePaper(token)
  } catch (e) {
    loadError.value = e.response?.data?.detail || '打不开这场考试，请向老师确认链接'
  } finally {
    loading.value = false
  }
})

const asking = ref(false)

async function submit() {
  // 学生紧张时容易连点，挡住重复弹窗和重复提交
  if (asking.value || submitting.value || result.value) return

  if (!me.student_name.trim()) {
    ElMessage.warning('请先填写姓名')
    return
  }

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
    result.value = await api.submitPaper(token, { ...me, answers })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="wrap" v-loading="loading">
    <el-result v-if="loadError" icon="warning" title="无法进入考试" :sub-title="loadError" />

    <template v-else-if="paper">
      <!-- 卷头 -->
      <div class="head">
        <h1>{{ paper.title }}</h1>
        <div class="meta">
          <span v-if="paper.school">{{ paper.school }}　·　</span>
          <span v-if="paper.duration">{{ paper.duration }} 分钟　·　</span>
          <span>{{ paper.code }}</span>
        </div>
        <div v-if="!result" class="who">
          <el-input v-model="me.student_name" placeholder="姓名" style="width: 140px" />
          <el-input v-model="me.student_class" placeholder="班级" style="width: 160px" />
          <el-input v-model="me.student_no" placeholder="学号" style="width: 160px" />
        </div>
      </div>

      <!-- 交卷结果 -->
      <el-result
        v-if="result"
        :icon="result.score === null ? 'success' : result.score >= 60 ? 'success' : 'info'"
        :title="result.score === null ? '交卷成功' : `得分 ${result.score}`"
        :sub-title="
          result.score === null
            ? result.message
            : `客观题答对 ${result.right_count} / ${result.objective_count}${
                paper.groups.some(g => g.type === '操作题') ? '，操作题由老师评阅' : ''
              }`
        "
      >
        <template #extra>
          <p class="tip">{{ me.student_name }}　{{ me.student_class }}　{{ me.student_no }}</p>
          <p class="tip">这个页面可以关掉了。</p>
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
              :class="{
                picked: answers[q.id] === o.label,
                disabled: !!result
              }"
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
      <div v-if="!result" class="bar">
        <span class="prog">已作答 {{ answered }} / {{ paper.total }}</span>
        <el-button type="primary" size="large" :loading="submitting" @click="submit">
          交卷
        </el-button>
      </div>
      <div v-else class="bar">
        <span class="prog">已交卷</span>
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
</style>

<script setup>
/** 我能参加的考试。列表由后端按班级筛过，这里只管展示。 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api'

const router = useRouter()
const rows = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    rows.value = await api.studentExams()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const todo = computed(() => rows.value.filter(e => !e.submitted))
const done = computed(() => rows.value.filter(e => e.submitted))

function open(e) {
  if (e.submitted && !e.allow_retake) {
    return ElMessage.info('这场考试你已经交过卷了，如需重考请找老师')
  }
  router.push(`/exam/${e.id}`)
}

const fmt = t => (t ? String(t).replace('T', ' ').slice(0, 16) : '')
</script>

<template>
  <div class="page" v-loading="loading">
    <el-empty
      v-if="!rows.length && !loading"
      description="现在没有可以参加的考试，老师发布后会出现在这里"
      :image-size="90"
    />

    <template v-else>
      <section v-if="todo.length">
        <h3 class="sect">待完成<span class="cnt">{{ todo.length }}</span></h3>
        <div class="grid">
          <article v-for="e in todo" :key="e.id" class="card todo" @click="open(e)">
            <div class="tag">待作答</div>
            <h4>{{ e.title }}</h4>
            <div class="meta">
              <span>共 {{ e.total }} 题</span>
              <span v-if="e.created_at">发布于 {{ fmt(e.created_at) }}</span>
            </div>
            <el-button type="primary" size="small" class="go">开始答题</el-button>
          </article>
        </div>
      </section>

      <section v-if="done.length">
        <h3 class="sect">已完成<span class="cnt">{{ done.length }}</span></h3>
        <div class="grid">
          <article v-for="e in done" :key="e.id" class="card">
            <div class="tag ok">已交卷</div>
            <h4>{{ e.title }}</h4>
            <div class="meta">
              <span>共 {{ e.total }} 题</span>
              <span v-if="e.submitted_at">{{ fmt(e.submitted_at) }} 交卷</span>
            </div>
            <div class="foot">
              <span v-if="e.score !== null && e.score !== undefined" class="score">
                {{ e.score }}<i>分</i>
              </span>
              <span v-else class="pending">成绩由老师统一公布</span>
              <el-button v-if="e.allow_retake" size="small" @click.stop="open(e)">再考一次</el-button>
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 980px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}
.sect {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
}
.cnt {
  margin-left: 8px;
  font-size: 12px;
  font-family: ui-monospace, Consolas, monospace;
  color: var(--el-text-color-secondary);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(258px, 1fr));
  gap: 14px;
}
.card {
  position: relative;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.card.todo {
  cursor: pointer;
  border-color: var(--el-color-primary-light-7);
  transition: box-shadow 0.16s, transform 0.16s;
}
.card.todo:hover {
  box-shadow: 0 6px 20px rgba(64, 100, 220, 0.14);
  transform: translateY(-2px);
}
.tag {
  align-self: flex-start;
  font-size: 11.5px;
  padding: 2px 9px;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.tag.ok {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
h4 {
  margin: 0;
  font-size: 15.5px;
  font-weight: 600;
  line-height: 1.5;
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.go {
  align-self: flex-start;
  margin-top: 2px;
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 2px;
}
.score {
  font-size: 24px;
  font-weight: 650;
  font-family: ui-monospace, Consolas, monospace;
  color: var(--el-color-success);
}
.score i {
  font-style: normal;
  font-size: 12px;
  font-weight: 400;
  margin-left: 2px;
  color: var(--el-text-color-secondary);
}
.pending {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
</style>

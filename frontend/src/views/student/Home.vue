<script setup>
/**
 * 学生首页：个人基本信息 + 改密码 + 几个学习数字。
 *
 * 学号和姓名是学校给的身份，这里只读不改 —— 学生改了姓名，
 * 老师那边的成绩单就对不上人了。要改找老师。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api'
import { currentStudent } from '../../auth'

const me = currentStudent
const home = ref(null)
const loading = ref(false)

const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const saving = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    home.value = await api.studentHome()
  } finally {
    loading.value = false
  }
})

async function changePassword() {
  if (!pwd.old_password || !pwd.new_password) return ElMessage.warning('原密码和新密码都要填')
  // 只有前端知道"两次输入是否一致"，其余规则交给后端，它的提示更具体
  if (pwd.new_password !== pwd.confirm) return ElMessage.warning('两次输入的新密码不一致')

  saving.value = true
  try {
    await api.studentChangePassword({
      old_password: pwd.old_password,
      new_password: pwd.new_password
    })
    pwd.old_password = pwd.new_password = pwd.confirm = ''
    ElMessage.success('密码已修改，下次登录用新密码')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page" v-loading="loading">
    <!-- 个人信息 -->
    <section class="card hero">
      <div class="avatar">{{ (me?.name || '?').slice(0, 1) }}</div>
      <div class="who">
        <h2>{{ me?.name || '—' }}</h2>
        <div class="meta">
          <span class="pill">学号 {{ me?.student_no || '—' }}</span>
          <span class="pill">{{ me?.student_class || '未分班' }}</span>
        </div>
        <p class="note">学号和姓名由学校统一分配，如有错误请找任课老师修改。</p>
      </div>
    </section>

    <!-- 学习概况 -->
    <section class="stats">
      <div class="stat">
        <span class="n">{{ home?.exam_done ?? 0 }} <i>/ {{ home?.exam_total ?? 0 }}</i></span>
        <span class="l">已完成考试</span>
      </div>
      <div class="stat">
        <span class="n">{{ home?.typing_count ?? 0 }}</span>
        <span class="l">打字练习次数</span>
      </div>
      <div class="stat">
        <span class="n">{{ home?.typing_best_speed ?? 0 }} <i>字/分</i></span>
        <span class="l">最快打字速度</span>
      </div>
      <div class="stat">
        <span class="n">{{ home?.typing_avg_accuracy ?? 0 }}<i>%</i></span>
        <span class="l">平均正确率</span>
      </div>
    </section>

    <!-- 改密码 -->
    <section class="card">
      <h3>修改密码</h3>
      <p class="hint">
        初始密码就是学号，同学之间很容易猜到，<b>第一次登录后请尽快改掉</b>。
      </p>
      <div class="form">
        <label class="field">
          <span>原密码</span>
          <el-input v-model="pwd.old_password" type="password" show-password placeholder="当前使用的密码" />
        </label>
        <label class="field">
          <span>新密码</span>
          <el-input v-model="pwd.new_password" type="password" show-password placeholder="至少 6 位，别用学号" />
        </label>
        <label class="field">
          <span>确认新密码</span>
          <el-input
            v-model="pwd.confirm"
            type="password"
            show-password
            placeholder="再输一次"
            @keyup.enter="changePassword"
          />
        </label>
      </div>
      <el-button type="primary" :loading="saving" @click="changePassword">修改密码</el-button>
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 860px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 20px 22px;
}

.hero {
  display: flex;
  align-items: center;
  gap: 20px;
}
.avatar {
  width: 62px;
  height: 62px;
  flex: none;
  border-radius: 18px;
  background: linear-gradient(135deg, #5b7cfa, #3f5bd8);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  font-weight: 600;
}
.who h2 {
  margin: 0 0 8px;
  font-size: 19px;
  font-weight: 650;
}
.meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.pill {
  font-size: 12.5px;
  padding: 3px 11px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
.note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.stat {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stat .n {
  font-size: 24px;
  font-weight: 650;
  font-family: ui-monospace, Consolas, monospace;
  color: var(--el-color-primary);
}
.stat .n i {
  font-style: normal;
  font-size: 13px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.stat .l {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}

h3 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
}
.hint {
  margin: 0 0 16px;
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--el-text-color-secondary);
}
.form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}
.field > span {
  display: block;
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 6px;
}
</style>

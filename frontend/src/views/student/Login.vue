<script setup>
/** 学生登录：学号 + 密码。账号由老师创建，这里不提供注册。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api'
import { setStudent } from '../../auth'
import { siteConfig, year } from '../../siteConfig'

const router = useRouter()
const title = computed(
  () => siteConfig.site?.student_title || '昌邑市实验中学信息科技学生实践平台'
)

const form = reactive({ student_no: '', password: '' })
const loading = ref(false)
const noRef = ref(null)

onMounted(() => {
  // 机房里同一台电脑轮流用，记住上次的学号能省点事；密码当然不记
  form.student_no = localStorage.getItem('lastStudentNo') || ''
  noRef.value?.focus()
})

async function submit() {
  if (!form.student_no.trim()) return ElMessage.warning('请输入学号')
  if (!form.password) return ElMessage.warning('请输入密码')

  loading.value = true
  try {
    const res = await api.studentLogin(form.student_no.trim(), form.password)
    localStorage.setItem('studentToken', res.access_token)
    localStorage.setItem('lastStudentNo', form.student_no.trim())
    setStudent(res.student)
    ElMessage.success(`欢迎，${res.student.name}`)
    router.push('/home')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="wrap">
    <div class="card">
      <div class="head">
        <span class="logo">科</span>
        <h1>{{ title }}</h1>
        <p class="sub">用学号登录，做考试和打字练习</p>
      </div>

      <form @submit.prevent="submit">
        <label class="field">
          <span>学号</span>
          <el-input
            ref="noRef"
            v-model="form.student_no"
            size="large"
            placeholder="老师发给你的学号"
            autocomplete="username"
          />
        </label>
        <label class="field">
          <span>密码</span>
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            show-password
            placeholder="初始密码就是学号"
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </label>
        <el-button type="primary" size="large" class="btn" :loading="loading" @click="submit">
          登录
        </el-button>
      </form>

      <p class="tip">
        第一次登录：<b>密码就是你的学号</b>，登录后请到「首页」改掉。<br />
        忘记密码找任课老师重置。
      </p>

      <p class="copy">
        © {{ year }} 昌邑市实验中学
        <router-link to="/js/login" class="teacher">教师入口</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: linear-gradient(160deg, #eef2f7, #dde6f5 60%, #e8eefb);
}
.card {
  width: 100%;
  max-width: 388px;
  background: var(--el-bg-color);
  border-radius: 16px;
  padding: 34px 30px 24px;
  box-shadow: 0 12px 40px rgba(31, 56, 120, 0.12);
}
.head {
  text-align: center;
  margin-bottom: 24px;
}
.logo {
  display: inline-flex;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, #5b7cfa, #3f5bd8);
  color: #fff;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 14px;
}
h1 {
  font-size: 17px;
  font-weight: 650;
  margin: 0 0 6px;
  line-height: 1.5;
}
.sub {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.field {
  display: block;
  margin-bottom: 16px;
}
.field > span {
  display: block;
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 6px;
}
.btn {
  width: 100%;
  margin-top: 4px;
}
.tip {
  margin: 20px 0 0;
  font-size: 12px;
  line-height: 1.9;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 9px;
  padding: 10px 13px;
}
.copy {
  margin: 16px 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.teacher {
  margin-left: 10px;
  color: var(--el-text-color-placeholder);
  text-decoration: none;
}
.teacher:hover {
  color: var(--el-color-primary);
}

@media (prefers-color-scheme: dark) {
  .wrap {
    background: var(--el-bg-color-page);
  }
}
</style>

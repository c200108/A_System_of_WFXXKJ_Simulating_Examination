<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const router = useRouter()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const res = await api.login(form.username, form.password)
    localStorage.setItem('token', res.access_token)
    localStorage.setItem('user', JSON.stringify(res.user))
    ElMessage.success(`欢迎回来，${res.user.name || res.user.username}`)
    router.push('/paper')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">信息技术组卷台</h2>
      <p class="sub">教师登录后可以组卷、维护题库、导入模板</p>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" size="large" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            show-password
            placeholder="请输入密码"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="btn" :loading="loading" @click="submit">
          登录
        </el-button>
      </el-form>
      <p class="tip">首次部署的默认账号见 .env 里的 ADMIN_USERNAME / ADMIN_PASSWORD，登录后请立刻改密码。</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #eef2f7, #dfe7f3);
}
.login-card {
  width: 380px;
  padding: 8px 12px 16px;
}
.title {
  margin: 4px 0 6px;
  font-size: 20px;
}
.sub {
  margin: 0 0 18px;
  color: #909399;
  font-size: 13px;
}
.btn {
  width: 100%;
}
.tip {
  margin-top: 16px;
  color: #a8abb2;
  font-size: 12px;
  line-height: 1.6;
}
</style>

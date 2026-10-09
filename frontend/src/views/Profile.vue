<script setup>
/**
 * 我的账号：看账号信息、改个人资料、改密码。
 *
 * 能改的只有姓名、任教年级班级、联系方式三项 —— 用户名、角色、启停
 * 都得管理员来，接口那边也是这么限的，不是光靠这里不显示。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { currentUser, setUser } from '../auth'

const loading = ref(false)
const savingProfile = ref(false)
const savingPwd = ref(false)

const profile = reactive({ name: '', grade_class: '', contact: '' })
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })

const user = currentUser

const roleLabel = computed(() => (user.value?.role === 'admin' ? '系统管理员' : '教师'))
const joined = computed(() =>
  user.value?.created_at ? String(user.value.created_at).replace('T', ' ').slice(0, 10) : '—'
)
const initial = computed(() => (user.value?.name || user.value?.username || '?').slice(0, 1))

function fill(u) {
  profile.name = u?.name || ''
  profile.grade_class = u?.grade_class || ''
  profile.contact = u?.contact || ''
}

onMounted(async () => {
  loading.value = true
  try {
    const u = await api.me() // 以服务端为准，localStorage 里可能是旧的
    setUser(u)
    fill(u)
  } finally {
    loading.value = false
  }
})

async function saveProfile() {
  savingProfile.value = true
  try {
    const u = await api.updateMe({ ...profile })
    setUser(u) // 顶栏的名字要立刻跟着变
    fill(u)
    ElMessage.success('资料已保存')
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  // 只留前端才知道的那条（两次输入是否一致）。长度、纯数字之类交给后端判，
  // 它的报错更具体，也不会和后端规则脱节。
  if (!pwd.old_password || !pwd.new_password) return ElMessage.warning('原密码和新密码都要填')
  if (pwd.new_password !== pwd.confirm) return ElMessage.warning('两次输入的新密码不一致')

  savingPwd.value = true
  try {
    await api.changePassword({
      old_password: pwd.old_password,
      new_password: pwd.new_password
    })
    pwd.old_password = pwd.new_password = pwd.confirm = ''
    ElMessage.success('密码已修改，下次登录请用新密码')
  } finally {
    savingPwd.value = false
  }
}
</script>

<template>
  <div class="page" v-loading="loading">
    <!-- 账号信息 -->
    <el-card shadow="never" class="idcard">
      <div class="idrow">
        <div class="avatar">{{ initial }}</div>
        <div class="who">
          <div class="nm">
            {{ user?.name || user?.username }}
            <el-tag :type="user?.role === 'admin' ? 'danger' : 'primary'" size="small" effect="light">
              {{ roleLabel }}
            </el-tag>
          </div>
          <div class="sub">
            登录名 <b>{{ user?.username }}</b>
            <span class="dot">·</span>
            启用于 {{ joined }}
          </div>
        </div>
      </div>
      <el-alert v-if="user?.role !== 'admin'" type="info" :closable="false" class="scope-tip">
        你只看得到<b>自己发布的考试</b>和上面的成绩，别的老师同样看不到你的。
        需要跨账号查看请找系统管理员。
      </el-alert>
      <el-alert v-else type="warning" :closable="false" class="scope-tip">
        你是系统管理员：看得到<b>全校所有老师</b>的考试与成绩，也只有你能下架和删除反馈评论。
      </el-alert>
    </el-card>

    <div class="cols">
      <!-- 个人资料 -->
      <el-card shadow="never">
        <template #header><span class="ch">个人资料</span></template>
        <el-form label-position="top">
          <el-form-item label="姓名">
            <el-input v-model="profile.name" maxlength="64" placeholder="显示在顶栏和反馈回复的署名上" />
          </el-form-item>
          <el-form-item label="任教年级班级">
            <el-input
              v-model="profile.grade_class"
              maxlength="128"
              placeholder="如 七年级 1-4 班、八(2)(3)班"
            />
          </el-form-item>
          <el-form-item label="联系方式">
            <el-input v-model="profile.contact" maxlength="64" placeholder="手机号或办公室电话，选填" />
          </el-form-item>
          <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</el-button>
        </el-form>
        <p class="note">
          登录名和角色不能自己改。忘了密码也只能由管理员重置 —— 系统里没存邮箱，找不回来。
        </p>
      </el-card>

      <!-- 修改密码 -->
      <el-card shadow="never">
        <template #header><span class="ch">修改密码</span></template>
        <el-form label-position="top">
          <el-form-item label="原密码">
            <el-input v-model="pwd.old_password" type="password" show-password autocomplete="current-password" />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input
              v-model="pwd.new_password"
              type="password"
              show-password
              autocomplete="new-password"
              placeholder="至少 6 位"
            />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input
              v-model="pwd.confirm"
              type="password"
              show-password
              autocomplete="new-password"
              @keyup.enter="savePassword"
            />
          </el-form-item>
          <el-button type="primary" :loading="savingPwd" @click="savePassword">修改密码</el-button>
        </el-form>
        <p class="note">改完当前登录不会掉线，但下次登录要用新密码。</p>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 900px;
  margin: 0 auto;
  padding: 4px 4px 60px;
}
.idcard {
  margin-bottom: 16px;
}
.idrow {
  display: flex;
  align-items: center;
  gap: 16px;
}
.avatar {
  width: 54px;
  height: 54px;
  flex: none;
  border-radius: 15px;
  background: linear-gradient(135deg, #5b7cfa, #4f6ef7);
  color: #fff;
  font-size: 24px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.nm {
  font-size: 19px;
  font-weight: 650;
  display: flex;
  align-items: center;
  gap: 10px;
}
.sub {
  margin-top: 5px;
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
.sub b {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 600;
}
.dot {
  margin: 0 7px;
}
.scope-tip {
  margin-top: 16px;
}

.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 780px) {
  .cols {
    grid-template-columns: 1fr;
  }
}
.ch {
  font-weight: 600;
}
.note {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}
</style>

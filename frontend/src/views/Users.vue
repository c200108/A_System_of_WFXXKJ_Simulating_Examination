<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const users = ref([])
const dialog = ref(false)
const pwdDialog = ref(false)
const form = reactive({ username: '', password: '', name: '', role: 'teacher' })
const pwd = reactive({ old_password: '', new_password: '' })

async function load() {
  users.value = await api.listUsers()
}
onMounted(load)

async function create() {
  if (!form.username || form.password.length < 6) {
    return ElMessage.warning('用户名必填，密码至少 6 位')
  }
  await api.createUser({ ...form })
  ElMessage.success('已创建')
  dialog.value = false
  Object.assign(form, { username: '', password: '', name: '', role: 'teacher' })
  load()
}

async function disable(row) {
  await ElMessageBox.confirm(`确定停用「${row.name || row.username}」？`, '提示', { type: 'warning' })
  await api.disableUser(row.id)
  ElMessage.success('已停用')
  load()
}

async function changePassword() {
  if (pwd.new_password.length < 6) return ElMessage.warning('新密码至少 6 位')
  await api.changePassword({ ...pwd })
  ElMessage.success('密码已修改')
  pwdDialog.value = false
  Object.assign(pwd, { old_password: '', new_password: '' })
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>教师账号</span>
        <div>
          <el-button size="small" @click="pwdDialog = true">修改我的密码</el-button>
          <el-button size="small" type="primary" @click="dialog = true">新增账号</el-button>
        </div>
      </div>
    </template>

    <el-table :data="users" border size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" width="160" />
      <el-table-column prop="name" label="姓名" width="160" />
      <el-table-column label="角色" width="110">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
            {{ row.role === 'admin' ? '管理员' : '教师' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <span :class="row.is_active ? 'on' : 'off'">{{ row.is_active ? '正常' : '已停用' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间">
        <template #default="{ row }">{{ String(row.created_at).replace('T', ' ').slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button v-if="row.is_active" link type="danger" @click="disable(row)">停用</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialog" title="新增账号" width="440px">
    <el-form label-width="80px">
      <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="初始密码"><el-input v-model="form.password" show-password /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role" style="width: 140px">
          <el-option label="教师" value="teacher" />
          <el-option label="管理员" value="admin" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">取消</el-button>
      <el-button type="primary" @click="create">创建</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="pwdDialog" title="修改我的密码" width="400px">
    <el-form label-width="80px">
      <el-form-item label="原密码"><el-input v-model="pwd.old_password" show-password /></el-form-item>
      <el-form-item label="新密码"><el-input v-model="pwd.new_password" show-password /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialog = false">取消</el-button>
      <el-button type="primary" @click="changePassword">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.on {
  color: #67c23a;
}
.off {
  color: #f56c6c;
}
</style>

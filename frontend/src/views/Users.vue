<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { currentUser, setUser } from '../auth'

const users = ref([])
const loading = ref(false)

const dialog = ref(false)
const pwdDialog = ref(false)
const resetDialog = ref(false)

const form = reactive({ username: '', password: '', name: '', role: 'teacher' })
const pwd = reactive({ old_password: '', new_password: '' })
const reset = reactive({ id: null, who: '', password: '' })

async function load() {
  loading.value = true
  try {
    users.value = await api.listUsers()
  } finally {
    loading.value = false
  }
}
onMounted(load)

/** 随机口令：去掉了 0/O/1/l/I 这些容易看错的字符，念给老师抄不会错 */
function randomPassword(n = 12) {
  const chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const buf = new Uint32Array(n)
  crypto.getRandomValues(buf)
  return Array.from(buf, x => chars[x % chars.length]).join('')
}

// ---------- 新增 ----------
function openCreate() {
  Object.assign(form, { username: '', password: randomPassword(), name: '', role: 'teacher' })
  dialog.value = true
}

async function create() {
  if (!form.username.trim()) return ElMessage.warning('用户名必填')
  if (form.password.length < 6) return ElMessage.warning('密码至少 6 位')
  await api.createUser({ ...form })
  dialog.value = false
  await load()
  await ElMessageBox.alert(
    `账号：${form.username}\n密码：${form.password}`,
    '创建成功，请把这两行发给老师',
    { confirmButtonText: '我记下了' }
  )
}

// ---------- 重置密码 ----------
function openReset(row) {
  Object.assign(reset, { id: row.id, who: row.name || row.username, password: randomPassword() })
  resetDialog.value = true
}

async function doReset() {
  if (reset.password.length < 6) return ElMessage.warning('密码至少 6 位')
  await api.updateUser(reset.id, { password: reset.password })
  resetDialog.value = false
  await ElMessageBox.alert(
    `${reset.who} 的新密码：${reset.password}`,
    '已重置，请把新密码发给本人',
    { confirmButtonText: '我记下了' }
  )
}

// ---------- 改资料 ----------
async function rename(row) {
  const { value } = await ElMessageBox.prompt('姓名', '修改姓名', {
    inputValue: row.name,
    inputValidator: v => (v && v.trim() ? true : '不能为空')
  })
  await api.updateUser(row.id, { name: value.trim() })
  await load()
  ElMessage.success('已修改')
}

async function setRole(row, role) {
  await api.updateUser(row.id, { role })
  await load()
  // 改的是自己就同步顶栏，否则「账号」菜单会和实际权限对不上
  if (row.id === currentUser.value?.id) setUser(await api.me())
  ElMessage.success(role === 'admin' ? '已设为管理员' : '已改为普通教师')
}

async function toggleActive(row) {
  if (row.is_active) {
    await ElMessageBox.confirm(
      `停用后「${row.name || row.username}」将无法登录，确定吗？`,
      '提示',
      { type: 'warning' }
    )
    await api.disableUser(row.id)
    ElMessage.success('已停用')
  } else {
    await api.updateUser(row.id, { is_active: true })
    ElMessage.success('已重新启用')
  }
  await load()
}

// ---------- 改自己的密码 ----------
async function changePassword() {
  if (pwd.new_password.length < 6) return ElMessage.warning('新密码至少 6 位')
  await api.changePassword({ ...pwd })
  pwdDialog.value = false
  Object.assign(pwd, { old_password: '', new_password: '' })
  ElMessage.success('密码已修改')
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>教师账号</span>
        <div>
          <el-button size="small" @click="pwdDialog = true">修改我的密码</el-button>
          <el-button size="small" type="primary" @click="openCreate">新增账号</el-button>
        </div>
      </div>
    </template>

    <el-alert type="info" :closable="false" class="hint">
      系统里没有邮箱，老师忘记密码<b>只能由管理员重置</b>。重置后新密码只显示一次，请当场发给本人。
    </el-alert>

    <el-table :data="users" v-loading="loading" border size="small">
      <el-table-column prop="id" label="ID" width="56" />
      <el-table-column prop="username" label="用户名" width="130" show-overflow-tooltip />
      <el-table-column prop="name" label="姓名" width="130" show-overflow-tooltip />
      <el-table-column prop="grade_class" label="任教年级班级" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.grade_class">{{ row.grade_class }}</span>
          <span v-else class="blank">未填</span>
        </template>
      </el-table-column>
      <el-table-column prop="contact" label="联系方式" width="130" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.contact">{{ row.contact }}</span>
          <span v-else class="blank">未填</span>
        </template>
      </el-table-column>
      <el-table-column label="角色" width="96">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
            {{ row.role === 'admin' ? '管理员' : '教师' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <span :class="row.is_active ? 'on' : 'off'">{{ row.is_active ? '正常' : '已停用' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="150">
        <template #default="{ row }">{{ String(row.created_at).replace('T', ' ').slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openReset(row)">重置密码</el-button>
          <el-button link type="primary" @click="rename(row)">改姓名</el-button>
          <el-button
            v-if="row.role !== 'admin'"
            link
            type="warning"
            @click="setRole(row, 'admin')"
          >设为管理员</el-button>
          <el-button
            v-else-if="row.id !== currentUser?.id"
            link
            type="warning"
            @click="setRole(row, 'teacher')"
          >降为教师</el-button>
          <el-button
            v-if="row.id !== currentUser?.id"
            link
            :type="row.is_active ? 'danger' : 'success'"
            @click="toggleActive(row)"
          >{{ row.is_active ? '停用' : '启用' }}</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <!-- 新增 -->
  <el-dialog v-model="dialog" title="新增账号" width="460px">
    <el-form label-width="80px">
      <el-form-item label="用户名"><el-input v-model="form.username" placeholder="登录用，建议用拼音或工号" /></el-form-item>
      <el-form-item label="姓名"><el-input v-model="form.name" placeholder="留空则同用户名" /></el-form-item>
      <el-form-item label="初始密码">
        <el-input v-model="form.password">
          <template #append>
            <el-button @click="form.password = randomPassword()">换一个</el-button>
          </template>
        </el-input>
      </el-form-item>
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

  <!-- 重置密码 -->
  <el-dialog v-model="resetDialog" title="重置密码" width="440px">
    <p class="who-line">给「{{ reset.who }}」设置新密码：</p>
    <el-input v-model="reset.password">
      <template #append>
        <el-button @click="reset.password = randomPassword()">换一个</el-button>
      </template>
    </el-input>
    <p class="tip">确定后新密码只显示一次，请当场记下发给本人。</p>
    <template #footer>
      <el-button @click="resetDialog = false">取消</el-button>
      <el-button type="primary" @click="doReset">确定重置</el-button>
    </template>
  </el-dialog>

  <!-- 改自己的密码 -->
  <el-dialog v-model="pwdDialog" title="修改我的密码" width="400px">
    <el-form label-width="80px">
      <el-form-item label="原密码"><el-input v-model="pwd.old_password" type="password" show-password /></el-form-item>
      <el-form-item label="新密码"><el-input v-model="pwd.new_password" type="password" show-password /></el-form-item>
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
.hint {
  margin-bottom: 14px;
}
.on {
  color: var(--el-color-success);
}
.off {
  color: var(--el-color-danger);
}
.who-line {
  margin: 0 0 10px;
}
.tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 10px 0 0;
}
.blank {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>

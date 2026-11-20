<script setup>
/**
 * 「我的账号」里的个人云盘（2.25.0）：分到多少、用了多少、云盘登录名，以及单独设云盘密码。
 * 服务器没启用云盘时整块不显示。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { fmtBytes, openCloud, usedPct } from '../cloud'
import CloudUrl from './CloudUrl.vue'

const info = ref(null)
const pwd = reactive({ password: '', confirm: '', current: '', saving: false })

async function load() {
  try {
    info.value = await api.cloudMe()
  } catch {
    info.value = null
  }
}
onMounted(load)

const pct = computed(() => usedPct(info.value?.used_bytes, info.value?.quota_bytes))

async function setCustom() {
  if (!pwd.password) return ElMessage.warning('先填新的云盘密码')
  if (pwd.password !== pwd.confirm) return ElMessage.warning('两次输入的密码不一致')
  pwd.saving = true
  try {
    info.value = { ...info.value, ...(await api.cloudSetPassword(pwd.password)) }
    pwd.password = pwd.confirm = ''
    ElMessage.success('云盘密码已单独设置。直接打开云盘登录时用这个密码')
  } finally {
    pwd.saving = false
  }
}

async function syncBack() {
  if (!pwd.current) return ElMessage.warning('请输入教学平台的登录密码')
  pwd.saving = true
  try {
    info.value = { ...info.value, ...(await api.cloudSyncPassword(pwd.current)) }
    pwd.current = ''
    ElMessage.success('云盘密码已改回和教学平台一致')
  } finally {
    pwd.saving = false
  }
}
</script>

<template>
  <el-card v-if="info?.enabled" shadow="never" class="cloudcard">
    <template #header>
      <div class="head">
        <span class="ch">☁ 个人云盘</span>
        <el-button v-if="info.allocated" type="primary" size="small" @click="openCloud">打开个人云盘</el-button>
      </div>
    </template>

    <el-alert v-if="!info.allocated" type="info" :closable="false">
      你还没有分配个人云盘空间，暂时无法使用。需要的话请联系系统管理员分配。
    </el-alert>

    <template v-else>
      <div class="usage">
        <el-progress :percentage="pct" :stroke-width="12" :status="info.over_quota ? 'exception' : ''" />
        <div class="num">
          已用 <b>{{ fmtBytes(info.used_bytes) }}</b> / 共 {{ fmtBytes(info.quota_bytes) }}
          <span class="muted">（用量每 5 分钟统计一次）</span>
        </div>
      </div>
      <el-alert v-if="info.over_quota" type="error" :closable="false" class="over">
        空间超出了分配的额度，暂时不能上传、复制、解压，删掉一些文件后几分钟内自动恢复。
      </el-alert>

      <CloudUrl class="url" />
      <p class="note">
        点顶栏的「☁ 个人云盘」就能直接进去，不用再登录。在别的电脑、手机上打开上面的网址也行：
        用户名 <code>{{ info.login }}</code>，密码
        <b>{{ info.password_custom ? '是下面单独设置的云盘密码' : '和教学平台的登录密码一样' }}</b>。
      </p>

      <div class="pwd">
        <template v-if="!info.password_custom">
          <div class="sub">单独设置一个云盘密码（设了以后，改教学平台密码不再影响云盘）</div>
          <div class="row">
            <el-input v-model="pwd.password" type="password" show-password placeholder="新的云盘密码，至少 6 位" autocomplete="new-password" />
            <el-input v-model="pwd.confirm" type="password" show-password placeholder="再输一次" autocomplete="new-password" @keyup.enter="setCustom" />
            <el-button :loading="pwd.saving" @click="setCustom">设置</el-button>
          </div>
        </template>
        <template v-else>
          <div class="sub">云盘密码现在是单独设置的。改回和教学平台一致：</div>
          <div class="row">
            <el-input v-model="pwd.current" type="password" show-password placeholder="输入教学平台的登录密码" autocomplete="current-password" @keyup.enter="syncBack" />
            <el-button :loading="pwd.saving" @click="syncBack">改回一致</el-button>
          </div>
          <div class="sub again">或者重新设一个：</div>
          <div class="row">
            <el-input v-model="pwd.password" type="password" show-password placeholder="新的云盘密码" autocomplete="new-password" />
            <el-input v-model="pwd.confirm" type="password" show-password placeholder="再输一次" autocomplete="new-password" />
            <el-button :loading="pwd.saving" @click="setCustom">设置</el-button>
          </div>
        </template>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.cloudcard {
  margin-top: 16px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ch {
  font-weight: 600;
}
.num {
  margin-top: 8px;
  font-size: 13px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.url {
  margin-top: 14px;
}
.over {
  margin-top: 12px;
}
.note {
  margin: 14px 0 0;
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--el-text-color-secondary);
}
.note code {
  font-family: ui-monospace, Consolas, monospace;
  background: var(--el-fill-color-light);
  padding: 1px 5px;
  border-radius: 4px;
}
.pwd {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--el-border-color-light);
}
.sub {
  font-size: 13px;
  margin-bottom: 8px;
}
.sub.again {
  margin-top: 12px;
}
.row {
  display: flex;
  gap: 8px;
}
@media (max-width: 680px) {
  .row {
    flex-direction: column;
  }
}
</style>

<script setup>
/**
 * 账号页顶上的「个人云盘」卡片（2.25.0）：磁盘还剩多少、云盘总容量设多少、已经分出去多少。
 * 给每位老师分多少在下面账号表格的「个人云盘」一列里点。数据由 Users.vue 取回来传进来。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { fmtBytes, usedPct } from '../cloud'

const props = defineProps({ data: { type: Object, default: null } })
const emit = defineEmits(['changed'])

const GB = 1024 ** 3
const totalGb = ref(0)
const saving = ref(false)
const showCred = ref(false)

watch(
  () => props.data?.total_bytes,
  v => (totalGb.value = Math.round(((v || 0) / GB) * 10) / 10),
  { immediate: true }
)

const disk = computed(() => props.data?.disk || null)
const diskMaxGb = computed(() => (disk.value ? Math.floor(disk.value.total / GB) : 1024 * 1024))
const allocPct = computed(() => usedPct(props.data?.allocated_bytes, props.data?.total_bytes))
const usedOfTotal = computed(() => usedPct(props.data?.used_bytes, props.data?.total_bytes))
const diskPct = computed(() => (disk.value ? usedPct(disk.value.used, disk.value.total) : 0))

async function saveTotal() {
  saving.value = true
  try {
    await api.cloudSetTotal(totalGb.value || 0)
    ElMessage.success('云盘总容量已保存')
    emit('changed')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-card v-if="data?.enabled" shadow="never" class="cloud-admin">
    <template #header>
      <div class="head">
        <span>☁ 个人云盘</span>
        <el-tag v-if="data.service_ok" type="success" size="small" effect="plain">云盘服务正常</el-tag>
        <el-tag v-else type="danger" size="small" effect="plain">云盘服务连不上</el-tag>
      </div>
    </template>

    <el-alert v-if="!data.service_ok" type="error" :closable="false" class="tip">
      {{ data.service_error }}。服务器上运行 <code>sudo docker compose up -d</code>，
      再用 <code>sudo docker compose logs openlist</code> 看看原因。
    </el-alert>

    <div class="grid">
      <div class="cell">
        <div class="label">服务器磁盘（{{ data.root_dir_host }} 所在的盘）</div>
        <template v-if="disk">
          <el-progress :percentage="diskPct" :stroke-width="10" :show-text="false"
            :status="diskPct > 90 ? 'exception' : ''" />
          <div class="num">共 {{ fmtBytes(disk.total) }}，已用 {{ fmtBytes(disk.used) }}，剩 <b>{{ fmtBytes(disk.free) }}</b></div>
        </template>
        <div v-else class="num muted">看不到云盘目录（容器里没有挂上）</div>
      </div>

      <div class="cell">
        <div class="label">云盘总容量（全校老师分的空间加起来不能超过它）</div>
        <div class="row">
          <el-input-number v-model="totalGb" :min="0" :max="diskMaxGb" :step="10" :precision="1"
            controls-position="right" size="small" />
          <span class="unit">GB</span>
          <el-button size="small" type="primary" :loading="saving" @click="saveTotal">保存</el-button>
        </div>
        <div class="num muted">最多设到磁盘总大小 {{ diskMaxGb }} GB；别设满，给系统和数据库留点地方。</div>
      </div>

      <div class="cell">
        <div class="label">已分配给老师</div>
        <el-progress :percentage="allocPct" :stroke-width="10" :show-text="false" />
        <div class="num">
          {{ fmtBytes(data.allocated_bytes) }} / {{ fmtBytes(data.total_bytes) }}
          <span class="muted">· 实际已用 {{ fmtBytes(data.used_bytes) }}（{{ usedOfTotal }}%）</span>
        </div>
      </div>
    </div>

    <p class="note">
      在下面表格的「个人云盘」一列给老师分配空间（填 0 是收回，文件留在服务器上不删）。
      分到空间的老师点顶栏「☁ 个人云盘」直接进，不用再登录；也可以直接打开 <code>/cloud/</code>，
      用教学平台的用户名和密码登录。上传时超出分配的空间会被拒绝，用量每 5 分钟统计一次。
      <template v-if="data.openlist_admin">
        <el-button link size="small" type="primary" @click="showCred = !showCred">
          {{ showCred ? '收起' : '云盘后台管理员账号' }}
        </el-button>
        <span v-if="showCred" class="cred">
          用户名 <code>{{ data.openlist_admin.username }}</code>
          密码 <code>{{ data.openlist_admin.password }}</code>
          （只给排查问题用；老师的账号、空间都在这里管，不要在云盘后台里改）
        </span>
      </template>
    </p>
  </el-card>
</template>

<style scoped>
.cloud-admin {
  margin-bottom: 16px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}
.tip {
  margin-bottom: 14px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 22px;
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.num {
  margin-top: 6px;
  font-size: 13px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.unit {
  font-size: 13px;
}
.note {
  margin: 16px 0 0;
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--el-text-color-secondary);
}
.cred code,
.note code {
  font-family: ui-monospace, Consolas, monospace;
  background: var(--el-fill-color-light);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>

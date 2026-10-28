<script setup>
/**
 * 数据回收站（放在「我的账号」里，每位老师和管理员都有）。
 *
 * 删掉的考试、答卷、存档试卷、题目、学生、班级、打字成绩、练习文本、仿真任务、反馈
 * 都先进这里放 7 天：勾上点「还原」原样回来；不管它，7 天后自动从数据库里彻底删掉。
 * 老师只看得到自己删的，管理员看得到所有人删的。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { currentUser } from '../auth'

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const loading = ref(false)
const items = ref([])
const kinds = ref({})
const keepDays = ref(7)
const kind = ref('')
const picked = ref([])
const table = ref()

const shown = computed(() => items.value.filter(i => !kind.value || i.kind === kind.value))
const counts = computed(() => {
  const out = {}
  items.value.forEach(i => (out[i.kind] = (out[i.kind] || 0) + 1))
  return out
})

async function load() {
  loading.value = true
  try {
    const res = await api.recycleList()
    items.value = res.items
    kinds.value = res.kinds
    keepDays.value = res.keep_days
    table.value?.clearSelection()
  } finally {
    loading.value = false
  }
}
onMounted(load)

function when(t) {
  return String(t || '').replace('T', ' ').slice(0, 16)
}

async function restore(rows) {
  const res = await api.recycleRestore(rows.map(r => r.id))
  if (res.failed?.length) {
    await ElMessageBox.alert(res.failed.join('\n\n'), `还原了 ${res.restored} 条，${res.failed.length} 条没还原`, {
      confirmButtonText: '知道了'
    })
  } else {
    ElMessage.success(`已还原 ${res.restored} 条，回到原来的位置了`)
  }
  await load()
}

async function destroy(rows) {
  await ElMessageBox.confirm(
    `彻底删除这 ${rows.length} 条？彻底删除后就再也找不回来了。`,
    '彻底删除',
    { type: 'warning', confirmButtonText: '彻底删除' }
  )
  await api.recycleDestroy(rows.map(r => r.id))
  ElMessage.success('已彻底删除')
  await load()
}

async function clearAll() {
  await ElMessageBox.confirm(
    `清空回收站里全部 ${items.value.length} 条（包括所有老师删的）？清空后就再也找不回来了。`,
    '清空回收站',
    { type: 'warning', confirmButtonText: '清空' }
  )
  await api.recycleClear()
  ElMessage.success('回收站已清空')
  await load()
}
</script>

<template>
  <div v-loading="loading" class="bin">
    <el-alert type="info" :closable="false" class="tip">
      删掉的考试、答卷、存档试卷、题目、学生、班级、打字成绩、练习文本等都先放在这里
      <b>{{ keepDays }} 天</b>：勾选后点「还原」就原样回到原来的位置；不操作的话，
      {{ keepDays }} 天后自动从数据库里永久删除。
      <template v-if="isAdmin">你是管理员，看得到所有老师删的。</template>
      <template v-else>这里只有你自己删的。</template>
    </el-alert>

    <div class="bar">
      <el-radio-group v-model="kind" size="small">
        <el-radio-button value="">全部（{{ items.length }}）</el-radio-button>
        <el-radio-button v-for="(n, k) in counts" :key="k" :value="k">
          {{ kinds[k] || k }}（{{ n }}）
        </el-radio-button>
      </el-radio-group>
      <span class="grow" />
      <el-button size="small" type="primary" :disabled="!picked.length" @click="restore(picked)">
        还原勾选（{{ picked.length }}）
      </el-button>
      <el-button size="small" type="danger" plain :disabled="!picked.length" @click="destroy(picked)">
        彻底删除
      </el-button>
      <el-button v-if="isAdmin" size="small" type="danger" link :disabled="!items.length" @click="clearAll">
        清空回收站
      </el-button>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-table
      ref="table"
      :data="shown"
      size="small"
      border
      empty-text="回收站是空的"
      @selection-change="v => (picked = v)"
    >
      <el-table-column type="selection" width="38" />
      <el-table-column label="类别" width="90">
        <template #default="{ row }"><el-tag size="small" effect="plain">{{ row.kind_name }}</el-tag></template>
      </el-table-column>
      <el-table-column label="内容" min-width="240">
        <template #default="{ row }">
          <div class="ttl">{{ row.title }}</div>
          <div v-if="row.detail" class="sub">{{ row.detail }}</div>
        </template>
      </el-table-column>
      <el-table-column v-if="isAdmin" prop="deleted_by_name" label="删除人" width="96" />
      <el-table-column label="删除时间" width="136">
        <template #default="{ row }">{{ when(row.deleted_at) }}</template>
      </el-table-column>
      <el-table-column label="剩余" width="80">
        <template #default="{ row }">
          <span :class="{ soon: row.days_left <= 1 }">{{ row.days_left }} 天</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="128" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="restore([row])">还原</el-button>
          <el-button link type="danger" size="small" @click="destroy([row])">彻底删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.tip {
  margin-bottom: 12px;
}
.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.grow {
  flex: 1;
}
.ttl {
  font-weight: 500;
}
.sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.soon {
  color: var(--el-color-danger);
  font-weight: 600;
}
</style>

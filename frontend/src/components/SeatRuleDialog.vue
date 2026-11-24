<script setup>
/**
 * 认座设置（2.26.0）：签到时怎么认出「这台电脑是哪个座位」，认出来的就自动签上，不让学生自己选。
 *
 * - 认座规则：电脑名最后一段就是座号 / 电脑名末尾数字 / 内网 IP 末段 / 不认（学生自己选）。
 *   换规则先看下面的预览（最近 2 小时登录过学生端的电脑按这个规则各对哪个座号），确认了再保存；
 * - 绑座模式：电脑名、IP 都对不上座号的机房用。开着的时候，每台学生机登录后弹框选一次座号，存在服务器上；
 * - 两样都认不出来的电脑，签到时照旧从下拉框选。
 *
 * 全校一份，管理员能改，别的老师只能看。规则见 backend/app/services/checkin.py。
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { isAdmin } from '../auth'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  cls: { type: Object, default: null }
})
const emit = defineEmits(['update:modelValue'])
const show = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const admin = computed(() => isAdmin())
const saved = ref(null)            // 服务器上现在的规则
const mode = ref('pick')
const offset = ref(0)
const modes = ref({})
const pv = ref(null)               // 预览
const loading = ref(false)
const saving = ref(false)
const binds = ref([])
const bindLeft = ref(0)
const bindMinutes = ref(15)
let timer = null

const numeric = computed(() => mode.value === 'host_num' || mode.value === 'ip_num')
const changed = computed(() => saved.value && (saved.value.mode !== mode.value || saved.value.offset !== offset.value))
const HOW = { auto: '规则', bind: '绑定' }
const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

function applyRule(r) {
  saved.value = { mode: r.mode, offset: r.offset }
  modes.value = r.modes || modes.value
  bindLeft.value = r.bind_remaining || 0
  clearInterval(timer)
  if (bindLeft.value > 0) {
    timer = setInterval(() => {
      bindLeft.value = Math.max(0, bindLeft.value - 1)
      if (bindLeft.value % 10 === 0) loadBinds()
      if (!bindLeft.value) clearInterval(timer)
    }, 1000)
  }
}

async function load() {
  loading.value = true
  try {
    const r = await api.seatRule()
    applyRule(r)
    mode.value = r.mode
    offset.value = r.offset
    await Promise.all([preview(), loadBinds()])
  } finally {
    loading.value = false
  }
}

async function preview() {
  try {
    pv.value = await api.seatRulePreview({ mode: mode.value, offset: offset.value || 0, class_id: props.cls?.id || 0 })
  } catch {
    pv.value = null
  }
}

async function loadBinds() {
  try {
    binds.value = await api.seatBindings()
  } catch {
    binds.value = []
  }
}

async function save() {
  if (pv.value?.clash?.length) {
    await ElMessageBox.confirm(
      `预览里 ${pv.value.clash.join('、')} 对上了不止一台电脑，签到时后登录的那台会签不上。仍然保存？`,
      '有重复的座号',
      { type: 'warning', confirmButtonText: '仍然保存' }
    )
  }
  saving.value = true
  try {
    applyRule(await api.seatRuleSave(mode.value, offset.value || 0))
    ElMessage.success('认座规则已保存，下次签到起生效')
  } finally {
    saving.value = false
  }
}

async function setBind(minutes) {
  applyRule(await api.seatBindMode(minutes))
  ElMessage.success(minutes ? `绑座模式已打开 ${minutes} 分钟：学生机登录后会弹框选这台电脑的座号` : '绑座模式已关掉')
  loadBinds()
}

async function unbind(b) {
  const all = b === 'all'
  await ElMessageBox.confirm(all ? '删掉全部绑座？' : `删掉 ${b.seat}（${b.host || '没报电脑名'}）的绑定？`, '删除绑座', { type: 'warning' })
  await api.seatBindingDelete(all ? 'all' : b.device)
  loadBinds()
  preview()
}

let debounce = null
watch([mode, offset], () => {
  clearTimeout(debounce)
  debounce = setTimeout(preview, 300)
})
watch(show, v => v && load(), { immediate: true })
onUnmounted(() => {
  clearInterval(timer)
  clearTimeout(debounce)
})
</script>

<template>
  <el-dialog v-model="show" title="认座设置：签到时怎么认出电脑是哪个座位" width="min(96vw, 820px)" append-to-body>
    <div v-loading="loading">
      <p class="tip">
        认得出座号的电脑，学生登录后<b>直接签到那个座位</b>，不用也不能自己选，防止乱签占别人的座号。
        自己选的座号被真正的那台电脑认领时会让出来。认不出来的电脑照旧从下拉框选。
        <template v-if="!admin">全校一份，只有管理员能改。</template>
      </p>

      <h5>① 认座规则</h5>
      <el-radio-group v-model="mode" :disabled="!admin" class="modes">
        <el-radio v-for="(label, key) in modes" :key="key" :value="key">{{ label }}</el-radio>
      </el-radio-group>
      <div v-if="numeric" class="off">
        偏移
        <el-input-number v-model="offset" :min="0" :max="65535" size="small" :disabled="!admin" />
        <span class="muted">数字减去偏移就是第几个座位；座位按 A1、A2…A15、B1… 的顺序数。</span>
      </div>

      <div class="pvhead">
        <span>
          预览（{{ pv?.sheet || '' }}的座号，最近 2 小时登录过学生端的电脑）：
          <template v-if="pv">认出 <b>{{ pv.matched }}</b> / {{ pv.machines.length }} 台</template>
          <b v-if="pv?.clash?.length" class="bad">，{{ pv.clash.join('、') }} 对上了不止一台</b>
        </span>
        <el-button size="small" link type="primary" @click="preview">刷新</el-button>
      </div>
      <el-table :data="pv?.machines || []" size="small" max-height="260" empty-text="最近没有学生端登录过（4.16.0 起的学生端才报电脑名和 IP）">
        <el-table-column prop="host" label="电脑名" min-width="150">
          <template #default="{ row }">{{ row.host || '（没报）' }}</template>
        </el-table-column>
        <el-table-column prop="lan_ip" label="内网 IP" width="120" />
        <el-table-column prop="student" label="最近登录" width="100" />
        <el-table-column label="→ 座号" width="150">
          <template #default="{ row }">
            <b v-if="row.seat" :class="{ bad: row.clash }">{{ row.seat }}</b>
            <small v-if="row.seat" class="muted">（{{ HOW[row.how] }}）</small>
            <span v-else class="muted">认不出 · 下拉框选</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="admin" class="actions">
        <el-button type="primary" size="small" :disabled="!changed" :loading="saving" @click="save">
          保存认座规则
        </el-button>
        <span v-if="changed" class="muted">还没保存，上面是按新规则算的预览</span>
      </div>

      <h5>② 绑座模式 <small class="muted">（电脑名、IP 都和座号对不上的机房用，绑定优先于规则）</small></h5>
      <div class="bind">
        <template v-if="bindLeft > 0">
          <el-tag type="warning" effect="dark">绑座中 {{ fmt(bindLeft) }}</el-tag>
          <span class="muted">学生机登录后会弹框选「这台电脑的座号」，每台选一次就行。</span>
          <el-button v-if="admin" size="small" @click="setBind(0)">关掉</el-button>
        </template>
        <template v-else-if="admin">
          <el-select v-model="bindMinutes" size="small" style="width: 96px">
            <el-option v-for="m in [5, 10, 15, 30, 60]" :key="m" :label="`${m} 分钟`" :value="m" />
          </el-select>
          <el-button size="small" type="warning" plain @click="setBind(bindMinutes)">打开绑座模式</el-button>
        </template>
        <span v-else class="muted">没开</span>
      </div>
      <el-table :data="binds" size="small" max-height="220" empty-text="还没有电脑绑过座号">
        <el-table-column prop="seat" label="座号" width="70" />
        <el-table-column prop="host" label="电脑名" min-width="140" />
        <el-table-column prop="lan_ip" label="内网 IP" width="120" />
        <el-table-column prop="bound_by" label="绑的时候登录的" width="110" />
        <el-table-column v-if="admin" width="70">
          <template #header>
            <el-button v-if="binds.length" size="small" link type="danger" @click="unbind('all')">全删</el-button>
          </template>
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="unbind(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<style scoped>
.tip {
  margin: 0 0 12px;
  line-height: 1.7;
  font-size: 13px;
}
h5 {
  margin: 14px 0 8px;
}
.modes {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.off {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0 0 24px;
  font-size: 13px;
}
.pvhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 10px 0 4px;
  font-size: 13px;
}
.actions,
.bind {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.bad {
  color: var(--el-color-danger);
}
</style>

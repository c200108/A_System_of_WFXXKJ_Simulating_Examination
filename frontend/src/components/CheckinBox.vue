<script setup>
/**
 * 班级详情顶上的「课堂签到」（2.24.0）：选时长（1～10 分钟）发起，签到中显示倒计时和进度，
 * 点「签到详情」看未签到名单、缺勤人数、已登录学生和座号。
 *
 * 实时刷新用**带版本号的短轮询**：签到进行中每 2 秒问一次 /checkins/current，版本号（已签人数 + 最后一条）
 * 变了才通知外面重读签到那张表；签到一结束就停，不再问。选它而不是 SSE / WebSocket：
 * 后端是多进程 + nginx（局域网版直连），长连接要额外的消息中转和代理配置，机房网络一抖就断；
 * 2 秒一问的请求很小（一个班几十行），一节课只问几分钟，稳定、好排查、不用改部署。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const props = defineProps({
  cls: { type: Object, required: true },
  canEdit: { type: Boolean, default: false }
})
const emit = defineEmits(['started', 'progress'])

const minutes = ref(3)
const view = ref(null)          // 最近一次签到的进度
const starting = ref(false)
const showDetail = ref(false)
const left = ref(0)
let pollTimer = null
let tickTimer = null
let version = ''

const active = computed(() => !!view.value?.active && left.value > 0)
const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

function apply(v) {
  const before = version
  view.value = v
  if (!v) return
  left.value = v.remaining
  version = `${v.id}:${v.version}`
  if (version !== before) emit('progress', v)
  clearInterval(tickTimer)
  if (v.active) {
    tickTimer = setInterval(() => {
      left.value = Math.max(0, left.value - 1)
      if (left.value <= 0) clearInterval(tickTimer)
    }, 1000)
  }
}

async function poll() {
  try {
    const { checkin } = await api.checkinCurrent(props.cls.id)
    apply(checkin)
  } catch {
    // 网络抖一下：下一轮再问
  }
  schedule()
}

function schedule() {
  clearTimeout(pollTimer)
  // 进行中每 2 秒问一次；结束了就不问了（倒计时到 0 时再问最后一次，拿最终结果）
  if (view.value?.active) pollTimer = setTimeout(poll, left.value > 0 ? 2000 : 800)
}

async function start() {
  starting.value = true
  try {
    const v = await api.checkinStart(props.cls.id, minutes.value)
    apply(v)
    emit('started', v)
    schedule()
    ElMessage.success(`已发起签到（${minutes.value} 分钟），本班登录着的学生端会弹出签到框`)
  } finally {
    starting.value = false
  }
}

async function stop() {
  await ElMessageBox.confirm('现在就结束签到？还没签的学生就签不了了。', '结束签到', { type: 'warning' })
  apply(await api.checkinStop(props.cls.id, view.value.id))
  clearTimeout(pollTimer)
}

onMounted(poll)
onUnmounted(() => {
  clearTimeout(pollTimer)
  clearInterval(tickTimer)
})
</script>

<template>
  <div class="ckbox">
    <template v-if="active">
      <el-tag type="success" effect="dark" class="live">签到中 {{ fmt(left) }}</el-tag>
      <span class="stat">
        已签 <b>{{ view.signed_count }}</b> / {{ view.total }}　缺勤 <b class="bad">{{ view.absent }}</b>
      </span>
      <el-button size="small" @click="showDetail = true">签到详情</el-button>
      <el-button v-if="canEdit" size="small" type="danger" plain @click="stop">结束签到</el-button>
    </template>
    <template v-else>
      <template v-if="canEdit">
        <el-select v-model="minutes" size="small" style="width: 92px">
          <el-option v-for="m in 10" :key="m" :label="`${m} 分钟`" :value="m" />
        </el-select>
        <el-button size="small" type="primary" :loading="starting" @click="start">发起签到</el-button>
      </template>
      <el-button v-if="view" size="small" link type="primary" @click="showDetail = true">
        上次签到（{{ view.tab_name || '已删表' }}）：已签 {{ view.signed_count }} / {{ view.total }}
      </el-button>
    </template>

    <el-dialog v-model="showDetail" :title="`签到详情 · ${cls.display}`" width="min(94vw, 720px)" append-to-body>
      <template v-if="view">
        <p class="sum">
          {{ view.started_by }} 发起于 {{ String(view.started_at).replace('T', ' ').slice(0, 16) }}，
          <template v-if="active">还剩 <b>{{ fmt(left) }}</b></template>
          <template v-else>已结束</template>
          。应到 <b>{{ view.total }}</b> 人，已签 <b>{{ view.signed_count }}</b> 人，缺勤 <b class="bad">{{ view.absent }}</b> 人。
          签到结果填在工作表「{{ view.tab_name }}」里。
        </p>
        <div class="cols">
          <section>
            <h5>未签到（{{ view.unsigned.length }}）</h5>
            <p v-if="!view.unsigned.length" class="muted">全部签到了</p>
            <span v-for="u in view.unsigned" :key="u.student_id" class="who" :class="{ on: u.online }">
              {{ u.name }}<small v-if="u.online">（已登录）</small>
            </span>
          </section>
          <section>
            <h5>已签到（{{ view.signed.length }}）</h5>
            <el-table :data="view.signed" size="small" max-height="320">
              <el-table-column prop="seat" label="座号" width="70" />
              <el-table-column prop="name" label="姓名" />
              <el-table-column label="时间" width="90">
                <template #default="{ row }">{{ String(row.at).replace('T', ' ').slice(11, 19) }}</template>
              </el-table-column>
            </el-table>
          </section>
        </div>
        <h5>已登录的学生（{{ view.online.length }}）</h5>
        <p class="muted small">学生端登录着（最近 20 秒内有响应）的同学和他选的座号；没选的还没签到。</p>
        <span v-for="o in view.online" :key="o.student_id" class="who on">
          {{ o.name }}<small>{{ o.seat ? ` · ${o.seat}` : ' · 未签' }}</small>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ckbox {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.live {
  font-variant-numeric: tabular-nums;
}
.stat {
  font-size: 13px;
}
.bad {
  color: var(--el-color-danger);
}
.sum {
  margin: 0 0 12px;
  line-height: 1.7;
}
.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 12px;
}
@media (max-width: 640px) {
  .cols {
    grid-template-columns: 1fr;
  }
}
h5 {
  margin: 0 0 8px;
}
.who {
  display: inline-block;
  margin: 0 6px 6px 0;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  font-size: 13px;
}
.who.on {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success-dark-2);
}
.muted {
  color: var(--el-text-color-secondary);
}
.small {
  font-size: 12px;
  margin: 0 0 6px;
}
</style>

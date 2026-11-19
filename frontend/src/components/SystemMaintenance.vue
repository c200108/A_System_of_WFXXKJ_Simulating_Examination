<script setup>
/**
 * 系统管理员「我的账号」里的「数据备份与系统更新」（2.18.0）。
 *
 * 只有部署时建的系统管理员看得到（user.is_root），接口那边也只认这一个账号。
 *
 * - 导出数据：后端现打一个 exam-data 压缩包直接下载；
 * - 导入数据：传 exam-data 压缩包 → 后端体检 + 试算 → 服务器上的主机助手跑 data-import.sh、重建容器；
 * - 一键更新：从 GitHub 下载 main 压缩包，或者自己传一个，主机助手照
 *   「unzip -p … update-from-zip.sh > u.sh → bash u.sh <压缩包>」升级，文件名叫什么都行。
 *   从 GitHub 更新时主机助手**先比版本**（提交号 / 更新日志版本号），已经是最新就不下载。
 * - 下载学生最新客户端：浏览器直接问 GitHub 最新正式版（Latest）的附件清单，点哪个下哪个。
 *
 * 导入、更新期间后端会重启，问进度会断一会儿 —— 那是正常的，接着问，不弹错。
 */
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, download } from '../api'

const status = ref(null)
const loading = ref(false)
const exporting = ref(false)
const uploading = ref(0)          // 上传进度 0~100，0 = 没在传
const importFile = ref(null)
const updateFile = ref(null)
const dryRun = ref('')

const job = ref(null)             // 正在看的那个任务
const offline = ref(0)            // 连着问不通几次了（服务重启中）
const logBox = ref()
let timer = null

const agentOk = computed(() => status.value?.agent?.installed)
const busy = computed(() => job.value && ['queued', 'running'].includes(job.value.status))

const STATUS = {
  queued: ['等待服务器接单', 'info'],
  running: ['正在执行', 'warning'],
  ok: ['完成', 'success'],
  failed: ['没做成', 'danger'],
  lost: ['已结束（没有结果）', 'info']
}

async function refresh() {
  loading.value = true
  try {
    status.value = await api.systemStatus()
    const cur = status.value.busy
    if (cur) watchJob(cur)
    else if (!job.value && status.value.recent?.length) {
      // 刷新页面后把上一次的结果和日志带出来（升级完刷新，正好看到升级日志）
      job.value = status.value.recent[0]
      poll()
    }
  } finally {
    loading.value = false
  }
}

function stopPolling() {
  clearTimeout(timer)
  timer = null
}

function watchJob(j) {
  job.value = j
  offline.value = 0
  stopPolling()
  poll()
}

async function poll() {
  if (!job.value) return
  try {
    const got = await api.systemJob(job.value.id)
    const was = job.value.status
    job.value = got
    offline.value = 0
    await nextTick()
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
    if (['ok', 'failed', 'lost'].includes(got.status)) {
      if (['queued', 'running'].includes(was)) finished(got)
      return
    }
  } catch (err) {
    // 升级、重建容器时后端在重启：问不通是正常的，接着问
    if (err?.response?.status === 404) return
    offline.value += 1
  }
  timer = setTimeout(poll, 3000)
}

function finished(j) {
  status.value && (status.value.busy = null)
  if (j.status === 'ok') {
    if ((j.message || '').startsWith('已经是最新版本')) {
      ElMessageBox.alert(`${j.message}。服务器上的代码和 GitHub 上的一致，没有下载任何东西。`, '已经是最新版本', {
        type: 'success'
      })
    } else if (j.action === 'import') {
      ElMessageBox.alert('数据已导入，容器已重建。刷新页面后核对一下题目数、学生数。', '导入完成', { type: 'success' })
    } else {
      ElMessageBox.alert('已经升级到最新版本，数据库和上传文件原样保留。点确定刷新页面，加载新版网页。', '更新完成', {
        type: 'success',
        callback: () => window.location.reload()
      })
    }
  } else {
    ElMessage.error(`${j.label}没做成，看下面日志最后几行`)
  }
}

async function askPassword(title, warn) {
  const { value } = await ElMessageBox.prompt(
    `${warn}<br><br>请输入你的登录密码确认：`,
    title,
    {
      dangerouslyUseHTMLString: true,
      inputType: 'password',
      inputPlaceholder: '登录密码',
      confirmButtonText: '确认执行',
      cancelButtonText: '取消',
      type: 'warning',
      inputValidator: v => (v ? true : '要输入密码')
    }
  )
  return value
}

// ---------------------------------------------------------------- 导出
function stamp() {
  const d = new Date()
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

async function doExport() {
  exporting.value = true
  try {
    await download(api.exportBackup(), `exam-data-${stamp()}.zip`)
    ElMessage.success('数据已导出，压缩包里是完整的 exam-data（数据表、配图、配置）')
  } finally {
    exporting.value = false
  }
}

// ---------------------------------------------------------------- 导入 / 更新
// 用原生的文件框：只是选文件，上传自己发（要带密码、要显示进度）
const importInput = ref()
const updateInput = ref()
function pickImport(e) {
  importFile.value = e.target.files?.[0] || null
  e.target.value = ''          // 同一个文件再选一次也能触发
}
function pickUpdate(e) {
  updateFile.value = e.target.files?.[0] || null
  e.target.value = ''
}

function progress(e) {
  if (e.total) uploading.value = Math.max(1, Math.round((e.loaded / e.total) * 100))
}

async function doImport() {
  if (!importFile.value) return ElMessage.warning('先选一个 exam-data 压缩包')
  let pw
  try {
    pw = await askPassword(
      '导入数据并重建容器',
      `用 <b>${importFile.value.name}</b> 里的数据<b>覆盖</b>本机数据库。<br>` +
        '导入前会自动把现有数据存一份「回滚点」；.env、口令、表结构都不动。<br>' +
        '导完会重建容器，<b>期间网站会有一段时间打不开</b>，请避开考试时段。'
    )
  } catch {
    return
  }
  uploading.value = 1
  dryRun.value = ''
  try {
    const got = await api.importBackup(importFile.value, pw, progress)
    dryRun.value = got.dry_run || ''
    importFile.value = null
    ElMessage.success('体检通过，已交给服务器执行')
    watchJob(got)
  } finally {
    uploading.value = 0
  }
}

async function doUpdateGithub() {
  let pw
  try {
    pw = await askPassword(
      '一键更新（从 GitHub 下载）',
      '服务器会从 GitHub 下载项目最新的 main 压缩包，然后运行压缩包里的升级脚本：<br>' +
        '先备份，再构建新版本（这期间网站照常能用），最后切换 —— <b>切换时网页会有十几秒打不开</b>。<br>' +
        '题库、成绩、账号、上传文件、.env、config.yaml 都原样保留。'
    )
  } catch {
    return
  }
  watchJob(await api.updateFromGithub(pw))
}

async function doUpdateZip() {
  if (!updateFile.value) return ElMessage.warning('先选项目的 main 压缩包')
  let pw
  try {
    pw = await askPassword(
      '上传压缩包更新',
      `用 <b>${updateFile.value.name}</b> 升级（GitHub 仓库页 Code → Download ZIP 下的那个，不用解压）。<br>` +
        '先备份、再构建、最后切换 —— <b>切换时网页会有十几秒打不开</b>。数据原样保留。'
    )
  } catch {
    return
  }
  uploading.value = 1
  try {
    const got = await api.updateFromZip(updateFile.value, pw, progress)
    updateFile.value = null
    watchJob(got)
  } finally {
    uploading.value = 0
  }
}

// ---------------------------------------------------------------- 学生客户端
// 2.24.0 起由本网站导出，自动带上本网站地址（原来直接下 GitHub 附件，里面烤的是开发者服务器的地址）。
// 两种方式：改文件名（…@地址.exe，老版 exe 也认）、写进 exe（文件名不变，4.15.0 起的 exe 才行）
const RELEASES = 'https://github.com/c200108/A_System_of_WFXXKJ_Simulating_Examination/releases'
const clientDlg = ref(false)
const clientLoading = ref(false)
const clientErr = ref('')
const clientCat = ref(null)
const clientAddr = ref(window.location.origin)
const clientBusy = ref('')
const isLocalhost = computed(() => /\/\/(localhost|127\.|\[::1\])/i.test(clientAddr.value))

const clientItems = computed(() =>
  (clientCat.value?.items || []).map(a => ({
    ...a,
    mb: (a.size / 1024 / 1024).toFixed(1) + ' MB',
    win7: /win32-runtime|32位-内置运行库/i.test(a.name)
  }))
)

async function openClients() {
  clientDlg.value = true
  if (clientCat.value) return
  clientLoading.value = true
  clientErr.value = ''
  try {
    clientCat.value = await api.systemClients()
    clientErr.value = clientCat.value.error || ''
  } catch {
    clientErr.value = '服务器没答上来'
  } finally {
    clientLoading.value = false
  }
}

function hostPart(addr) {
  return addr.replace(/^https?:\/\//i, '').replace(/\/+$/, '').replace(':', '_')
}

async function exportClient(a, how) {
  const addr = clientAddr.value.trim().replace(/\/+$/, '')
  if (!addr) return ElMessage.warning('先填学生要连的地址')
  clientBusy.value = a.name + how
  try {
    const name = how === 'name' ? `${a.name.replace(/(@[^@]*)?\.exe$/i, '')}@${hostPart(addr)}.exe` : a.name
    await download(api.systemClientExport(a.name, how, addr), name)
  } finally {
    clientBusy.value = ''
  }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.info(text)
  }
}

onMounted(refresh)
onUnmounted(stopPolling)
</script>

<template>
  <div class="sysm" v-loading="loading">
    <el-alert v-if="status && !agentOk" type="warning" :closable="false" show-icon class="agent">
      <template #title>服务器上还没装「主机助手」，导入数据和一键更新暂时用不了（导出数据不受影响）</template>
      <p>
        在服务器的项目目录里运行一次下面这条（以后每次升级会自动装好）：
        <code>sudo bash scripts/host-agent-install.sh</code>
        <el-button link type="primary" @click="copy('sudo bash scripts/host-agent-install.sh')">复制</el-button>
      </p>
    </el-alert>
    <p v-else-if="status" class="agent-ok">
      ✓ 服务器主机助手已就绪<span v-if="status.agent.version">（{{ status.agent.version }} 装的）</span>
    </p>

    <div class="cols">
      <!-- 数据备份 -->
      <section class="box">
        <h4>数据备份</h4>
        <div class="row">
          <div class="what">
            <b>导出数据</b>
            <span>全部数据表 + 题目配图 + 平台配置，打成一个 exam-data 压缩包下载（不含任何口令）。</span>
          </div>
          <el-button type="primary" :loading="exporting" @click="doExport">导出数据</el-button>
        </div>
        <div class="row col">
          <div class="what">
            <b>导入数据</b>
            <span>
              上传导出得到的 exam-data 压缩包，先体检试算，通过后覆盖本机数据并<b>重建容器</b>。
              期间网站可能有一段时间打不开。
            </span>
          </div>
          <div class="pickline">
            <input ref="importInput" type="file" accept=".zip" hidden @change="pickImport" />
            <el-button :disabled="busy || !!uploading" @click="importInput.click()">选择 exam-data 压缩包</el-button>
            <span class="fname">{{ importFile?.name || '未选择' }}</span>
            <el-button
              type="danger"
              plain
              :disabled="!agentOk || busy || !importFile || !!uploading"
              @click="doImport"
            >导入并重建容器</el-button>
          </div>
        </div>
      </section>

      <!-- 一键更新 -->
      <section class="box">
        <h4>教师端一键更新</h4>
        <div class="row">
          <div class="what">
            <b>途径一：从 GitHub 自动下载</b>
            <span>
              先和 GitHub 上的比版本，已经是最新就不下载；不是最新才下载 main 压缩包升级，数据无损。
              <template v-if="status?.version">
                本机现在是服务端 <b>{{ status.version }}</b><template v-if="status.commit">（提交 {{ status.commit.slice(0, 7) }}）</template>。
              </template>
            </span>
          </div>
          <el-button type="primary" :disabled="!agentOk || busy || !!uploading" @click="doUpdateGithub">
            一键更新
          </el-button>
        </div>
        <div class="row">
          <div class="what">
            <b>下载学生客户端</b>
            <span>从本网站导出学生端 exe，自动带上本网站地址（改文件名或写进 exe），发到学生机上双击就能连。</span>
          </div>
          <el-button @click="openClients">下载学生客户端</el-button>
        </div>
        <div class="row col">
          <div class="what">
            <b>途径二：上传 main 压缩包</b>
            <span>服务器连不上 GitHub 时用：在自己电脑上下载 main 压缩包（文件名随意，不用解压）传上来。</span>
          </div>
          <div class="pickline">
            <input ref="updateInput" type="file" accept=".zip" hidden @change="pickUpdate" />
            <el-button :disabled="busy || !!uploading" @click="updateInput.click()">选择 main 压缩包</el-button>
            <span class="fname">{{ updateFile?.name || '未选择' }}</span>
            <el-button
              type="primary"
              plain
              :disabled="!agentOk || busy || !updateFile || !!uploading"
              @click="doUpdateZip"
            >上传并更新</el-button>
          </div>
        </div>
      </section>
    </div>

    <el-progress v-if="uploading" :percentage="uploading" :stroke-width="14" class="up">
      <span>上传中 {{ uploading }}%</span>
    </el-progress>

    <!-- 任务进度 -->
    <div v-if="job" class="job">
      <div class="jhead">
        <b>{{ job.label }}</b>
        <el-tag :type="STATUS[job.status]?.[1] || 'info'" size="small" effect="light">
          {{ STATUS[job.status]?.[0] || job.status }}
        </el-tag>
        <span class="muted">
          {{ job.file ? job.file + ' · ' : '' }}{{ job.created_at }}
          <template v-if="job.finished_at"> → {{ job.finished_at }}</template>
        </span>
      </div>
      <el-alert v-if="busy && offline >= 2" type="info" :closable="false" show-icon class="restart">
        服务正在重启（升级、重建容器时网站会有一会儿打不开），稍等，连上后自动接着显示进度……
      </el-alert>
      <el-alert
        v-else-if="job.status === 'queued' && agentOk"
        type="info"
        :closable="false"
        class="restart"
      >已交给服务器，几秒内开始执行。</el-alert>
      <details v-if="dryRun" class="dry">
        <summary>导入前的试算报告</summary>
        <pre>{{ dryRun }}</pre>
      </details>
      <pre v-if="job.log" ref="logBox" class="log">{{ job.log }}</pre>
    </div>

    <el-dialog v-model="clientDlg" title="下载学生客户端" width="680px" append-to-body>
      <div v-loading="clientLoading" class="clients">
        <p class="muted tip">
          exe 由本网站导出，学生打开就连下面这个地址（就是你现在打开网站用的地址）。
          学生机要是用别的地址访问本网站（比如内网 IP），在这里改成那个地址再导出。
        </p>
        <el-input v-model="clientAddr" class="caddr">
          <template #prepend>学生连的地址</template>
        </el-input>
        <el-alert
          v-if="isLocalhost"
          type="warning"
          :closable="false"
          show-icon
          title="你是在服务器本机用 localhost 打开的，学生机连不上这个地址，请改成服务器的 IP 或域名"
        />
        <el-alert v-if="clientErr" type="warning" :closable="false" show-icon>
          <template #title>{{ clientErr }}</template>
          也可以打开 <a :href="RELEASES + '/latest'" target="_blank" rel="noopener">GitHub 发布页</a> 下载原版 exe，
          再自己把文件名改成「原名@地址.exe」（端口前的冒号换成下划线）。
        </el-alert>
        <template v-else-if="clientCat">
          <p class="rel">
            {{ clientCat.source === 'local' ? '本机「发布」文件夹里的 exe' : '最新正式版' }}
            <b v-if="clientCat.version">{{ clientCat.version }}</b>
          </p>
          <p class="muted tip">
            两种导出：<b>改文件名</b>（文件名后面带上地址，哪个版本的 exe 都认，但别人改了名就没了）；
            <b>写进 exe</b>（文件名不变，地址写在 exe 里，4.15.0 起的 exe 才支持）。
            Win7 学生机发标着「Win7 选这个」的 32 位内置运行库版。
          </p>
          <div v-for="a in clientItems" :key="a.name" class="casset">
            <span class="cname">
              {{ a.label || a.name }}<el-tag v-if="a.win7" size="small" type="success" effect="plain">Win7 选这个</el-tag>
              <span class="muted">{{ a.name }} · {{ a.mb }}</span>
            </span>
            <span class="cbtns">
              <el-button size="small" :loading="clientBusy === a.name + 'name'" @click="exportClient(a, 'name')">改文件名</el-button>
              <el-button size="small" type="primary" :loading="clientBusy === a.name + 'slot'" @click="exportClient(a, 'slot')">写进 exe</el-button>
            </span>
          </div>
          <p v-if="!clientItems.length" class="muted">没有找到学生端 exe。</p>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.clients {
  min-height: 120px;
}
.caddr {
  margin: 4px 0 10px;
}
.cbtns {
  flex: none;
  display: flex;
  gap: 6px;
}
.rel {
  margin: 0 0 4px;
}
.tip {
  margin: 0 0 10px;
  font-size: 12.5px;
}
.cgroup h5 {
  margin: 12px 0 6px;
  font-size: 14px;
}
.casset {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  text-decoration: none;
  color: inherit;
}
.casset:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.cname {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 6px;
  min-width: 0;
  font-size: 13.5px;
}
.cname .muted {
  flex-basis: 100%;
}
.casset .muted {
  font-size: 12px;
}
.agent p {
  margin: 6px 0 0;
}
.agent code {
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 4px;
  margin: 0 4px;
}
.agent-ok {
  margin: 0 0 12px;
  color: var(--el-color-success);
  font-size: 13px;
}
.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.box {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px 16px;
}
.box h4 {
  margin: 0 0 6px;
  font-size: 15px;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 0;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.row:first-of-type {
  border-top: 0;
}
.row.col {
  flex-direction: column;
  align-items: stretch;
}
.what > b {
  display: block;
  font-size: 14px;
  margin-bottom: 3px;
}
.what span {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.pickline {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.fname {
  flex: 1;
  min-width: 80px;
  font-size: 12.5px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.up {
  margin-top: 14px;
}
.job {
  margin-top: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 12px 14px;
}
.jhead {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.jhead b {
  font-size: 14.5px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.restart {
  margin-top: 10px;
}
.dry summary {
  cursor: pointer;
  margin-top: 10px;
  font-size: 13px;
}
.log,
.dry pre {
  margin: 10px 0 0;
  max-height: 340px;
  overflow: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.55;
  padding: 10px 12px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-all;
}
@media (max-width: 900px) {
  .cols {
    grid-template-columns: 1fr;
  }
}
</style>

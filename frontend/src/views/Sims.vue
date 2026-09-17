<script setup>
/**
 * 仿真操作题的出题台（教师端）。
 *
 * 出一道题分两步，都是**在仿真器里点出来的**，不用写 JSON：
 *
 *   ① 布置环境 —— 把学生打开时该看到的文件夹 / 文档 / 代码摆好，存为初始环境
 *   ② 做标准答案 —— 从初始环境开始，按题目要求做一遍，
 *      点「生成检查点」，系统把前后差异翻译成一条条检查点，改改措辞和分值就行
 *
 * 指望一线老师手写断言 JSON 是不现实的，出题门槛决定了这套东西最后有没有人用。
 *
 * 存之前建议按一次「试判」：拿当前状态跑一遍检查点，应该是满分。
 * 检查点写错了（比如路径少一层）在这里就能发现，不用等考完了才看见全班 0 分。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import SimHost from '../components/sim/SimHost.vue'

const KINDS = [
  { v: 'win', t: 'Windows 操作', d: 'XP 桌面，二十多种文件类型，新建改名移动删除' },
  { v: 'wps', t: 'WPS 文字', d: '照着 WPS 界面做的排版环境' },
  { v: 'html', t: '网页编程', d: '写 HTML/CSS，服务端解析标签和样式判分' },
  { v: 'ai', t: 'AI 工具', d: '对话界面。不用出检查点，按题干自动判分' }
]
const KIND_NAME = Object.fromEntries(KINDS.map(k => [k.v, k.t]))

const rows = ref([])
const loading = ref(false)

// 编辑中的任务
const edit = ref(null)          // { id, kind, title, env, checks }
const mode = ref('env')         // env 布置环境 / answer 做标准答案
const seed = ref(0)             // 换它让仿真器重建
const work = ref('')            // SimHost 的 v-model（JSON 字符串）
const tried = ref(null)

async function load() {
  loading.value = true
  try {
    rows.value = await api.sims()
  } finally {
    loading.value = false
  }
}
load()

/** SimHost 收上来的是 {state, log} 的字符串，这里只要 state */
const workState = computed(() => {
  try {
    return JSON.parse(work.value || 'null')?.state || null
  } catch {
    return null
  }
})

function restart(nextMode) {
  mode.value = nextMode
  work.value = ''
  tried.value = null
  seed.value++
}

async function openNew(kind) {
  const { env } = await api.simBlank(kind)
  edit.value = { id: null, kind, title: '', env, checks: [] }
  restart('env')
}

async function openEdit(row) {
  const full = await api.simGet(row.id)
  edit.value = { id: full.id, kind: full.kind, title: full.title, env: full.env, checks: full.checks || [] }
  restart('env')
}

// AI 工具题是另一套：题干本身就是要求，学生把要求提交给工具就是得分点，
// 所以既不用布置环境、也不用做标准答案、更不用出检查点 —— 判分时按题干现算。
const isAi = computed(() => edit.value?.kind === 'ai')

function saveEnv() {
  if (!workState.value) return ElMessage.warning('先在下面操作几步，再保存为初始环境')
  edit.value.env = workState.value
  ElMessage.success('初始环境已更新，学生打开时看到的就是这个样子')
  restart('env')
}

async function makeChecks() {
  if (!workState.value) return ElMessage.warning('先按题目要求做一遍，再生成检查点')
  const res = await api.simPropose({
    kind: edit.value.kind,
    env: edit.value.env,
    state: workState.value
  })
  if (!res.count) {
    return ElMessage.warning('没看出你做了什么改动，检查点生成不出来')
  }
  // 追加而不是覆盖：老师可能分几次做（先做文件部分，再做文档部分）
  edit.value.checks = [...edit.value.checks, ...res.checks]
  ElMessage.success(`生成了 ${res.count} 条检查点，改改措辞和分值`)
}

async function tryRun() {
  if (!edit.value.checks.length) return ElMessage.warning('还没有检查点')
  if (!workState.value) return ElMessage.warning('先做一遍再试判')
  if (!edit.value.id) {
    return ElMessage.warning('试判要先保存一次任务（检查点存进库才能跑）')
  }
  tried.value = await api.simTry(edit.value.id, {
    state: workState.value,
    checks: edit.value.checks
  })
}

const totalScore = computed(() =>
  (edit.value?.checks || []).reduce((n, c) => n + (Number(c.score) || 0), 0)
)

async function save() {
  const e = edit.value
  if (!e.title.trim()) return ElMessage.warning('给这道题起个名字')
  if (!isAi.value && !e.checks.length) {
    return ElMessage.warning('至少要有一条检查点，否则学生做什么都是 0 分')
  }
  const body = { kind: e.kind, title: e.title.trim(), env: e.env, checks: e.checks }
  const saved = e.id ? await api.simUpdate(e.id, body) : await api.simCreate(body)
  e.id = saved.id
  await load()
  ElMessage.success('已保存')
}

async function remove(row) {
  await ElMessageBox.confirm(
    row.question_count
      ? `有 ${row.question_count} 道题挂着「${row.title}」。删掉之后那些题不会消失，只是退回「老师人工评阅」。已经考完的成绩不受影响。`
      : `确定删除「${row.title}」吗？`,
    '删除仿真任务',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  )
  await api.simDelete(row.id)
  if (edit.value?.id === row.id) edit.value = null
  await load()
  ElMessage.success('已删除')
}

const simFor = computed(() =>
  edit.value ? { kind: edit.value.kind, title: edit.value.title || '（未命名）', env: edit.value.env } : null
)
</script>

<template>
  <!-- 列表 -->
  <el-card v-if="!edit" shadow="never" v-loading="loading">
    <template #header>
      <div class="head">
        <span>仿真操作题</span>
        <el-dropdown @command="openNew">
          <el-button size="small" type="primary">新建<i class="caret">▾</i></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="k in KINDS" :key="k.v" :command="k.v">
                {{ k.t }}<br /><span class="sub">{{ k.d }}</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>

    <el-alert type="info" :closable="false">
      学生在网页里把操作真做一遍，交卷后<b>按检查点自动判分</b>，每小问一档分，做对几问得几问的分。
      判出来的分会预填到成绩页，<b>老师随时能改</b>。
      建好之后到「题库管理」里把某道操作题挂上它。
    </el-alert>

    <el-empty v-if="!rows.length && !loading" description="还没有仿真任务，点右上角新建" :image-size="80" />

    <el-table v-else :data="rows" size="small" style="margin-top: 12px">
      <el-table-column label="题型" width="120">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ KIND_NAME[row.kind] || row.kind }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="名称" min-width="200" />
      <el-table-column label="检查点" width="90">
        <template #default="{ row }">{{ (row.checks || []).length }} 条</template>
      </el-table-column>
      <el-table-column label="满分" width="80">
        <template #default="{ row }">
          {{ (row.checks || []).reduce((n, c) => n + (Number(c.score) || 0), 0) }} 分
        </template>
      </el-table-column>
      <el-table-column label="被引用" width="90">
        <template #default="{ row }">
          <span :class="{ dim: !row.question_count }">{{ row.question_count }} 道题</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130">
        <template #default="{ row }">
          <el-button link size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <!-- 编辑 -->
  <template v-else>
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>
            <el-button link size="small" @click="edit = null">‹ 返回列表</el-button>
            {{ edit.id ? '编辑' : '新建' }}{{ KIND_NAME[edit.kind] }}仿真题
          </span>
          <el-button size="small" type="primary" @click="save">保存</el-button>
        </div>
      </template>

      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="edit.title" placeholder="如：新建文件夹并改名（win02）" style="max-width: 420px" />
        </el-form-item>
      </el-form>

      <template v-if="isAi">
        <el-form label-width="80px">
          <el-form-item label="工具名称">
            <el-input v-model="edit.env.tool" placeholder="如：通义千问 / 文心一言 / DeepSeek" style="max-width: 300px" />
          </el-form-item>
          <el-form-item label="开场白">
            <el-input v-model="edit.env.greeting" placeholder="学生打开时 AI 说的第一句话" style="max-width: 460px" />
          </el-form-item>
        </el-form>
        <el-alert type="success" :closable="false">
          <b>这类题不用你做标准答案，也不用出检查点。</b>
          学生要做的是把题干里的要求完整地描述给 AI 工具并发送，判分就看两条：提交过提问、
          提问内容覆盖题目要求 —— 判分时按<b>题干</b>现算，所以题干把要求写清楚就行。
          <br />对话里的回复由本地模板生成，不联网调用真实大模型（考试环境不往外发请求）。
        </el-alert>
      </template>

      <div v-if="!isAi" class="steps">
        <button class="step" :class="{ on: mode === 'env' }" @click="restart('env')">
          <b>① 布置环境</b>
          <span>把学生打开时该看到的样子摆好</span>
        </button>
        <button class="step" :class="{ on: mode === 'answer' }" @click="restart('answer')">
          <b>② 做标准答案</b>
          <span>从初始环境开始按要求做一遍，生成检查点</span>
        </button>
      </div>

      <div v-if="!isAi" class="actions">
        <template v-if="mode === 'env'">
          <el-button size="small" type="primary" @click="saveEnv">把当前状态设为初始环境</el-button>
          <span class="tip">改完环境记得重新做一遍标准答案 —— 检查点是按环境算出来的。</span>
        </template>
        <template v-else>
          <el-button size="small" type="primary" @click="makeChecks">生成检查点</el-button>
          <el-button size="small" @click="tryRun">试判一下</el-button>
          <span class="tip">按答案做完应该是满分；什么都不做应该是 0 分。</span>
        </template>
      </div>

      <div v-if="tried" class="tried" :class="{ good: tried.score === tried.full }">
        试判结果：<b>{{ tried.score }} / {{ tried.full }}</b> 分
        <span v-for="r in tried.results" :key="r.no" class="chip" :class="{ no: !r.ok }">
          {{ r.ok ? '✓' : '✕' }} {{ r.desc }}<em v-if="!r.ok">（{{ r.why }}）</em>
        </span>
      </div>
    </el-card>

    <el-card shadow="never" class="stage">
      <SimHost v-if="simFor" :key="seed + mode" v-model="work" :sim="simFor" />
    </el-card>

    <el-card v-if="!isAi" shadow="never">
      <template #header>
        <div class="head">
          <span>检查点（共 {{ edit.checks.length }} 条，满分 {{ totalScore }} 分）</span>
          <el-button size="small" @click="edit.checks = []">全部清空</el-button>
        </div>
      </template>

      <el-empty v-if="!edit.checks.length" :image-size="60"
                description="还没有检查点。切到「② 做标准答案」，做一遍再点「生成检查点」" />

      <div v-for="(c, i) in edit.checks" :key="i" class="chk">
        <span class="no">{{ i + 1 }}</span>
        <el-input v-model="c.desc" size="small" placeholder="这一问要求学生做什么" />
        <el-input-number v-model="c.score" size="small" :min="0" :max="50" controls-position="right"
                         style="width: 96px" />
        <span class="unit">分</span>
        <el-button link size="small" type="danger" @click="edit.checks.splice(i, 1)">删</el-button>
        <code class="rule">{{ JSON.stringify(c.assert) }}</code>
      </div>

      <p v-if="edit.checks.length" class="foot">
        下面那行灰字是这一问实际判分的规则。改描述和分值就够了，规则一般不用动；
        真要调（比如把「等于」改成「包含」），照着 <code>docs/仿真操作题.md</code> 改。
      </p>
    </el-card>
  </template>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.caret { font-style: normal; margin-left: 4px; }
.sub { font-size: 12px; color: var(--el-text-color-secondary); }
.dim { color: var(--el-text-color-secondary); }
.steps { display: flex; gap: 10px; flex-wrap: wrap; margin: 4px 0 12px; }
.step {
  flex: 1 1 240px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  text-align: left;
  padding: 10px 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.step.on { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.step span { font-size: 12px; color: var(--el-text-color-secondary); }
.actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.tip { font-size: 12px; color: var(--el-text-color-secondary); }
.tried {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-color-warning-light-9);
  font-size: 13px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.tried.good { background: var(--el-color-success-light-9); }
.chip {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 1px 9px;
  font-size: 12px;
}
.chip.no { color: var(--el-color-danger); border-color: var(--el-color-danger-light-7); }
.chip em { font-style: normal; opacity: 0.8; }
.stage :deep(.el-card__body) { padding: 12px; }
.chk {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 7px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.chk .no {
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: var(--el-fill-color);
  font-size: 12px;
}
.chk :deep(.el-input) { flex: 1 1 260px; }
.chk .unit { font-size: 12px; color: var(--el-text-color-secondary); }
.chk .rule {
  flex: 1 1 100%;
  padding-left: 30px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}
.foot { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.8; }
</style>

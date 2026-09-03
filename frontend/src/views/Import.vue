<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const result = ref(null)
const logs = ref([])
const uploading = ref(false)

async function loadLogs() {
  logs.value = await api.importLogs()
}
onMounted(loadLogs)

async function doUpload(options) {
  uploading.value = true
  result.value = null
  try {
    result.value = await api.importQuestions(options.file)
    ElMessage.success(`导入成功 ${result.value.success} 题`)
    await loadLogs()
  } finally {
    uploading.value = false
  }
}

// 模板接口要带令牌，所以走 fetch 拿 blob 再触发下载
async function downloadTemplate() {
  const res = await fetch('/api/imports/template', {
    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
  })
  if (!res.ok) return ElMessage.error('模板下载失败')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '题库导入模板.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <el-row :gutter="16">
    <el-col :span="14">
      <el-card shadow="never" class="page-card">
        <template #header>上传补充题库</template>
        <el-upload
          drag
          :http-request="doUpload"
          :show-file-list="false"
          accept=".xlsx,.xlsm,.csv"
          :disabled="uploading"
        >
          <el-icon class="up-icon"><UploadFilled /></el-icon>
          <div class="up-text">把模板文件拖到这里，或者点击选择</div>
          <div class="up-hint">支持 .xlsx 和 .csv；Excel 的多张工作表会一起读取</div>
        </el-upload>

        <div v-if="result" class="result">
          <el-alert
            :title="`扫描 ${result.total} 行：成功 ${result.success} 题，失败 ${result.failed} 行，重复跳过 ${result.skipped} 行`"
            :type="result.failed ? 'warning' : 'success'"
            :closable="false"
          />
          <p class="by-type">
            <span v-for="(v, k) in result.by_type" :key="k" class="tag">{{ k }} {{ v }}</span>
          </p>
          <el-table v-if="result.errors.length" :data="result.errors" size="small" border max-height="280">
            <el-table-column prop="sheet" label="工作表" width="120" />
            <el-table-column prop="row" label="行号" width="80" />
            <el-table-column prop="reason" label="原因" />
          </el-table>
          <el-button type="primary" link @click="$router.push('/bank')">去题库查看新题</el-button>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>导入记录</template>
        <el-table :data="logs" size="small" border>
          <el-table-column prop="created_at" label="时间" width="180">
            <template #default="{ row }">{{ String(row.created_at).replace('T', ' ').slice(0, 19) }}</template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="110" />
          <el-table-column prop="filename" label="文件" show-overflow-tooltip />
          <el-table-column prop="success" label="成功" width="70" />
          <el-table-column prop="failed" label="失败" width="70" />
          <el-table-column prop="skipped" label="重复" width="70" />
        </el-table>
      </el-card>
    </el-col>

    <el-col :span="10">
      <el-card shadow="never">
        <template #header>
          <div class="card-head">
            <span>模板格式</span>
            <el-button type="primary" size="small" @click="downloadTemplate">下载空白模板</el-button>
          </div>
        </template>
        <p class="note">表头必须是这六列，顺序可以不同；<b>题型、题干、答案、知识范围</b> 必填。</p>
        <el-table
          :data="[
            {
              a: '选择题',
              b: '切换活动窗口的快捷键是（ ）。',
              c: 'A.Alt+Tab\nB.Ctrl+C',
              d: 'A',
              e: 'Windows系统操作',
              f: ''
            },
            { a: '判断题', b: '计算机病毒可以自我复制。', c: '', d: '正确', e: '信息安全与网络道德', f: '' }
          ]"
          size="small"
          border
        >
          <el-table-column prop="a" label="题型" width="70" />
          <el-table-column prop="b" label="题干" show-overflow-tooltip />
          <el-table-column prop="c" label="可选项" show-overflow-tooltip />
          <el-table-column prop="d" label="答案" width="60" />
          <el-table-column prop="e" label="知识范围" show-overflow-tooltip />
        </el-table>

        <ul class="note rules">
          <li><b>可选项</b>：一行一个，写成 A.内容 的形式；判断题留空，系统自动补正确/错误。</li>
          <li><b>答案</b>：选择题填 A/B/C/D；判断题填 正确/错误/√/×/对/错 都认。</li>
          <li><b>知识范围</b>：只能填十类之一，写错会在导入结果里逐行提示。</li>
          <li><b>图片</b>：填图片网址或已上传的 /uploads/... 路径。</li>
          <li>题干重复的行会自动跳过，同一份文件重复上传不会产生重复题。</li>
          <li><b>CSV</b> 也能传，表头和上面一样；WPS/Excel 存出来的 GBK 编码能自动识别。</li>
        </ul>
      </el-card>
    </el-col>
  </el-row>
</template>

<style scoped>
.up-icon {
  font-size: 42px;
  color: #c0c4cc;
  margin-top: 26px;
}
.up-text {
  margin-top: 8px;
  color: #606266;
}
.up-hint {
  color: #a8abb2;
  font-size: 12px;
  margin: 4px 0 22px;
}
.result {
  margin-top: 16px;
}
.by-type {
  margin: 10px 0;
}
.tag {
  display: inline-block;
  background: #ecf5ff;
  color: #409eff;
  border-radius: 4px;
  padding: 2px 8px;
  margin-right: 8px;
  font-size: 12px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.note {
  color: #606266;
  font-size: 13px;
  line-height: 1.8;
}
.rules {
  padding-left: 18px;
}
</style>

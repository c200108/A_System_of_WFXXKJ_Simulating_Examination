<script setup>
/**
 * 更新日志（公开可看，教师可添加）。
 *
 * 版式遵循 Keep a Changelog：新版本在前，每版一个入口，
 * 版内按 Added / Changed / Deprecated / Removed / Fixed / Security 分组。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { currentUser } from '../auth'

const versions = ref([])
const types = ref([])
const loading = ref(false)
const dialog = ref(false)

const form = reactive({
  version: '',
  released_on: new Date().toISOString().slice(0, 10),
  change_type: 'Added',
  content: ''
})

// 六种变动类型各给一个颜色，扫一眼就知道这条是加东西还是修 bug
const TYPE_STYLE = {
  Added: { color: 'var(--el-color-success)', bg: 'var(--el-color-success-light-9)', icon: '✚' },
  Changed: { color: 'var(--el-color-primary)', bg: 'var(--el-color-primary-light-9)', icon: '↻' },
  Deprecated: { color: '#b88230', bg: 'var(--el-color-warning-light-9)', icon: '⚠' },
  Removed: { color: 'var(--el-text-color-secondary)', bg: 'var(--el-fill-color)', icon: '−' },
  Fixed: { color: 'var(--el-color-warning)', bg: 'var(--el-color-warning-light-9)', icon: '✔' },
  Security: { color: 'var(--el-color-danger)', bg: 'var(--el-color-danger-light-9)', icon: '🛡' }
}
const styleOf = t => TYPE_STYLE[t] || TYPE_STYLE.Changed

const isTeacher = computed(() => !!currentUser.value)

async function load() {
  loading.value = true
  try {
    versions.value = await api.changelog()
    types.value = await api.changelogTypes()
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openAdd() {
  // 默认沿用最新版本号，改个末位数字即可
  form.version = versions.value[0]?.version || '1.0.0'
  form.released_on = new Date().toISOString().slice(0, 10)
  form.change_type = 'Added'
  form.content = ''
  dialog.value = true
}

async function submit() {
  if (!form.version.trim()) return ElMessage.warning('请填版本号')
  if (!form.content.trim()) return ElMessage.warning('请填更新内容')
  await api.changelogCreate({ ...form })
  dialog.value = false
  await load()
  ElMessage.success('已添加')
}

async function removeItem(item) {
  await ElMessageBox.confirm(`删除这条更新记录？\n\n${item.content}`, '提示', { type: 'warning' })
  await api.changelogDelete(item.id)
  await load()
  ElMessage.success('已删除')
}
</script>

<template>
  <div class="page" v-loading="loading">
    <header class="hd">
      <div>
        <h1>更新日志</h1>
        <p class="sub">
          记录平台每一次改动。遵循
          <a href="https://keepachangelog.com/zh-CN/1.1.0/" target="_blank" rel="noopener">Keep a Changelog</a>
          规范与语义化版本。
        </p>
      </div>
      <el-button v-if="isTeacher" type="primary" @click="openAdd">添加记录</el-button>
    </header>

    <el-empty v-if="!versions.length && !loading" description="还没有更新记录" />

    <section v-for="(v, vi) in versions" :key="v.version" class="ver">
      <div class="rail">
        <span class="dot" :class="{ latest: vi === 0 }" />
        <span v-if="vi < versions.length - 1" class="line" />
      </div>

      <div class="body">
        <div class="vhead">
          <h2>{{ v.version }}</h2>
          <span v-if="vi === 0" class="latest-tag">最新</span>
          <time>{{ v.released_on }}</time>
        </div>

        <div v-for="g in v.groups" :key="g.type" class="grp">
          <div class="gtitle" :style="{ color: styleOf(g.type).color }">
            <span class="gicon" :style="{ background: styleOf(g.type).bg }">
              {{ styleOf(g.type).icon }}
            </span>
            {{ g.label }}
            <span class="gen">{{ g.type }}</span>
          </div>
          <ul>
            <li v-for="it in g.items" :key="it.id">
              <span>{{ it.content }}</span>
              <el-button
                v-if="isTeacher"
                link
                type="danger"
                class="del"
                @click="removeItem(it)"
              >删除</el-button>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <el-dialog v-model="dialog" title="添加更新记录" width="560px">
      <el-form label-width="90px">
        <el-form-item label="版本号">
          <el-input v-model="form.version" placeholder="如 1.4.1" style="width: 180px" />
          <span class="hint">语义化版本：功能变更升次版本号，只修 bug 升修订号</span>
        </el-form-item>
        <el-form-item label="发布日期">
          <el-input v-model="form.released_on" type="date" style="width: 180px" />
        </el-form-item>
        <el-form-item label="变动类型">
          <el-select v-model="form.change_type" style="width: 200px">
            <el-option
              v-for="t in types"
              :key="t.value"
              :label="`${t.label}  ${t.value}`"
              :value="t.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="3"
            placeholder="说清楚改了什么、对使用者意味着什么，而不是罗列改了哪个文件"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="submit">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  max-width: 860px;
  margin: 0 auto;
  padding: 8px 4px 60px;
}
.hd {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 32px;
}
h1 {
  font-size: 26px;
  font-weight: 650;
  letter-spacing: 0.5px;
  margin: 0 0 6px;
}
.sub {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
.sub a {
  color: var(--el-color-primary);
  text-decoration: none;
}

.ver {
  display: flex;
  gap: 18px;
}
.rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 12px;
  flex: none;
  padding-top: 7px;
}
.dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 2px solid var(--el-border-color);
  background: var(--el-bg-color);
  flex: none;
}
.dot.latest {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  box-shadow: 0 0 0 4px var(--el-color-primary-light-9);
}
.line {
  flex: 1;
  width: 2px;
  background: var(--el-border-color-lighter);
  margin: 6px 0 0;
}
.body {
  flex: 1;
  padding-bottom: 34px;
  min-width: 0;
}
.vhead {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}
.vhead h2 {
  font-size: 19px;
  font-weight: 650;
  margin: 0;
  font-family: ui-monospace, Consolas, monospace;
}
.latest-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.vhead time {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, Consolas, monospace;
}

.grp {
  margin-bottom: 16px;
}
.gtitle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 600;
  margin-bottom: 7px;
}
.gicon {
  width: 21px;
  height: 21px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}
.gen {
  font-size: 11px;
  font-weight: 400;
  opacity: 0.55;
  font-family: ui-monospace, Consolas, monospace;
}
.grp ul {
  margin: 0;
  padding-left: 30px;
}
.grp li {
  position: relative;
  font-size: 14px;
  line-height: 1.85;
  color: var(--el-text-color-regular);
  padding-right: 46px;
}
.grp li::marker {
  color: var(--el-text-color-placeholder);
}
.del {
  position: absolute;
  right: 0;
  top: 2px;
  opacity: 0;
  transition: 0.15s;
}
.grp li:hover .del {
  opacity: 1;
}
.hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
@media (max-width: 640px) {
  .hd {
    flex-direction: column;
  }
  .grp li {
    padding-right: 0;
  }
  .del {
    position: static;
    opacity: 1;
  }
}
</style>

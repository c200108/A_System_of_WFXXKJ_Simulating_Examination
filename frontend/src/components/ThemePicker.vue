<script setup>
/**
 * 「数据备份与系统更新」里的「界面主题」（2.22.0）：选一套配色、一档字号，全站所有人都换。
 * 点卡片先在自己这里预览，点「应用到全站」才存到服务器；不存就刷新回原样。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { siteConfig } from '../siteConfig'
import { FONTS, THEMES, applyTheme } from '../theme'

const theme = ref(siteConfig.ui?.theme || 'default')
const font = ref(siteConfig.ui?.font || 'large')
const saving = ref(false)
const changed = computed(() => theme.value !== siteConfig.ui?.theme || font.value !== siteConfig.ui?.font)

function preview() {
  applyTheme(theme.value, font.value)
}
function pick(id) {
  theme.value = id
  preview()
}
function revert() {
  theme.value = siteConfig.ui?.theme || 'default'
  font.value = siteConfig.ui?.font || 'large'
  preview()
}
async function save() {
  saving.value = true
  try {
    siteConfig.ui = await api.uiSave({ theme: theme.value, font: font.value })
    preview()
    ElMessage.success('已应用到全站，其他人刷新页面就是新样式')
  } finally {
    saving.value = false
  }
}

/** 卡片上的小样：主色、底色、文字色、圆角 */
const swatch = t => ({
  '--p': t.primary || '#409eff',
  '--bg': t.light?.['--el-bg-color-page'] || '#f2f3f5',
  '--tx': t.light?.['--el-text-color-primary'] || '#303133',
  '--bd': t.light?.['--el-border-color'] || '#dcdfe6',
  '--r': t.radius || '4px'
})
</script>

<template>
  <section class="tp">
    <div class="thead">
      <b>🎨 界面主题</b>
      <span class="muted">全站共用一套：学生平台、教师后台、手机 APP 内嵌页都跟着换。点一下先在你这里预览。</span>
    </div>

    <div class="grid">
      <button
        v-for="t in THEMES"
        :key="t.id"
        type="button"
        class="card"
        :class="{ on: theme === t.id }"
        :style="swatch(t)"
        @click="pick(t.id)"
      >
        <div class="mock">
          <div class="bar" />
          <div class="body">
            <div class="line w1" />
            <div class="line w2" />
            <div class="row">
              <span class="btn" />
              <span class="tag" />
            </div>
          </div>
        </div>
        <div class="name">
          {{ t.name }}
          <span v-if="t.id === 'default'" class="def">默认</span>
          <span v-if="siteConfig.ui?.theme === t.id" class="cur">在用</span>
        </div>
        <div class="desc">{{ t.desc }}</div>
      </button>
    </div>

    <div class="frow">
      <span>字号</span>
      <el-radio-group v-model="font" size="small" @change="preview">
        <el-radio-button v-for="f in FONTS" :key="f.id" :value="f.id">{{ f.name }}（{{ f.base }}px）</el-radio-button>
      </el-radio-group>
      <div class="flex-1" />
      <el-button v-if="changed" size="small" @click="revert">还原</el-button>
      <el-button type="primary" size="small" :disabled="!changed" :loading="saving" @click="save">应用到全站</el-button>
    </div>
  </section>
</template>

<style scoped>
.tp {
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px dashed var(--el-border-color);
}
.thead {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 12px;
  margin-bottom: 12px;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.card {
  padding: 8px;
  border: 2px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
  text-align: left;
  font: inherit;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.card:hover {
  border-color: var(--p);
}
.card.on {
  border-color: var(--p);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--p) 25%, transparent);
}
.mock {
  height: 64px;
  border-radius: var(--r);
  border: 1px solid var(--bd);
  background: var(--bg);
  overflow: hidden;
}
.bar {
  height: 12px;
  background: var(--p);
}
.body {
  padding: 6px 8px;
}
.line {
  height: 5px;
  margin-bottom: 5px;
  border-radius: 3px;
  background: var(--tx);
  opacity: 0.7;
}
.w1 {
  width: 70%;
}
.w2 {
  width: 45%;
  opacity: 0.35;
}
.row {
  display: flex;
  gap: 6px;
}
.btn {
  width: 32px;
  height: 12px;
  border-radius: var(--r);
  background: var(--p);
}
.tag {
  width: 24px;
  height: 12px;
  border-radius: var(--r);
  background: color-mix(in srgb, var(--p) 18%, #fff);
  border: 1px solid color-mix(in srgb, var(--p) 40%, #fff);
}
.name {
  margin-top: 6px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}
.def,
.cur {
  margin-left: 4px;
  padding: 0 5px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 400;
}
.def {
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
}
.cur {
  background: var(--el-color-success-light-8);
  color: var(--el-color-success);
}
.desc {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
.frow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  font-size: 13px;
}
.flex-1 {
  flex: 1;
}
</style>

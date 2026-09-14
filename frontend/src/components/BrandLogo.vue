<script setup>
/**
 * 校徽。配了 config.yaml 的 site.favicon 就显示那张图，没配就退回文字。
 *
 * 和浏览器标签页图标用的是同一个配置项 —— 换校徽只要换一次，
 * 标签页、学生登录页、侧边栏一起变，不用到处改。
 */
import { computed, ref, watch } from 'vue'
import { siteConfig } from '../siteConfig'

const props = defineProps({
  size: { type: Number, default: 30 },
  /** 没配校徽时显示的字 */
  fallback: { type: String, default: '科' },
  /** 圆角比例，按尺寸算，小图标不至于圆得太夸张 */
  radius: { type: Number, default: 0.3 }
})

// 图片加载失败（路径填错、文件被删）时退回文字，不要留一个破图框
const broken = ref(false)
const configured = computed(() => siteConfig.site?.favicon || '')
watch(configured, () => (broken.value = false))
const src = computed(() => (broken.value ? '' : configured.value))
const style = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  borderRadius: `${Math.round(props.size * props.radius)}px`,
  fontSize: `${Math.round(props.size * 0.5)}px`
}))
</script>

<template>
  <img
    v-if="src"
    :src="src"
    :style="style"
    class="brand-logo img"
    alt="校徽"
    @error="broken = true"
  />
  <span v-else :style="style" class="brand-logo txt">{{ fallback }}</span>
</template>

<style scoped>
.brand-logo {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
}
.brand-logo.img {
  object-fit: contain;
  background: #fff;
}
.brand-logo.txt {
  background: linear-gradient(135deg, #5b7cfa, #3f5bd8);
  color: #fff;
  font-weight: 600;
}
</style>

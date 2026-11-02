<script setup>
/**
 * 题库工作台。题库维护、Excel 导入、仿真操作题、打字练习文本收在一页，摆法和考试工作台一致。
 */
import { defineAsyncComponent } from 'vue'
import PanelGroup from '../components/PanelGroup.vue'

const panels = [
  {
    key: 'bank',
    icon: '📚',
    label: '题库管理',
    desc: '增删改查、配图、导出',
    component: defineAsyncComponent(() => import('./Questions.vue'))
  },
  {
    key: 'import',
    icon: '📥',
    label: '批量导入',
    desc: '下载模板、上传 Excel 导题',
    component: defineAsyncComponent(() => import('./Import.vue'))
  },
  {
    key: 'sims',
    icon: '🖥',
    label: '仿真操作题',
    desc: '学生在网页里真做一遍，自动判分',
    component: defineAsyncComponent(() => import('./Sims.vue'))
  },
  {
    key: 'typing-texts',
    icon: '📖',
    label: '练习文本',
    desc: '打字练习用的中英文段落',
    component: defineAsyncComponent(() => import('./TypingTexts.vue'))
  }
]
</script>

<template>
  <PanelGroup :panels="panels" storage-key="bank-hub" default-key="bank" />
</template>

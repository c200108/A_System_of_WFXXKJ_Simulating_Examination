<script setup>
/**
 * 考试工作台。把考试、打字学情、练习文本三件事收在一页里，
 * 默认都收着，点按钮才展开。
 *
 * 三个功能的代码原封不动 —— 这里只是换了个摆放方式。
 * 以后再加一个模块，往 panels 里加一项就行。
 */
import { defineAsyncComponent } from 'vue'
import PanelGroup from '../components/PanelGroup.vue'

const panels = [
  {
    key: 'exams',
    icon: '📋',
    label: '考试管理',
    desc: '发布考试、看成绩、导出',
    component: defineAsyncComponent(() => import('./Exams.vue'))
  },
  {
    key: 'typing',
    icon: '⌨',
    label: '打字学情',
    desc: '成绩排名、正确率分布',
    component: defineAsyncComponent(() => import('./TypingAdmin.vue'))
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
  <PanelGroup :panels="panels" storage-key="exam-hub" default-key="exams" />
</template>

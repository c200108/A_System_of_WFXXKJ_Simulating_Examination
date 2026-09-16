<script setup>
/**
 * 学生工作台。学生账号和班级是一件事的两面 —— 导名单要先有班、看班要看班里的人，
 * 以前分成两个顶栏菜单，来回跳。现在收在一页里，摆法和「题库」「考试」一致。
 */
import { defineAsyncComponent } from 'vue'
import PanelGroup from '../components/PanelGroup.vue'

const panels = [
  {
    key: 'students',
    icon: '🧑',
    label: '学生管理',
    desc: '建号、导入名单、批量操作',
    component: defineAsyncComponent(() => import('./Students.vue'))
  },
  {
    key: 'classes',
    icon: '🏫',
    label: '班级管理',
    desc: '建班、分配老师、班级详情',
    component: defineAsyncComponent(() => import('./Classes.vue'))
  }
]
</script>

<template>
  <PanelGroup :panels="panels" storage-key="student-hub" default-key="students" />
</template>

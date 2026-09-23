<script setup>
/**
 * 一张 ECharts 图。只按需引入用得到的几种图，整个 echarts 打进来有 1 MB 多 ——
 * 机房五十台机器同时开「成绩分析」，每一台都得下这么多。
 *
 * option 变了就整份重画（notMerge），容器尺寸变了就跟着缩放。
 */
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, BoxplotChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, BoxplotChart, ScatterChart,
  GridComponent, LegendComponent, MarkLineComponent, TooltipComponent,
  CanvasRenderer
])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '300px' },
  label: { type: String, default: '' }
})

const el = ref(null)
const chart = shallowRef(null)
let observer = null

function render() {
  if (chart.value) chart.value.setOption(props.option, true)
}

onMounted(() => {
  chart.value = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  observer = new ResizeObserver(() => chart.value && chart.value.resize())
  observer.observe(el.value)
})
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => {
  if (observer) observer.disconnect()
  if (chart.value) chart.value.dispose()
})
</script>

<template>
  <div ref="el" class="echart" :style="{ height }" role="img" :aria-label="label" />
</template>

<style scoped>
.echart {
  width: 100%;
}
</style>

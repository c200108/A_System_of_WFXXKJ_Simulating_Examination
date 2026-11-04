<script setup>
/**
 * 一张 ECharts 图。只按需引入用得到的几种图，整个 echarts 打进来有 1 MB 多 ——
 * 机房五十台机器同时开「成绩分析」，每一台都得下这么多。
 *
 * option 变了就整份重画（notMerge），容器尺寸变了就跟着缩放。
 *
 * 坐标轴文字太长被截断（overflow: 'truncate'）时，轴上写 triggerEvent: true，
 * 鼠标停在**文字**上也弹出这一行的提示框（和停在柱子上一样），完整内容在框里看。
 */
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, BoxplotChart, HeatmapChart, LineChart, PieChart, RadarChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, BoxplotChart, HeatmapChart, LineChart, PieChart, RadarChart, ScatterChart,
  GridComponent, LegendComponent, MarkLineComponent, RadarComponent, TooltipComponent, VisualMapComponent,
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

/** 鼠标停在类目轴的文字上：找到是第几项，替它弹出第一组数据的提示框 */
function labelTip(e) {
  if (e.componentType !== 'xAxis' && e.componentType !== 'yAxis') return
  const axes = [].concat(props.option[e.componentType] || [])
  const data = (axes[e[e.componentType + 'Index'] || 0] || {}).data || []
  const i = data.findIndex(d => (d && typeof d === 'object' ? d.value : d) === e.value)
  if (i >= 0) chart.value.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: i })
}

onMounted(() => {
  chart.value = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  chart.value.on('mouseover', labelTip)
  chart.value.on('mouseout', e => {
    if (e.componentType === 'xAxis' || e.componentType === 'yAxis') chart.value.dispatchAction({ type: 'hideTip' })
  })
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

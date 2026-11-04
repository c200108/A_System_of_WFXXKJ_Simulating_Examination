<script setup>
/**
 * 一张 ECharts 图。只按需引入用得到的几种图，整个 echarts 打进来有 1 MB 多 ——
 * 机房五十台机器同时开「成绩分析」，每一台都得下这么多。
 *
 * option 变了就整份重画（notMerge），容器尺寸变了就跟着缩放。
 */
import { onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
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
  label: { type: String, default: '' },
  // 坐标轴文字太长被截成「…」时，鼠标停在文字上弹出完整内容。
  // 传一个函数 (轴上的原文) => 要显示的文字（可以多行）；不传就不弹。
  // 用的时候那根轴要开 triggerEvent: true，ECharts 才会把文字上的鼠标事件发出来
  axisTip: { type: Function, default: null }
})

const el = ref(null)
const chart = shallowRef(null)
let observer = null
const tip = reactive({ show: false, text: '', x: 0, y: 0 })

function onAxisOver(p) {
  if (!props.axisTip || p.targetType !== 'axisLabel') return
  if (p.componentType !== 'yAxis' && p.componentType !== 'xAxis') return
  const e = p.event && p.event.event
  tip.text = props.axisTip(p.value) || String(p.value ?? '')
  // 贴着鼠标右下方；靠近屏幕右边、下边时翻到另一侧，不被窗口切掉
  const x = e ? e.clientX : 0
  const y = e ? e.clientY : 0
  tip.x = x + 440 > window.innerWidth ? Math.max(8, x - 440) : x + 14
  tip.y = y + 160 > window.innerHeight ? Math.max(8, y - 150) : y + 14
  tip.show = true
}
function hideTip() {
  tip.show = false
}

function render() {
  if (chart.value) chart.value.setOption(props.option, true)
}

onMounted(() => {
  chart.value = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  chart.value.on('mouseover', onAxisOver)
  chart.value.on('mouseout', hideTip)
  chart.value.on('globalout', hideTip)
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
  <Teleport to="body">
    <div v-if="tip.show" class="echart-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">{{ tip.text }}</div>
  </Teleport>
</template>

<style scoped>
.echart {
  width: 100%;
}
.echart-tip {
  position: fixed;
  z-index: 3000;
  max-width: 420px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-bg-color-overlay);
  color: var(--el-text-color-primary);
  box-shadow: var(--el-box-shadow-light);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-line;
  word-break: break-all;
  pointer-events: none;
}
</style>

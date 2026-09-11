<script setup lang="ts">
// src/components/perf/PerfCharts.vue
// 性能曲线容器:多子图纵向排,echarts connect 十字准星跨子图联动。
// option 组装全部在 perfOption 纯函数,组件只做 init/setOption 透传与生命周期管理。
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { buildPerfOptions, type PerfSummary } from './perfOption'
import type { AppPerfSeries } from '../../types'

// echarts/core 按需注册,控制包体
echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkLineComponent, TitleComponent, CanvasRenderer])

const props = defineProps<{ series: AppPerfSeries[]; summary?: PerfSummary; showRefs?: boolean }>()

const refsOn = ref(props.showRefs ?? false)
const hasCharts = ref(false) // instances 非响应式:模板只以此开关图表容器/空态
const host = ref<HTMLElement | null>(null)
const instances: ReturnType<typeof echarts.init>[] = []

async function render() {
  instances.forEach((c) => c.dispose())
  instances.length = 0
  const opts = buildPerfOptions(props.series, { showRefs: refsOn.value, summary: props.summary ?? null })
  hasCharts.value = opts.length > 0
  if (!opts.length) return
  await nextTick() // 容器随 hasCharts=true 挂载后才有 host 可 init
  if (!host.value) return
  host.value.innerHTML = ''
  for (const opt of opts) {
    // 子 div 为命令式创建,不吃 scoped CSS(无 data-v 标记)——高度必须内联,否则 0 高画布=全空白图
    const el = document.createElement('div')
    el.style.width = '100%'
    el.style.height = '240px'
    el.style.marginBottom = '8px'
    const chart = echarts.init(host.value.appendChild(el))
    chart.setOption(opt)
    instances.push(chart)
  }
  echarts.connect(instances) // 十字准星跨子图联动
}

// 窗口尺寸变化 → 全部子图 resize;卸载时移除监听并 dispose
function onResize() {
  instances.forEach((c) => c.resize())
}
window.addEventListener('resize', onResize)
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  instances.forEach((c) => c.dispose())
  instances.length = 0
})

onMounted(render)
watch(() => [props.series, props.summary, refsOn.value], render)

function exportPng() {
  const url = instances[0]?.getDataURL({ pixelRatio: 2, backgroundColor: '#fff' })
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = 'perf-chart.png'
  a.click()
}
</script>

<template>
  <div class="perf-charts">
    <div class="toolbar">
      <el-checkbox v-model="refsOn" data-test="toggle-refs">mean/p90 参考线</el-checkbox>
      <el-button size="small" data-test="export-png" @click="exportPng">导出 PNG</el-button>
    </div>
    <div v-if="hasCharts" ref="host" class="charts" />
    <p v-else class="empty">暂无性能数据</p>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.charts > div { width: 100%; height: 240px; margin-bottom: 8px; }
/* 高度以内联样式为准(scoped 选择器匹配不到命令式创建的子 div),此规则仅作兜底 */
.empty { color: var(--el-text-color-secondary); }
</style>

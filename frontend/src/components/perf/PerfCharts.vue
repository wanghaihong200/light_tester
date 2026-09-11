<script setup lang="ts">
// src/components/perf/PerfCharts.vue
// 性能曲线容器:多子图纵向排;option 组装全部在 perfOption 纯函数,组件只做 init/setOption
// 透传与生命周期管理。connect 联动经用户实测裁撤(悬停只看当前子图,跨子图 tooltip/十字
// 同步反而是干扰),不再 import/调用 echarts.connect。
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { buildPerfOptions, type PerfChartOption, type PerfSummary } from './perfOption'
import type { AppPerfSeries } from '../../types'

// echarts/core 按需注册,控制包体
echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkLineComponent, TitleComponent, CanvasRenderer])

const props = defineProps<{ series: AppPerfSeries[]; summary?: PerfSummary; showRefs?: boolean }>()

const refsOn = ref(props.showRefs ?? false)
const bucketSec = ref(0) // 聚合桶宽(秒);0=原始全采样
const hasCharts = ref(false) // instances 非响应式:模板只以此开关图表容器/空态
const host = ref<HTMLElement | null>(null)
const instances: ReturnType<typeof echarts.init>[] = []

async function render() {
  instances.forEach((c) => c.dispose())
  instances.length = 0
  const opts = buildPerfOptions(props.series, { showRefs: refsOn.value, summary: props.summary ?? null, bucketSec: bucketSec.value || undefined })
  hasCharts.value = opts.length > 0
  if (!opts.length) return
  await nextTick() // 容器随 hasCharts=true 挂载后才有 host 可 init
  if (!host.value) return
  host.value.innerHTML = ''
  opts.forEach((opt, i) => {
    // wrapper 为命令式创建,不吃 scoped CSS(无 data-v 标记)——高度必须内联,否则 0 高画布=全空白图;
    // relative 定位承载右上角单子图下载钮,echarts.init 的目标是其内撑满的 chart div
    const wrap = document.createElement('div')
    wrap.style.position = 'relative'
    wrap.style.width = '100%'
    wrap.style.height = '240px'
    wrap.style.marginBottom = '8px'
    const el = document.createElement('div')
    el.style.width = '100%'
    el.style.height = '100%'
    wrap.appendChild(el)
    host.value.appendChild(wrap)
    const chart = echarts.init(el)
    chart.setOption(opt)
    instances.push(chart)
    wrap.appendChild(downloadBtn(opt, i, chart))
  })
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
watch(() => [props.series, props.summary, refsOn.value, bucketSec.value], render)

// 触发浏览器下载:url 为 dataURL,沿用 a[download] 点击方式
function downloadUrl(url: string, name: string) {
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
}

// 单子图下载文件名:优先取子图 title(采集大类),清洗文件系统非法字符;无 title 回退序号
function chartFileName(opt: PerfChartOption, index: number): string {
  const t = (opt.title as { text?: string } | undefined)?.text?.trim()
  const base = (t || `chart-${index + 1}`).replace(/[\\/:*?"<>|\s]+/g, '_')
  return `perf-chart-${base}.png`
}

// 单子图下载小钮:右上 top:28px(偏移避开顶部图例 legend top:2;底部有 dataZoom 不落下方)
function downloadBtn(opt: PerfChartOption, index: number, chart: ReturnType<typeof echarts.init>) {
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.style.cssText =
    'position:absolute;top:28px;right:4px;z-index:5;border:none;border-radius:4px;' +
    'background:rgba(255,255,255,.75);cursor:pointer;font-size:12px;padding:2px 6px;line-height:1;'
  btn.textContent = '⬇'
  btn.title = '下载本子图 PNG'
  btn.addEventListener('click', () =>
    downloadUrl(chart.getDataURL({ pixelRatio: 2, backgroundColor: '#fff' }), chartFileName(opt, index)),
  )
  return btn
}

// 导出 PNG 改为全部子图拼一张长图(只导首个子图=用户报的问题):
// 各子图 canvas 同容器等宽(物理像素含 dpr),白底纵向堆叠;
// 拿不到 2d 上下文(jsdom/异常环境)时静默降级,不抛错、不触发下载
function exportPng() {
  const canvases = instances
    .map((c) => c.getDom().querySelector('canvas'))
    .filter((cv): cv is HTMLCanvasElement => !!cv)
  if (!canvases.length) return
  const out = document.createElement('canvas')
  out.width = canvases[0].width
  out.height = canvases.reduce((h, cv) => h + cv.height, 0)
  const ctx = out.getContext('2d')
  if (!ctx) return
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, out.width, out.height)
  let y = 0
  for (const cv of canvases) {
    ctx.drawImage(cv, 0, y)
    y += cv.height
  }
  downloadUrl(out.toDataURL('image/png'), 'perf-charts.png')
}
</script>

<template>
  <div class="perf-charts">
    <div class="toolbar">
      <el-checkbox v-model="refsOn" data-test="toggle-refs">mean/p90 参考线</el-checkbox>
      <span class="bucket-lbl">聚合时长</span>
      <el-select v-model="bucketSec" size="small" class="bucket-select" data-test="bucket-select">
        <el-option label="原始采样" :value="0" />
        <el-option label="1 分钟" :value="60" />
        <el-option label="5 分钟" :value="300" />
        <el-option label="20 分钟" :value="1200" />
        <el-option label="1 小时" :value="3600" />
      </el-select>
      <el-button size="small" data-test="export-png" @click="exportPng">导出 PNG</el-button>
    </div>
    <div v-if="hasCharts" ref="host" class="charts" />
    <p v-else class="empty">暂无性能数据</p>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.bucket-lbl { color: var(--el-text-color-secondary); font-size: 13px; }
.bucket-select { width: 118px; }
.charts > div { width: 100%; height: 240px; margin-bottom: 8px; }
/* 高度以内联样式为准(scoped 选择器匹配不到命令式创建的子 div),此规则仅作兜底 */
.empty { color: var(--el-text-color-secondary); }
</style>

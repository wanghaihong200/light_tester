<script setup lang="ts">
// 计划14 Task11:性能趋势对话框(趋势仅 run 来源,聚合口径=perf_summary,同后端)
// 筛选(脚本/设备,下拉数据=列表 run 记录去重,可空=全部)→ getPerfTrend →
// 每 group(脚本@设备)一个区块,组内每 series 键一个子图:mean 实线 + p90 虚线,
// X=点序(0..n-1),轴 label=finished_at(格式化到分);points/series 为空的组显示组级空态。
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getPerfTrend, listPerfRecords } from '../../api/perf'
import type { TrendGroup, TrendPoint } from '../../types'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'close'): void }>()

// ── 筛选:下拉数据从列表 run 记录去重(同后端口径,import 不参与趋势)──
const scriptId = ref<'' | number>('') // ''=全部(ElOption value 不收 null,同面板来源筛选的哨兵)
const deviceSerial = ref('')
const scriptOptions = ref<{ id: number; name: string }[]>([])
const deviceOptions = ref<string[]>([])

// ── 数据 ──
const groups = ref<TrendGroup[]>([])
const loading = ref(false)
let seq = 0 // 请求序号守卫:快速切筛选时慢响应不覆盖新结果、不弹过期报错(PerfRecordPane 同款)

async function loadFilters() {
  try {
    // 趋势仅 run 口径:后端已按 source=run 过滤,前端再滤一道防契约松动(brief:从记录提取 run 来源)
    const recs = (await listPerfRecords(props.projectId, { source: 'run' })).filter((r) => r.source === 'run')
    const scripts = new Map<number, string>()
    const devices: string[] = []
    for (const r of recs) {
      if (r.script_id != null && !scripts.has(r.script_id)) scripts.set(r.script_id, r.script_name || `脚本 #${r.script_id}`)
      if (r.device_serial && !devices.includes(r.device_serial)) devices.push(r.device_serial)
    }
    scriptOptions.value = [...scripts].map(([id, name]) => ({ id, name }))
    deviceOptions.value = devices
  } catch {
    scriptOptions.value = [] // 筛选项拉取失败不打断趋势主数据加载
    deviceOptions.value = []
  }
}

async function load() {
  const s = ++seq
  loading.value = true
  try {
    const res = await getPerfTrend(props.projectId, {
      ...(scriptId.value !== '' ? { script_id: scriptId.value } : {}),
      ...(deviceSerial.value ? { device_serial: deviceSerial.value } : {}),
    })
    if (s !== seq) return
    groups.value = res.groups ?? []
  } catch (e) {
    if (s !== seq) return
    groups.value = []
    ElMessage.error(`加载趋势数据失败:${(e as Error).message}`)
  } finally {
    if (s === seq) loading.value = false
  }
  await renderCharts()
}

async function init() {
  await loadFilters()
  await load()
}
onMounted(init)
watch([scriptId, deviceSerial], () => { load() })

// ── 图表:组内子图键 = 各点 series 键并集(顺序取首现);全部为空 → 组级空态 ──
const wrap = ref<HTMLElement | null>(null)
const instances: ReturnType<typeof echarts.init>[] = []

function groupKeys(g: TrendGroup): string[] {
  const keys: string[] = []
  for (const p of g.points) {
    for (const k of Object.keys(p.series ?? {})) if (!keys.includes(k)) keys.push(k)
  }
  return keys
}

function groupTitle(g: TrendGroup): string {
  return `${g.script_name || '未关联脚本'}@${g.device_serial}`
}

// ISO 截断到分钟(PerfRecordPane 同款,格式跨环境稳定)
function fmtMinute(iso: string): string {
  return String(iso).slice(0, 16).replace('T', ' ')
}

function trendOption(points: TrendPoint[], key: string): Record<string, unknown> {
  const mean = points.map((p) => p.series?.[key]?.mean ?? null)
  const p90 = points.map((p) => p.series?.[key]?.p90 ?? null)
  const series: Record<string, unknown>[] = [
    { name: 'mean', type: 'line', showSymbol: true, lineStyle: { type: 'solid' }, data: mean },
  ]
  if (p90.some((v) => v != null)) { // p90 整键缺失(null)只画 mean
    series.push({ name: 'p90', type: 'line', showSymbol: true, lineStyle: { type: 'dashed' }, data: p90 })
  }
  return {
    title: { text: key, left: 10, top: 0, textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 2, right: 10 },
    grid: { left: 50, right: 20, top: 34, bottom: 40 },
    xAxis: { type: 'category', name: '采集时间', boundaryGap: false, data: points.map((p) => fmtMinute(p.finished_at)) },
    yAxis: { type: 'value', scale: true, name: key },
    series,
  }
}

async function renderCharts() {
  instances.forEach((c) => c.dispose())
  instances.length = 0
  await nextTick() // 组块随 groups 渲染完成后才有容器可查
  const hosts = wrap.value ? Array.from(wrap.value.querySelectorAll<HTMLDivElement>('[data-test="trend-charts"]')) : []
  hosts.forEach((h) => {
    const g = groups.value[Number(h.dataset.group)]
    if (!g) return
    // 先清旧子节点:dispose 只清 echarts 实例,追加的容器 div 本体会残留;
    // 组块 v-for 用索引键、筛选变化时 host 被原位复用,不清会越积越多(PerfCharts 同款防护)
    h.innerHTML = ''
    for (const key of groupKeys(g)) {
      const el = h.appendChild(document.createElement('div'))
      // 动态建出的节点不带 scoped data-v,尺寸写内联(依赖 scoped 样式会拿不到高度)
      el.style.width = '100%'
      el.style.height = '220px'
      el.style.marginBottom = '8px'
      const chart = echarts.init(el)
      chart.setOption(trendOption(g.points, key))
      instances.push(chart)
    }
  })
  if (instances.length) echarts.connect(instances)
}

function onResize() {
  instances.forEach((c) => c.resize())
}
window.addEventListener('resize', onResize)
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  instances.forEach((c) => c.dispose())
  instances.length = 0
})
</script>

<template>
  <el-dialog :model-value="true" title="性能趋势" width="900px" top="5vh" @close="emit('close')">
    <div class="filters">
      <el-select v-model="scriptId" size="small" data-test="trend-script-filter" class="filter-select">
        <el-option label="全部脚本" value="" />
        <el-option v-for="s in scriptOptions" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <el-select v-model="deviceSerial" size="small" data-test="trend-device-filter" class="filter-select">
        <el-option label="全部设备" value="" />
        <el-option v-for="d in deviceOptions" :key="d" :label="d" :value="d" />
      </el-select>
    </div>

    <div ref="wrap" v-loading="loading" class="trend-body">
      <div v-for="(g, gi) in groups" :key="gi" class="trend-group" data-test="trend-group">
        <h4 class="group-title" data-test="trend-group-title">{{ groupTitle(g) }}</h4>
        <div v-if="groupKeys(g).length" class="charts" data-test="trend-charts" :data-group="gi" />
        <p v-else class="empty" data-test="group-empty">该分组暂无趋势数据(采集中断或统计缺失)</p>
      </div>
      <el-empty v-if="!loading && groups.length === 0" description="暂无趋势数据" data-test="trend-empty" />
    </div>
  </el-dialog>
</template>

<style scoped>
.filters {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.filter-select {
  width: 200px;
}
.trend-body {
  min-height: 160px;
}
.trend-group {
  margin-bottom: 14px;
}
.group-title {
  margin: 0 0 6px;
}
.empty {
  color: var(--el-text-color-secondary);
}
</style>

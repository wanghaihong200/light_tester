<script setup lang="ts">
// 计划14 冒烟修复:趋势弹窗重构为「单指标下拉 + 单走势图」。
// 旧实现每 group 每 series 键一张子图,真实数据(43 文件×列=97 键)→ 97 子图、弹窗 4.4 万像素,不可用。
// 现在:脚本/设备筛选(可空=全部)→ getPerfTrend → 汇总键集(各 group points 的 series 键并集)
// → 「指标」下拉(默认第一个键)→ 单张走势图:多 group 同键各出一组 mean/p90 系列(名前缀=脚本@设备),
// 单组免前缀;mean 实线 + p90 虚线(p90 全 null 只画 mean);X=时间并轴(首现序),缺点 null 断线。
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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
    groups.value = res.groups ?? [] // 渲染统一由下方 [groups, metricKey] watcher 驱动
  } catch (e) {
    if (s !== seq) return
    groups.value = []
    ElMessage.error(`加载趋势数据失败:${(e as Error).message}`)
  } finally {
    if (s === seq) loading.value = false
  }
}

async function init() {
  await loadFilters()
  await load()
}
onMounted(init)
watch([scriptId, deviceSerial], () => { load() })

// ── 指标键汇总:当前筛选覆盖的所有 group 的 points series 键并集去重(顺序取首现)──
const metricKeys = computed<string[]>(() => {
  const keys: string[] = []
  for (const g of groups.value) {
    for (const p of g.points) {
      for (const k of Object.keys(p.series ?? {})) if (!keys.includes(k)) keys.push(k)
    }
  }
  return keys
})

// 键 label:`<fileKey>::<列名>` → `fileKey · 列名`(同对比弹窗统计表口径)
function metricLabel(key: string): string {
  return key.split('::').join(' · ')
}

const metricKey = ref('')

// groups 或指标变化统一走这里;键集变化需重置选中时只改选中值并先返回,
// 由指标变化再次触发本 watcher 渲染,保证每次数据/切换恰好一次 setOption
watch([groups, metricKey], () => {
  const keys = metricKeys.value
  if (keys.length && !keys.includes(metricKey.value)) {
    metricKey.value = keys[0] ?? ''
    return
  }
  renderCharts()
})

// ── 单走势图 ──
const chartHost = ref<HTMLElement | null>(null)
const instances: ReturnType<typeof echarts.init>[] = []

function groupTitle(g: TrendGroup): string {
  return `${g.script_name || '未关联脚本'}@${g.device_serial}`
}

// ISO 截断到分钟(PerfRecordPane 同款,格式跨环境稳定)
function fmtMinute(iso: string): string {
  return String(iso).slice(0, 16).replace('T', ' ')
}

function trendOption(allGroups: TrendGroup[], key: string): Record<string, unknown> {
  // X 轴 = 各组点时间的有序并集(首现序);某组缺该时间点 → null 断线(echarts 跳点)
  const labels: string[] = []
  for (const g of allGroups) {
    for (const p of g.points) {
      const l = fmtMinute(p.finished_at)
      if (!labels.includes(l)) labels.push(l)
    }
  }
  const series: Record<string, unknown>[] = []
  const multi = allGroups.length > 1
  for (const g of allGroups) {
    const byLabel = new Map<string, TrendPoint['series'][string]>()
    for (const p of g.points) {
      const v = p.series?.[key]
      if (v) byLabel.set(fmtMinute(p.finished_at), v) // 同刻度取后点(截断到分理论碰撞防御)
    }
    if (byLabel.size === 0) continue // 该组整个没有此键(如其它脚本的独有指标)→ 不画全空线
    const prefix = multi ? `${groupTitle(g)} · ` : ''
    const mean = labels.map((l) => byLabel.get(l)?.mean ?? null)
    series.push({ name: `${prefix}mean`, type: 'line', showSymbol: true, lineStyle: { type: 'solid' }, data: mean })
    const p90 = labels.map((l) => byLabel.get(l)?.p90 ?? null)
    if (p90.some((v) => v != null)) { // p90 整线缺失(null)只画 mean
      series.push({ name: `${prefix}p90`, type: 'line', showSymbol: true, lineStyle: { type: 'dashed' }, data: p90 })
    }
  }
  return {
    title: { text: metricLabel(key), left: 10, top: 0, textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 2, right: 10 },
    grid: { left: 50, right: 20, top: 34, bottom: 40 },
    // 白底:echarts canvas 默认透明,叠在下层内容上=标题重影(冒烟反馈,同 perfOption)
    backgroundColor: '#fff',
    xAxis: { type: 'category', name: '采集时间', boundaryGap: false, data: labels },
    yAxis: { type: 'value', scale: true, name: metricLabel(key) },
    series,
  }
}

async function renderCharts() {
  instances.forEach((c) => c.dispose())
  instances.length = 0
  await nextTick() // v-show 容器随键集出现后再 init
  const host = chartHost.value
  if (!host || !metricKey.value) return // 无键:走 el-empty 空态,不 init
  const chart = echarts.init(host)
  chart.setOption(trendOption(groups.value, metricKey.value))
  instances.push(chart)
  // connect 联动经用户实测裁撤(悬停只看当前图,跨图 tooltip/十字同步反而是干扰)
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
      <el-select
        v-model="metricKey" size="small" data-test="metric-select" class="filter-select metric-select"
        placeholder="指标" :disabled="metricKeys.length === 0"
      >
        <el-option v-for="k in metricKeys" :key="k" :label="metricLabel(k)" :value="k" />
      </el-select>
    </div>

    <div v-loading="loading" class="trend-body">
      <div v-show="metricKeys.length > 0" ref="chartHost" class="charts" data-test="trend-charts" />
      <el-empty
        v-if="!loading && metricKeys.length === 0"
        data-test="trend-empty"
        :description="groups.length ? '当前筛选下暂无趋势数据(采集中断或统计缺失)' : '暂无趋势数据'"
      />
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
.metric-select {
  width: 260px; /* 键 label 含 fileKey·列名,比脚本/设备名长 */
}
.trend-body {
  min-height: 160px;
}
.charts {
  width: 100%;
  height: 320px;
}
</style>

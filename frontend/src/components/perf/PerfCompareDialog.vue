<script setup lang="ts">
// 计划14 Task11:跨记录对比对话框(上=同 item 叠加曲线,下=统计对比表)
// 叠加图:每记录各自 buildPerfOptions(seriesNamePrefix=记录名)后按大类组(title=组键)合并
// series 数组,组成每组一个 option(组键取并集,缺该组的记录在该子图无系列);
// 统计表行按 fileKey::列名 并列(计划14 冒烟修复 re-review),只呈现 mean/p90,
// 不做"最优值高亮"(方向因指标而异,ADR 共识)。
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { buildPerfOptions, normalizePerfSummary, type PerfChartOption, type PerfSummaryColumn } from './perfOption'
import { comparePerfRecords } from '../../api/perf'
import type { AppPerfSeries, PerfRecord } from '../../types'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent, CanvasRenderer])

const props = defineProps<{ projectId: number; recordIds: number[] }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(true)
const records = ref<PerfRecord[]>([])
const hasCharts = ref(false) // instances 非响应式:模板只以此开关图表容器/空态(PerfCharts 同款)
const host = ref<HTMLElement | null>(null)
const instances: ReturnType<typeof echarts.init>[] = []

// 合并同 item 子图:每记录一次 buildPerfOptions(纯函数,option 为平面对象),
// 以 option.title.text(=item 名)为键归并各记录的 series 数组;
// xAxis.max 取组内最大 x(分组化后组内首线不一定最长,偏小会裁掉长线;计划14 冒烟修复
// re-review)。X 已从采样序号改为 SimpleTime 秒(perfOption 冒烟反馈修 2),故 max 必须
// 取数据点 x 的最大值——沿用旧的「数据行数-1」会把 0~31s 的秒轴拉长到行数范围,线挤左半边。
function mergedOptions(recordList: PerfRecord[], seriesMap: Record<string, AppPerfSeries[]>): PerfChartOption[] {
  const byItem = new Map<string, { base: PerfChartOption; series: unknown[]; maxX: number }>()
  for (const r of recordList) {
    for (const opt of buildPerfOptions(seriesMap[String(r.id)] ?? [], { seriesNamePrefix: r.name })) {
      const item = String((opt.title as { text?: string } | undefined)?.text ?? '')
      if (!item) continue // item 名来自设备动态 CSV 数据,正常非空;空串(异常数据)不并入无标题子图
      const e = byItem.get(item) ?? { base: opt, series: [], maxX: 0 }
      e.series.push(...((opt.series as unknown[] | undefined) ?? []))
      for (const s of ((opt.series as { data?: [number, number][] }[] | undefined) ?? [])) {
        for (const p of s.data ?? []) {
          const x = Number(p?.[0])
          if (Number.isFinite(x) && x > e.maxX) e.maxX = x
        }
      }
      byItem.set(item, e)
    }
  }
  return [...byItem.values()].map((e) => ({
    ...e.base,
    series: e.series,
    xAxis: { ...(e.base.xAxis as Record<string, unknown>), max: e.maxX },
  }))
}

async function load() {
  loading.value = true
  try {
    const res = await comparePerfRecords(props.projectId, props.recordIds)
    records.value = res.records
    const opts = mergedOptions(res.records, res.series ?? {})
    hasCharts.value = opts.length > 0
    if (!opts.length) return
    await nextTick() // 容器随 hasCharts=true 挂载后才有 host 可 init(PerfCharts 同款)
    if (!host.value) return
    host.value.innerHTML = '' // 清空仅用于重渲染兜底,内容全部由 createElement 生成
    for (const opt of opts) {
      const el = host.value.appendChild(document.createElement('div'))
      // 动态建出的节点不带 scoped data-v,尺寸写内联(依赖 scoped 样式会拿不到高度)
      el.style.width = '100%'
      el.style.height = '240px'
      el.style.marginBottom = '8px'
      const chart = echarts.init(el)
      chart.setOption(opt)
      instances.push(chart)
    }
    // connect 联动经用户实测裁撤(悬停只看当前子图,跨子图 tooltip/十字同步反而是干扰)
  } catch (e) {
    ElMessage.error(`加载对比数据失败:${(e as Error).message}`)
    emit('close') // 无数据可展示,关窗回到列表页
  } finally {
    loading.value = false
  }
}
onMounted(load)

function onResize() {
  instances.forEach((c) => c.resize())
}
window.addEventListener('resize', onResize)
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  instances.forEach((c) => c.dispose())
  instances.length = 0
})

// ── 统计对比表:行=各记录 summary 列按 键 并集,列=各记录名(mean / p90 并列)──
// normalizePerfSummary 幂等:标准形透传,CLI perf-analyze 真实 {files:[…]} 归一(计划14 冒烟修复)。
// 行键用 fileKey::列名(计划14 冒烟修复 re-review):真实 stem 内嵌 hex16+时间戳逐次采集唯一,
// 按完整 stem::列名会让两记录同指标裂成两行、对方单元格显 —,并列目的落空;
// legacy 标准形(无 fileKey)回退 index。显示名保持 <fileKey> · <列名>。
const normCols = (r: PerfRecord): PerfSummaryColumn[] =>
  normalizePerfSummary(r.perf_summary)?.columns ?? []

const colKey = (c: PerfSummaryColumn): string =>
  c.fileKey != null && c.name ? `${c.fileKey}::${c.name}` : c.index
const colLabel = (c: PerfSummaryColumn): string =>
  c.fileKey != null && c.name ? `${c.fileKey} · ${c.name}` : c.index

const statRows = computed(() => {
  const rows: { key: string; label: string }[] = []
  const seen = new Set<string>()
  for (const r of records.value) {
    for (const c of normCols(r)) {
      const key = colKey(c)
      if (seen.has(key)) continue
      seen.add(key)
      rows.push({ key, label: colLabel(c) })
    }
  }
  return rows
})

const fmtNum = (v: number | null | undefined) => (v == null ? '—' : Number(v).toFixed(2))

function cellText(r: PerfRecord, key: string): string {
  const col: PerfSummaryColumn | undefined = normCols(r).find((c) => colKey(c) === key)
  if (!col || (col.mean == null && col.p90 == null)) return '—'
  return `${fmtNum(col.mean)} / ${fmtNum(col.p90)}`
}
</script>

<template>
  <el-dialog :model-value="true" style="background-color: #fff" title="跨记录对比" width="900px" top="5vh" @close="emit('close')">
    <div v-loading="loading" class="compare-body">
      <div v-if="hasCharts" ref="host" class="charts" data-test="compare-charts" />
      <p v-else-if="!loading" class="empty" data-test="charts-empty">暂无对比曲线(记录缺少可绘制的数值列)</p>

      <template v-if="records.length">
        <h4 class="section-title">统计对比</h4>
        <el-table :data="statRows" size="small" border max-height="280" data-test="compare-stat-table">
          <el-table-column label="指标" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.label }}</template>
          </el-table-column>
          <el-table-column v-for="r in records" :key="r.id" :label="r.name" min-width="130">
            <template #default="{ row }">{{ cellText(r, row.key) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.compare-body {
  min-height: 160px;
}
.charts {
  margin-bottom: 8px;
}
.section-title {
  margin: 4px 0 8px;
}
.empty {
  color: var(--el-text-color-secondary);
}
</style>

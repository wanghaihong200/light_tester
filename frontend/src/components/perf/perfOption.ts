// src/components/perf/perfOption.ts
// ECharts option 组装纯函数(零 DOM、零 echarts import,可测)——组件层只做 init/setOption。
// 轴单位不做换算:CSV 列语义动态发现且 SoloPi 值可能带单位字符串,轴名即采集项名(ADR-0010 YAGNI)。
import type { AppPerfSeries } from '../../types'

export interface PerfSummaryColumn {
  index: string
  sampleCount?: number
  min?: number; max?: number; mean?: number; median?: number; p90?: number
}
export type PerfSummary = { columns?: PerfSummaryColumn[]; error?: string } | null
export interface StatRow { index: string; sampleCount?: number; min?: number; max?: number; mean?: number; median?: number; p90?: number }
export type PerfChartOption = Record<string, unknown>

const isNum = (v: string) => v.trim() !== '' && Number.isFinite(Number(v))

function numericColumns(s: AppPerfSeries): number[] {
  const out: number[] = []
  for (let c = 1; c < s.columns.length; c++) {
    const name = (s.columns[c] || '').toLowerCase()
    if (/^(time|ts|timestamp)/.test(name)) continue // 首列后的时间列同样视为 X 轴
    if (s.rows.every((r) => isNum(r[c] ?? ''))) out.push(c)
  }
  return out
}

function refLines(item: string, col: string, summary: PerfSummary): unknown[] {
  const cols = summary?.columns ?? []
  // 按特异性顺序命中,避免 find 短路让前缀规则遮蔽后面的逐列精确匹配(参考线张冠李戴):
  // `item::col` 精确 → `item_col` 精确 → `item` 全项 → 前缀兜底。
  const hit = cols.find((c) => c.index === `${item}::${col}`)
    ?? cols.find((c) => c.index === `${item}_${col}`)
    ?? cols.find((c) => c.index === item)
    ?? cols.find((c) => c.index.startsWith(`${item}::`) || c.index.startsWith(`${item}_`))
  if (!hit || hit.mean == null) return []
  const lines: unknown[] = []
  lines.push({ yAxis: hit.mean, name: 'mean', lineStyle: { type: 'solid', color: '#909399' }, symbol: 'none', label: { formatter: 'mean {c}' } })
  if (hit.p90 != null) lines.push({ yAxis: hit.p90, name: 'p90', lineStyle: { type: 'dashed', color: '#e6a23c' }, symbol: 'none', label: { formatter: 'p90 {c}' } })
  return lines
}

export function buildPerfOptions(
  series: AppPerfSeries[],
  opts: { showRefs?: boolean; summary?: PerfSummary; seriesNamePrefix?: string } = {},
): PerfChartOption[] {
  const out: PerfChartOption[] = []
  for (const s of series) {
    const cols = numericColumns(s)
    if (!cols.length || s.rows.length < 2) continue
    const prefix = opts.seriesNamePrefix ? `${opts.seriesNamePrefix} · ` : ''
    const charts = cols.map((c) => ({
      name: `${prefix}${s.columns[c] || `col${c}`}`,
      type: 'line', showSymbol: false, sampling: 'lttb',
      data: s.rows.map((r, i) => [i, Number(r[c])]),
      ...(opts.showRefs ? { markLine: { silent: true, data: refLines(s.item, s.columns[c] || '', opts.summary ?? null) } } : {}),
    }))
    out.push({
      title: { text: s.item, left: 10, top: 0, textStyle: { fontSize: 13 } },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: { top: 2, right: 10, type: 'scroll' },
      grid: { left: 50, right: 20, top: 34, bottom: 52 },
      xAxis: { type: 'value', min: 0, max: s.rows.length - 1, name: '采样点' },
      yAxis: { type: 'value', scale: true, name: s.item },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 10 }],
      series: charts,
    })
  }
  return out
}

export function extractStatRows(summary: PerfSummary): StatRow[] {
  if (!summary || summary.error || !Array.isArray(summary.columns)) return []
  return summary.columns.map((c) => ({ ...c }))
}

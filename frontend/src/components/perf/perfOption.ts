// src/components/perf/perfOption.ts
// ECharts option 组装纯函数(零 DOM、零 echarts import,可测)——组件层只做 init/setOption。
// 轴单位不做换算:CSV 列语义动态发现且 SoloPi 值可能带单位字符串,轴名即采集项名(ADR-0010 YAGNI)。
// 计划14 冒烟修复:CLI perf-analyze 真实输出={success, files:[{path, columns:[{name,index,kind,
// min,max,mean,median,p90,sampleCount,…}]}], summary, assessment,…},平台此前按顶层
// {columns:[…]} 消费 → 统计表/趋势全空;normalizePerfSummary 负责归一为标准形。
// 子图也由「每 series 一个 option」改为按采集项大类(fileKey)分组:一次真实采集设备端拆出
// 51 个指标 CSV,逐文件一图会同步 init 51 个 echarts 实例 → 渲染崩/空白。
// 冒烟反馈再修(2026-09-11):①option 加白底治透明画布叠影;②SimpleTime(精确同名末列,
// 相对采集起始的秒)从指标线改为 X 轴秒值,可选 bucketSec 桶聚合;xAxis.name 随之定为
// 「时间 (秒)/采样点」,yAxis.name 置空(超长 stem 竖排乱字)——ADR-0010「轴名即采集项名」
// 至此只对历史非 SoloPi 数据的 title 语义成立。
import type { AppPerfSeries } from '../../types'

export interface PerfSummaryColumn {
  index: string
  name?: string    // 归一化行:列名(CLI columns[].name)
  file?: string    // 归一化行:来源 CSV 文件 stem
  fileKey?: string // 归一化行:stem 稳定大类 key(=fileKeyOf(stem),与后端 perf.py 对齐)
  sampleCount?: number
  min?: number; max?: number; mean?: number; median?: number; p90?: number
}
export type PerfSummary = { columns?: PerfSummaryColumn[]; error?: string } | null
export interface StatRow {
  index: string
  name?: string; file?: string; fileKey?: string
  sampleCount?: number
  min?: number; max?: number; mean?: number; median?: number; p90?: number
}
export type PerfChartOption = Record<string, unknown>

// 文件 stem → 稳定大类 key:SoloPi 拆文件名模式 <指标名>_<采集项>_<hex16>_<ts>_<ts>
// (如 CPU温度_Temperature_6f1c…_1789…_1789….csv;应用进程-main-10841_CPU_….csv 为三段含进程)。
// 取第二段(采集项 Temperature/Memory/Network/CPU/FPS/Battery/Response/ThreadCount…);
// 段数<2 退第一段;空段用全 stem。后端趋势聚合键用同一算法(backend/app/routers/perf.py
// 的 _file_key,注释互指):趋势键跨 run 稳定正是趋势聚合的意义,两端改动必须同步。
export function fileKeyOf(stem: string): string {
  const parts = stem.split('_')
  const key = parts.length >= 2 ? parts[1] : parts[0]
  return key || stem
}

// CLI perf-analyze 真实结构 → 平台标准形;已是标准形(无 files)/error/null 原样透传(幂等)。
// 归一化列 index=`<文件stem>::<列名>`(refLines 的 `::` 精确规则吃这个键),
// 只收 kind==="numeric" 的列(skipped 列无统计语义)。
export function normalizePerfSummary(raw: unknown): PerfSummary {
  if (raw == null || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const files = r.files
  if (r.error != null || !Array.isArray(files)) return raw as PerfSummary
  const columns: PerfSummaryColumn[] = []
  for (const f of files) {
    const file = (f ?? {}) as Record<string, unknown>
    // path 取 stem:兼容带目录前缀的相对路径(Windows/Unix 分隔符都剥)
    const stem = String(file.path ?? '').split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') ?? ''
    for (const c of (file.columns ?? []) as Record<string, unknown>[]) {
      if (!c || c.kind !== 'numeric' || !c.name) continue
      columns.push({
        index: `${stem}::${String(c.name)}`,
        name: String(c.name),
        file: stem,
        fileKey: fileKeyOf(stem),
        sampleCount: c.sampleCount as number | undefined,
        min: c.min as number | undefined,
        max: c.max as number | undefined,
        mean: c.mean as number | undefined,
        median: c.median as number | undefined,
        p90: c.p90 as number | undefined,
      })
    }
  }
  return { columns }
}

const isNum = (v: string) => v.trim() !== '' && Number.isFinite(Number(v))

// SimpleTime(精确同名)是相对采集起始的秒值(SoloPi 每文件末列),作 X 轴而非指标线
const SIMPLE_TIME_COL = 'SimpleTime'

function numericColumns(s: AppPerfSeries): number[] {
  const out: number[] = []
  for (let c = 1; c < s.columns.length; c++) {
    const name = (s.columns[c] || '').toLowerCase()
    if (/^(time|ts|timestamp)/.test(name)) continue // 首列后的时间列同样视为 X 轴
    if (s.rows.every((r) => isNum(r[c] ?? ''))) out.push(c)
  }
  return out
}

// 采样聚合:桶起点=floor(x/bucket)*bucket,x 取桶起点,y 取桶内算术均值,按桶起点升序
function bucketize(pts: [number, number][], bucket: number): [number, number][] {
  const acc = new Map<number, { sum: number; n: number }>()
  for (const [x, y] of pts) {
    const k = Math.floor(x / bucket) * bucket
    const b = acc.get(k) ?? { sum: 0, n: 0 }
    b.sum += y
    b.n += 1
    acc.set(k, b)
  }
  return [...acc.entries()].sort((a, b) => a[0] - b[0]).map(([k, b]) => [k, b.sum / b.n])
}

function refLines(item: string, col: string, summary: PerfSummary): unknown[] {
  const cols = summary?.columns ?? []
  // 归一化 summary(行带 fileKey)只认 `<item>::<col>` 精确键:同文件兄弟列共享 `<stem>::`
  // 前缀,若退前缀/短键兜底会把别的列的统计错画成参考线(张冠李戴),未命中就不画。
  // 人工构造的 legacy summary(无 fileKey)仍走按特异性排序的四段兜底:
  // `item::col` 精确 → `item_col` 精确 → `item` 全项 → 前缀兜底。
  const hit = cols.find((c) => c.index === `${item}::${col}`)
    ?? (cols.some((c) => c.fileKey != null) ? undefined
      : cols.find((c) => c.index === `${item}_${col}`)
        ?? cols.find((c) => c.index === item)
        ?? cols.find((c) => c.index.startsWith(`${item}::`) || c.index.startsWith(`${item}_`)))
  if (!hit || hit.mean == null) return []
  const lines: unknown[] = []
  lines.push({ yAxis: hit.mean, name: 'mean', lineStyle: { type: 'solid', color: '#909399' }, symbol: 'none', label: { formatter: 'mean {c}' } })
  if (hit.p90 != null) lines.push({ yAxis: hit.p90, name: 'p90', lineStyle: { type: 'dashed', color: '#e6a23c' }, symbol: 'none', label: { formatter: 'p90 {c}' } })
  return lines
}

export function buildPerfOptions(
  series: AppPerfSeries[],
  opts: { showRefs?: boolean; summary?: PerfSummary; seriesNamePrefix?: string; bucketSec?: number } = {},
): PerfChartOption[] {
  // 按采集项大类(fileKeyOf(item))分组:同组全部系列的线画在一张图,title=大类 key,
  // xAxis.max 取组内最大 x;Map 按首现顺序出图(确定性,利于快照式断言)。
  // 系列在合并组内仍带原 item(文件 stem),参考线按 `<stem>::<列名>` 逐线精确匹配。
  type Group = { key: string; charts: unknown[]; maxX: number; hasTime: boolean }
  const groups = new Map<string, Group>()
  const prefix = opts.seriesNamePrefix ? `${opts.seriesNamePrefix} · ` : ''
  for (const s of series) {
    // SimpleTime(精确同名)列不画线,提取为该系列的 X 值数组(相对采集起始的秒)
    const cols = numericColumns(s).filter((c) => s.columns[c] !== SIMPLE_TIME_COL)
    if (!cols.length || s.rows.length < 2) continue
    const key = fileKeyOf(s.item)
    const g = groups.get(key) ?? { key, charts: [], maxX: 0, hasTime: false }
    const stIdx = s.columns.indexOf(SIMPLE_TIME_COL)
    const xs = stIdx >= 0 ? s.rows.map((r) => Number(r[stIdx])) : null
    // 无 SimpleTime 列 / 值含非数值(Number→NaN,如字符串 "null")→ X 回退采样序号 0..n-1
    const timed = xs != null && xs.every((v) => Number.isFinite(v))
    if (timed) g.hasTime = true
    for (const c of cols) {
      let pts: [number, number][] = s.rows.map((r, i) => [timed ? xs![i] : i, Number(r[c])])
      if (opts.bucketSec != null && opts.bucketSec > 0) pts = bucketize(pts, opts.bucketSec)
      g.charts.push({
        name: `${prefix}${s.columns[c] || `col${c}`}`,
        type: 'line', showSymbol: false, sampling: 'lttb',
        data: pts,
        ...(opts.showRefs ? { markLine: { silent: true, data: refLines(s.item, s.columns[c] || '', opts.summary ?? null) } } : {}),
      })
      for (const p of pts) if (p[0] > g.maxX) g.maxX = p[0]
    }
    groups.set(key, g)
  }
  return [...groups.values()].map((g) => ({
    title: { text: g.key, left: 10, top: 0, textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { top: 2, right: 10, type: 'scroll' },
    grid: { left: 50, right: 20, top: 34, bottom: 52 },
    // 白底:echarts canvas 默认透明,多子图与下层页面内容互相透出叠加=标题重影(冒烟反馈)
    backgroundColor: '#fff',
    // X 轴:组内任一系列带 SimpleTime 即按秒(秒与序号并存以秒为准);全部回退则按采样点
    xAxis: { type: 'value', min: 0, max: g.maxX, name: g.hasTime ? '时间 (秒)' : '采样点' },
    // yAxis.name 置空:name 曾用文件 stem,超长竖排成乱字;子图含义由 title(采集大类)承担
    yAxis: { type: 'value', scale: true, name: '' },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 10 }],
    series: g.charts,
  }))
}

export function extractStatRows(summary: PerfSummary): StatRow[] {
  // 入参契约:normalizePerfSummary 之后的形状(标准形透传,归一化行含 name/file/fileKey)
  if (!summary || summary.error || !Array.isArray(summary.columns)) return []
  return summary.columns.map((c) => ({ ...c }))
}

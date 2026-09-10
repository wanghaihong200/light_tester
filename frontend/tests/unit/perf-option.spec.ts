// tests/unit/perf-option.spec.ts
// 计划14 冒烟修复:CLI perf-analyze 真实输出={files:[{path, columns:[{name,kind,…}]}]},
// 平台此前按顶层 {columns:[…]} 消费 → 统计表/趋势全空;normalizePerfSummary 负责归一。
// buildPerfOptions 由「每 series 一个 option」改为按采集项大类(fileKey)分组出图——
// 一次真实采集拆 51 个指标文件,逐文件同步 init echarts 实例会渲染崩/空白。
import { describe, expect, it } from 'vitest'
import { buildPerfOptions, extractStatRows, fileKeyOf, normalizePerfSummary } from '../../src/components/perf/perfOption'
import type { AppPerfSeries } from '../../src/types'
import series15 from './fixtures/series15.json'

const series = [
  { item: 'CPU', columns: ['ts', 'total', 'app'], rows: [['0', '10', '5'], ['1', '20', '8'], ['2', '30', '11']] },
  { item: 'Memo', columns: ['label'], rows: [['non-numeric']] }, // 无数值列 → 无子图
]

// 与 perfOption.numericColumns 同口径的本地复算(锁定「合并不丢线」的期望值)
const numericCount = (s: AppPerfSeries): number => {
  const isNum = (v: string) => v.trim() !== '' && Number.isFinite(Number(v))
  let n = 0
  for (let c = 1; c < s.columns.length; c++) {
    const name = (s.columns[c] || '').toLowerCase()
    if (/^(time|ts|timestamp)/.test(name)) continue
    if (s.rows.every((r) => isNum(r[c] ?? ''))) n++
  }
  return n
}

describe('fileKeyOf(文件 stem 稳定前缀;后端 perf.py 趋势聚合 _file_key 同算法,改动须两端同步)', () => {
  it('stem 第二段=采集项大类(Temperature/CPU/Network…);段数<2 退第一段;空段用全 stem', () => {
    expect(fileKeyOf('CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789')).toBe('Temperature')
    expect(fileKeyOf('应用进程-main-10841_CPU_6570384c_1_2')).toBe('CPU')
    expect(fileKeyOf('Plain')).toBe('Plain')
    expect(fileKeyOf('a_')).toBe('a_')
  })
})

describe('normalizePerfSummary', () => {
  // 真实结构小样例(字段与 run15 落库 perf_summary 一致,见 app_runs.id=15)
  const RAW = {
    files: [{
      path: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789045016565_1789045048339.csv',
      encoding: 'gbk', rowCount: 56, columnCount: 4,
      columns: [
        { name: 'RecordTime', index: 0, kind: 'numeric', min: 1, max: 2, mean: 1.5, median: 1.5, p90: 2, sampleCount: 56 },
        { name: 'CPU温度(度)', index: 1, kind: 'numeric', min: 39.3, max: 60, mean: 50.5, median: 50.4, p90: 56.4, sampleCount: 56 },
        { name: 'extra', index: 2, kind: 'skipped', reason: 'contains_non_numeric_values' },
      ],
    }],
  }

  it('CLI files 结构 → 标准形:index=stem::列名,只收 numeric 列,行带 name/file/fileKey', () => {
    const n = normalizePerfSummary(RAW)
    expect(n?.columns).toHaveLength(2) // kind=skipped 不收
    expect(n?.columns?.[0]).toMatchObject({
      index: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789045016565_1789045048339::RecordTime',
      name: 'RecordTime', fileKey: 'Temperature', mean: 1.5, sampleCount: 56,
    })
    expect(n?.columns?.[1]).toMatchObject({
      index: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789045016565_1789045048339::CPU温度(度)',
      name: 'CPU温度(度)', fileKey: 'Temperature', p90: 56.4,
    })
  })

  it('已是标准形 / error / null 原样透传(不二次加工)', () => {
    const std = { columns: [{ index: 'CPU', mean: 1 }] }
    expect(normalizePerfSummary(std)).toBe(std)
    expect(normalizePerfSummary({ error: 'csv 解析失败' })).toEqual({ error: 'csv 解析失败' })
    expect(normalizePerfSummary(null)).toBeNull()
    expect(normalizePerfSummary(undefined)).toBeNull()
  })

  it('空 files → columns 空数组(统计表呈「暂无统计」而非报错)', () => {
    expect(normalizePerfSummary({ files: [] })).toEqual({ columns: [] })
  })
})

describe('buildPerfOptions', () => {
  it('同组(单采集项小样例)仍一个 option:数值列各成一条线,首列时间不画', () => {
    const opts = buildPerfOptions(series)
    expect(opts).toHaveLength(1) // CPU 与 Memo 同组?否:Memo 无数值列被跳过,仅 CPU 一组
    const s = (opts[0] as any).series
    expect(s.map((x: any) => x.name)).toEqual(['total', 'app'])
    expect((opts[0] as any).xAxis.max).toBe(2)
    expect((opts[0] as any).title.text).toBe('CPU')
  })

  it('dataZoom/tooltip/legend 配置齐备(企业级清单)', () => {
    const o = buildPerfOptions(series)[0] as any
    expect(o.dataZoom).toBeTruthy()
    expect(o.tooltip.trigger).toBe('axis')
    expect(o.legend).toBeTruthy()
  })

  it('showRefs + 人工 summary 匹配 → mean/p90 markLine(legacy 兜底路径不变)', () => {
    const summary = { columns: [{ index: 'CPU', mean: 20, p90: 29 }] }
    const o = buildPerfOptions(series, { showRefs: true, summary })[0] as any
    const total = o.series.find((x: any) => x.name === 'total')
    const lines = total.markLine.data
    expect(lines).toHaveLength(2)
    expect(lines[0].yAxis).toBe(20)
    expect(lines[1].lineStyle.type).toBe('dashed')
  })

  it('showRefs 逐列索引按特异性匹配(legacy):total/app 各取己列统计,前缀不遮蔽精确', () => {
    const summary = { columns: [{ index: 'CPU_total', mean: 1, p90: 2 }, { index: 'CPU_app', mean: 10, p90: 20 }] }
    const o = buildPerfOptions(series, { showRefs: true, summary })[0] as any
    const total = o.series.find((x: any) => x.name === 'total')
    const app = o.series.find((x: any) => x.name === 'app')
    expect(total.markLine.data.map((l: any) => l.yAxis)).toEqual([1, 2])
    expect(app.markLine.data.map((l: any) => l.yAxis)).toEqual([10, 20])
  })

  it('无数值列的 item 产出空 option 数组跳过', () => {
    expect(buildPerfOptions([{ item: 'Memo', columns: ['label'], rows: [['x']] }])).toHaveLength(0)
  })
})

describe('buildPerfOptions:真实 51 系列按大类分组(fixtures/series15.json)', () => {
  const s15 = series15 as unknown as AppPerfSeries[]

  it('option 数 = 不同 groupKey 数(51 文件 → 10 图,echarts 实例数受控不再渲染崩)', () => {
    const opts = buildPerfOptions(s15)
    const keys = new Set(s15.map((s) => fileKeyOf(s.item)))
    expect(opts).toHaveLength(keys.size)
    expect(opts.length).toBeLessThanOrEqual(10)
  })

  it('title=大类 key 且不重复;含 Temperature/Network 等采集项', () => {
    const opts = buildPerfOptions(s15)
    const titles = opts.map((o) => (o as any).title.text as string)
    expect(new Set(titles).size).toBe(titles.length)
    expect(titles).toEqual(expect.arrayContaining(['Temperature', 'Network', 'Battery', 'FPS']))
    expect(opts.every((o) => ((o as any).series as unknown[]).length > 0)).toBe(true)
  })

  it('每 option 系列数合计 = 原系列可画线总数(合并不丢线)', () => {
    const opts = buildPerfOptions(s15)
    const drawn = opts.reduce((acc, o) => acc + ((o as any).series as unknown[]).length, 0)
    expect(drawn).toBe(s15.reduce((acc, s) => acc + numericCount(s), 0))
  })

  it('xAxis.max = 组内各系列最大行数-1(组间行数不同取最大)', () => {
    const opts = buildPerfOptions(s15)
    const net = opts.find((o) => (o as any).title.text === 'Network') as any
    const netRows = s15.filter((s) => fileKeyOf(s.item) === 'Network').map((s) => s.rows.length)
    expect(net.xAxis.max).toBe(Math.max(...netRows) - 1)
  })

  it('yAxis 名=大类 key(轴单位不做换算,沿用 ADR-0010)', () => {
    const opts = buildPerfOptions(s15)
    expect(opts.every((o) => (o as any).yAxis.name === (o as any).title.text)).toBe(true)
  })

  it('参考线:归一化 summary 以 <stem>::<列名> 精确命中;同文件兄弟列不串线、缺列不画', () => {
    const temp = s15.find((s) => fileKeyOf(s.item) === 'Temperature')!
    const metricCol = temp.columns[1] // CPU温度(度)
    const summary = normalizePerfSummary({
      files: [{ path: `${temp.item}.csv`, columns: [{ name: metricCol, index: 1, kind: 'numeric', mean: 50.5, p90: 56.4 }] }],
    })
    const opts = buildPerfOptions([temp], { showRefs: true, summary })
    const lines = opts.flatMap((o) => (o as any).series as { name: string; markLine?: { data: { yAxis: number }[] } }[])
    const metric = lines.find((l) => l.name === metricCol)!
    expect(metric.markLine?.data.map((l) => l.yAxis)).toEqual([50.5, 56.4])
    // SimpleTime 不在 summary:精确键未命中即不画(归一化键不退前缀兜底,防同文件兄弟列张冠李戴)
    const simple = lines.find((l) => l.name === 'SimpleTime')!
    expect(simple.markLine?.data ?? []).toHaveLength(0)
  })
})

describe('extractStatRows', () => {
  it('columns → 统计行(消费 normalizePerfSummary 之后的形状);error 摘要返回空', () => {
    expect(extractStatRows({ columns: [{ index: 'CPU', min: 1, max: 3, mean: 2, median: 2, p90: 3 }] }))
      .toEqual([{ index: 'CPU', min: 1, max: 3, mean: 2, median: 2, p90: 3 }])
    // 归一化行的 name/file/fileKey 原样透传为行字段(统计表短形显示的数据源)
    expect(extractStatRows({ columns: [{ index: 'a::b', name: 'b', file: 'a', fileKey: 'K', mean: 1 }] }))
      .toEqual([{ index: 'a::b', name: 'b', file: 'a', fileKey: 'K', mean: 1 }])
    expect(extractStatRows({ error: 'x' })).toEqual([])
    expect(extractStatRows(null)).toEqual([])
  })
})

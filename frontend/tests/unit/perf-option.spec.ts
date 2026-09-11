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

// 与 perfOption 系列构建同口径的本地复算(锁定「合并不丢线」的期望值);
// SimpleTime(精确同名)已改作 X 秒值不再画线,此处同步剔除
const numericCount = (s: AppPerfSeries): number => {
  const isNum = (v: string) => v.trim() !== '' && Number.isFinite(Number(v))
  let n = 0
  for (let c = 1; c < s.columns.length; c++) {
    if (s.columns[c] === 'SimpleTime') continue
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
    expect(s[0].data).toEqual([[0, 10], [1, 20], [2, 30]]) // 无 SimpleTime → X=采样序号
    expect((opts[0] as any).xAxis.name).toBe('采样点')
  })

  it('白底治叠影:每个 option backgroundColor=#fff(canvas 默认透明,子图与下层页面互相透出=标题重影)', () => {
    const opts = buildPerfOptions(series)
    expect(opts.length).toBeGreaterThan(0)
    expect(opts.every((o) => (o as any).backgroundColor === '#fff')).toBe(true)
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

describe('buildPerfOptions:SimpleTime 时间轴 + 采样聚合(冒烟反馈修 2)', () => {
  // 真实 SoloPi CSV 四列形态:RecordTime(epoch ms)/指标列/extra(字符串 "null")/SimpleTime(秒)
  const timed: AppPerfSeries[] = [{
    item: 'CPU温度_Temperature_x_1_2',
    columns: ['RecordTime', 'CPU温度(度)', 'extra', 'SimpleTime'],
    rows: [
      ['1789045017067', '39.3', 'null', '0.5'],
      ['1789045018067', '41.1', 'null', '1.5'],
      ['1789045019067', '43.7', 'null', '2.5'],
    ],
  }]

  it('SimpleTime 列不画线(图例无 SimpleTime),提取为该系列 X 秒值:首点 x=秒值', () => {
    const o = buildPerfOptions(timed)[0] as any
    expect(o.series.map((s: any) => s.name)).toEqual(['CPU温度(度)']) // SimpleTime 不在系列名
    expect(o.series[0].data[0]).toEqual([0.5, 39.3])
    expect(o.xAxis.name).toBe('时间 (秒)')
    expect(o.xAxis.max).toBe(2.5) // 组内最大 x=最大秒值
  })

  it('无 SimpleTime 列 → X 回退采样序号 0..n-1,xAxis.name=采样点(旧行为等价)', () => {
    const o = buildPerfOptions(series)[0] as any
    expect(o.series[0].data[0]).toEqual([0, 10])
    expect(o.xAxis.name).toBe('采样点')
  })

  it('SimpleTime 列含非数值(如字符串 "null")→ 整系列回退采样序号', () => {
    const bad: AppPerfSeries[] = [{
      item: 'CPU温度_Temperature_y_1_2',
      columns: ['RecordTime', 'v', 'extra', 'SimpleTime'],
      rows: [['1', '10', 'null', '0.5'], ['2', '20', 'null', 'null']],
    }]
    const o = buildPerfOptions(bad)[0] as any
    expect(o.series[0].data.map((d: unknown[]) => d[0])).toEqual([0, 1])
    expect(o.xAxis.name).toBe('采样点')
  })

  it('组内混排(部分系列带 SimpleTime)→ 以秒为准(任一系列带 SimpleTime 即 name=时间 (秒))', () => {
    const mixed: AppPerfSeries[] = [
      ...timed,
      { item: 'CPU占用_Temperature_z_1_2', columns: ['RecordTime', 'v'], rows: [['1', '5'], ['2', '6'], ['3', '7']] },
    ]
    const o = buildPerfOptions(mixed)[0] as any
    expect(o.series).toHaveLength(2)
    expect(o.xAxis.name).toBe('时间 (秒)')
    expect(o.series[1].data[0]).toEqual([0, 5]) // 无 SimpleTime 的系列自身仍回退序号
  })

  it('bucketSec=60:x 均为 60 倍数(桶起点),桶内 y 取算术均值,按桶起点升序', () => {
    const mk = (rows: string[][]): AppPerfSeries[] => [{
      item: 'CPU温度_Temperature_b_1_2',
      columns: ['RecordTime', 'v', 'extra', 'SimpleTime'],
      rows,
    }]
    // 计划样例:x=30(y=10)、x=90(y=20)→ 桶 0 均值 10、桶 60 均值 20
    const o1 = buildPerfOptions(mk([['1', '10', 'null', '30'], ['2', '20', 'null', '90']]), { bucketSec: 60 })[0] as any
    expect(o1.series[0].data).toEqual([[0, 10], [60, 20]])
    // 多点同桶:x=70(y=30)、x=90(y=20)同落桶 60 → 均值 25
    const o2 = buildPerfOptions(mk([['1', '30', 'null', '70'], ['2', '20', 'null', '90']]), { bucketSec: 60 })[0] as any
    expect(o2.series[0].data).toEqual([[60, 25]])
  })

  it('bucketSec 缺省/0 → 原始全采样(X 原样逐点)', () => {
    for (const bucketSec of [undefined, 0] as const) {
      const o = buildPerfOptions(timed, { bucketSec })[0] as any
      expect(o.series[0].data).toEqual([[0.5, 39.3], [1.5, 41.1], [2.5, 43.7]])
    }
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

  it('xAxis.max = 组内最大 SimpleTime 秒值(真实秒数,非行数-1)', () => {
    const opts = buildPerfOptions(s15)
    const mem = opts.find((o) => (o as any).title.text === 'Memory') as any
    // fixture 实测:Memory 组最大 SimpleTime=31.766 秒(0.501 起相对采集起始);
    // 旧行为取行数-1(整数,Memory 组最长 63 行 → 62),秒轴下断然不等
    expect(mem.xAxis.max).toBeGreaterThan(31)
    expect(mem.xAxis.max).toBeLessThan(35)
    expect(mem.xAxis.max).toBe(31.766)
  })

  it('全系列不再有名为 SimpleTime 的系列(SimpleTime 改作 X 秒值)', () => {
    const opts = buildPerfOptions(s15)
    const names = opts.flatMap((o) => ((o as any).series as { name: string }[]).map((s) => s.name))
    expect(names).not.toContain('SimpleTime')
  })

  it('yAxis.name 置空(超长文件 stem 竖排乱字下线,子图含义由 title=采集大类承担)', () => {
    const opts = buildPerfOptions(s15)
    expect(opts.every((o) => (o as any).yAxis.name === '')).toBe(true)
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
    // SimpleTime 已不画线(改作 X 秒值),参考线匹配无从谈起
    expect(lines.find((l) => l.name === 'SimpleTime')).toBeUndefined()
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

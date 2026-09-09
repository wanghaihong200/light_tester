// tests/unit/perf-option.spec.ts
import { describe, expect, it } from 'vitest'
import { buildPerfOptions, extractStatRows } from '../../src/components/perf/perfOption'

const series = [
  { item: 'CPU', columns: ['ts', 'total', 'app'], rows: [['0', '10', '5'], ['1', '20', '8'], ['2', '30', '11']] },
  { item: 'Memo', columns: ['label'], rows: [['non-numeric']] }, // 无数值列 → 无子图
]

describe('buildPerfOptions', () => {
  it('每个采集项一个 option,数值列各成一条线,首列时间不画', () => {
    const opts = buildPerfOptions(series)
    expect(opts).toHaveLength(1)
    const s = (opts[0] as any).series
    expect(s.map((x: any) => x.name)).toEqual(['total', 'app'])
    expect((opts[0] as any).xAxis.max).toBe(2)
  })

  it('dataZoom/tooltip/legend 配置齐备(企业级清单)', () => {
    const o = buildPerfOptions(series)[0] as any
    expect(o.dataZoom).toBeTruthy()
    expect(o.tooltip.trigger).toBe('axis')
    expect(o.legend).toBeTruthy()
  })

  it('showRefs + summary 匹配 → mean/p90 markLine', () => {
    const summary = { columns: [{ index: 'CPU', mean: 20, p90: 29 }] }
    const o = buildPerfOptions(series, { showRefs: true, summary })[0] as any
    const total = o.series.find((x: any) => x.name === 'total')
    const lines = total.markLine.data
    expect(lines).toHaveLength(2)
    expect(lines[0].yAxis).toBe(20)
    expect(lines[1].lineStyle.type).toBe('dashed')
  })

  it('showRefs 逐列索引按特异性匹配:total/app 各取己列统计,前缀不遮蔽精确', () => {
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

describe('extractStatRows', () => {
  it('columns → 统计行;error 摘要返回空', () => {
    expect(extractStatRows({ columns: [{ index: 'CPU', min: 1, max: 3, mean: 2, median: 2, p90: 3 }] }))
      .toEqual([{ index: 'CPU', min: 1, max: 3, mean: 2, median: 2, p90: 3 }])
    expect(extractStatRows({ error: 'x' })).toEqual([])
    expect(extractStatRows(null)).toEqual([])
  })
})

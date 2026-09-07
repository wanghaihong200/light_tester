import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PerfChart from '../../src/components/appauto/PerfChart.vue'

describe('PerfChart', () => {
  it('数值列渲染折线点,非数值整列跳过', () => {
    const w = mount(PerfChart, { props: { series: [
      { item: 'CPU', columns: ['时间', 'CPU(%)'], rows: [['10:00', '12.5'], ['10:01', '50'], ['10:02', '0']] },
      { item: 'Status', columns: ['时间', '状态'], rows: [['10:00', 'ok']] },
    ] } })
    const points = w.findAll('polyline')
    expect(points).toHaveLength(1) // 仅 CPU 有数值列
    expect(points[0].attributes('points')!.split(' ')).toHaveLength(3)
    expect(w.text()).toContain('CPU')
    expect(w.text()).toContain('Status(无数值列)') // 非数值整列在图例中标注跳过
  })
})

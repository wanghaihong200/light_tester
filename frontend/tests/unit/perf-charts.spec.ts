// tests/unit/perf-charts.spec.ts
// echarts 在 jsdom 无 canvas:mock 掉 echarts/*,只验证组件编排(init/setOption/connect/导出/空态)
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ElementPlus from 'element-plus'

const setOption = vi.fn()
const mockChart = {
  setOption,
  dispose: vi.fn(),
  resize: vi.fn(),
  getOption: vi.fn(() => ({})),
  getDataURL: vi.fn(() => 'data:image/png;base64,AAA'),
}
vi.mock('echarts/core', () => ({
  init: vi.fn(() => mockChart),
  use: vi.fn(),
  connect: vi.fn(),
}))
vi.mock('echarts/charts', () => ({ LineChart: {} }))
vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  DataZoomComponent: {},
  MarkLineComponent: {},
  TitleComponent: {},
}))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

import PerfCharts from '../../src/components/perf/PerfCharts.vue'

const series = [{ item: 'CPU', columns: ['ts', 'total'], rows: [['0', '10'], ['1', '20']] }]

// el-* 组件装真 Element Plus(对齐 appauto-pane.spec 形态),否则 data-test 落不到真实控件上
const mountCharts = (props: Record<string, unknown>) =>
  mount(PerfCharts, { props, global: { plugins: [ElementPlus] } })

describe('PerfCharts', () => {
  beforeEach(() => {
    setOption.mockClear()
    mockChart.dispose.mockClear()
  })

  it('按 option 数量 setOption(多子图),show-refs 透传', async () => {
    const w = mountCharts({ series, summary: { columns: [{ index: 'CPU', mean: 15 }] }, showRefs: false })
    await nextTick() // 首渲染在挂载后异步完成(host 随 hasCharts 出现)
    expect(setOption).toHaveBeenCalledTimes(1)
    expect((setOption.mock.calls[0][0] as any).series[0].markLine).toBeUndefined() // showRefs=false 不带参考线
    // jsdom 对 label 点击转发不稳:直击 input 触发 v-model(选择器仍锚定 data-test 元素)
    await w.find('[data-test="toggle-refs"] input').setValue(true)
    expect(setOption).toHaveBeenCalledTimes(2)
    const lines = (setOption.mock.calls[1][0] as any).series[0].markLine?.data ?? []
    expect(lines.map((l: any) => l.yAxis)).toContain(15) // refsOn 透传给 buildPerfOptions
    expect(w.find('[data-test="toggle-refs"]').exists()).toBe(true)
    w.unmount()
  })

  it('PNG 导出触发 a 标签下载', async () => {
    const w = mountCharts({ series, summary: null, showRefs: false })
    await nextTick() // instances 就绪后才有 getDataURL 可导
    const click = vi.fn()
    const orig = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = orig(tag) as HTMLAnchorElement
      if (tag === 'a') el.click = click
      return el
    })
    await w.find('[data-test="export-png"]').trigger('click')
    expect(click).toHaveBeenCalled()
    vi.restoreAllMocks()
    w.unmount()
  })

  it('空 series 渲染空态文案', () => {
    const w = mountCharts({ series: [], summary: null, showRefs: false })
    expect(w.text()).toContain('暂无性能数据')
    w.unmount()
  })

  it('命令式创建的子 div 必须带内联高度(scoped CSS 匹配不到,0 高画布=空白图)', async () => {
    const w = mountCharts({ series, summary: null, showRefs: false })
    await nextTick()
    await nextTick()
    const host = w.find('.charts')
    expect(host.exists()).toBe(true)
    const subs = host.element.querySelectorAll(':scope > div')
    expect(subs.length).toBeGreaterThan(0)
    subs.forEach((el) => {
      expect(el.style.height).toBe('240px')
      expect(el.style.width).toBe('100%')
    })
    w.unmount()
  })
})

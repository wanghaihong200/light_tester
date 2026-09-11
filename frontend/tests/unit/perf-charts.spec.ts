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
  // 每实例独立对象:getDom 返回 init 入参的 chart div(导出拼长图按它找子图 canvas)
  init: vi.fn((el: HTMLElement) => ({ ...mockChart, getDom: () => el })),
  use: vi.fn(),
  connect: vi.fn(), // 保留为 spy:断言组件不再调用(connect 联动经用户实测裁撤)
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
import * as echartsCore from 'echarts/core'

const connectMock = echartsCore.connect as unknown as ReturnType<typeof vi.fn>

const series = [{ item: 'CPU', columns: ['ts', 'total'], rows: [['0', '10'], ['1', '20']] }]

// el-* 组件装真 Element Plus(对齐 appauto-pane.spec 形态),否则 data-test 落不到真实控件上
const mountCharts = (props: Record<string, unknown>) =>
  mount(PerfCharts, { props, global: { plugins: [ElementPlus] } })

describe('PerfCharts', () => {
  beforeEach(() => {
    setOption.mockClear()
    mockChart.dispose.mockClear()
    connectMock.mockClear()
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

  it('PNG 导出改为全部子图拼长图:白底、逐子图纵向 drawImage、不经实例 getDataURL', async () => {
    // 两个采集项 → 两个子图 → 两个 wrapper
    const two = [
      { item: 'CPU', columns: ['ts', 'total'], rows: [['0', '10'], ['1', '20']] },
      { item: 'Memory', columns: ['ts', 'total'], rows: [['0', '30'], ['1', '40']] },
    ]
    const w = mountCharts({ series: two, summary: null, showRefs: false })
    await nextTick()
    await nextTick()
    // jsdom 无 echarts 真画布:给每个子图 chart div 塞一个带物理尺寸的真实 canvas 节点当导出源
    const srcCanvases: HTMLCanvasElement[] = []
    w.element.querySelectorAll('.charts > div > div').forEach((cd) => {
      const cv = document.createElement('canvas')
      cv.width = 300
      cv.height = srcCanvases.length === 0 ? 240 : 150 // 两子图等宽不等高,验证高度求和与纵向偏移
      cd.appendChild(cv)
      srcCanvases.push(cv)
    })
    const click = vi.fn()
    const anchors: HTMLAnchorElement[] = []
    const ctx2d = { fillStyle: '', fillRect: vi.fn(), drawImage: vi.fn() }
    const orig = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = orig(tag) as HTMLCanvasElement & { getContext?: unknown; toDataURL?: unknown }
      if (tag === 'a') { el.click = click; anchors.push(el) }
      if (tag === 'canvas') { // 离屏拼接画布:提供 2d 上下文与 dataURL(jsdom 真 canvas 无 2d)
        el.getContext = () => ctx2d
        el.toDataURL = () => 'data:image/png;base64,BBB'
      }
      return el
    })
    await w.find('[data-test="export-png"]').trigger('click')
    expect(mockChart.getDataURL).not.toHaveBeenCalled() // 全量导出走 canvas 拼接,不再逐实例 getDataURL
    expect(anchors).toHaveLength(1)
    expect(anchors[0].download).toBe('perf-charts.png')
    expect(anchors[0].href).toContain('data:image/png;base64,BBB')
    expect(ctx2d.fillStyle).toBe('#fff') // 白底
    expect(ctx2d.fillRect).toHaveBeenCalledWith(0, 0, 300, 390) // 全底填充:宽=首图宽,高=各子图高之和
    expect(ctx2d.drawImage.mock.calls.map((c) => [c[0], c[1], c[2]])).toEqual([
      [srcCanvases[0], 0, 0],
      [srcCanvases[1], 0, 240], // 纵向堆叠:y 累加前面的子图高
    ])
    vi.restoreAllMocks()
    w.unmount()
  })

  it('导出在拿不到 2d 上下文时(jsdom/异常环境)静默降级:不抛错、不触发下载', async () => {
    const w = mountCharts({ series, summary: null, showRefs: false })
    await nextTick()
    await nextTick()
    const cv = document.createElement('canvas') // 真实 jsdom canvas:getContext('2d') 返回 null
    cv.width = 300
    cv.height = 240
    w.element.querySelector('.charts > div > div')?.appendChild(cv)
    const createSpy = vi.spyOn(document, 'createElement') // 记录建了什么,不改行为
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    await w.find('[data-test="export-png"]').trigger('click')
    expect(mockChart.getDataURL).not.toHaveBeenCalled()
    const noAnchor = createSpy.mock.calls.every(([tag]) => tag !== 'a') // 静默 return,没走到下载
    expect(noAnchor).toBe(true)
    vi.restoreAllMocks()
    w.unmount()
  })

  it('空 series 渲染空态文案', () => {
    const w = mountCharts({ series: [], summary: null, showRefs: false })
    expect(w.text()).toContain('暂无性能数据')
    w.unmount()
  })

  it('命令式创建的子图 wrapper 必须带内联高度(scoped CSS 匹配不到,0 高画布=空白图)', async () => {
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

  it('每个子图包 wrapper(relative)+ 内嵌 chart div(撑满)+ 右上角独立下载小按钮', async () => {
    const w = mountCharts({ series, summary: null, showRefs: false })
    await nextTick()
    await nextTick()
    const wrappers = w.element.querySelectorAll('.charts > div')
    expect(wrappers.length).toBe(1)
    const chartDiv = wrappers[0].firstElementChild as HTMLElement
    expect(chartDiv.tagName).toBe('DIV') // echarts.init 的目标是 wrapper 内的 chart div
    expect(chartDiv.style.width).toBe('100%')
    expect(chartDiv.style.height).toBe('100%')
    const btn = wrappers[0].querySelector('button')
    expect(btn).toBeTruthy() // 每个子图一个下载钮
    expect(btn!.style.position).toBe('absolute')
    expect(btn!.style.top).toBe('28px') // 偏移避开顶部图例(legend top:2)
    expect(btn!.style.right).toBe('4px')
    expect(btn!.textContent).toBe('⬇')
    expect(btn!.title).toBe('下载本子图 PNG')
    w.unmount()
  })

  it('子图下载按钮:点击走该实例 getDataURL(白底 2x)触发 a 下载,文件名取子图 title 清洗', async () => {
    const w = mountCharts({ series, summary: null, showRefs: false })
    await nextTick()
    await nextTick()
    const click = vi.fn()
    const anchors: HTMLAnchorElement[] = []
    const orig = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = orig(tag) as HTMLAnchorElement
      if (tag === 'a') { el.click = click; anchors.push(el) }
      return el
    })
    const btn = w.element.querySelector('.charts > div > button') as HTMLButtonElement
    btn.click()
    expect(mockChart.getDataURL).toHaveBeenCalledWith({ pixelRatio: 2, backgroundColor: '#fff' })
    expect(anchors).toHaveLength(1)
    expect(anchors[0].download).toBe('perf-chart-CPU.png') // title.text='CPU' → 清洗后即文件名
    expect(anchors[0].href).toBe('data:image/png;base64,AAA')
    vi.restoreAllMocks()
    w.unmount()
  })

  it('connect 联动经用户实测裁撤:渲染后不调 echarts.connect(悬停只看当前子图)', async () => {
    const w = mountCharts({ series, summary: null, showRefs: false })
    await nextTick()
    await nextTick()
    expect(setOption).toHaveBeenCalled()
    expect(connectMock).not.toHaveBeenCalled()
    w.unmount()
  })

  it('聚合时长下拉:切换 bucket 后 setOption 重渲染,线数据按桶聚合(默认原始采样)', async () => {
    const timed = [{
      item: 'CPU温度_Temperature_x_1_2',
      columns: ['RecordTime', 'v', 'extra', 'SimpleTime'],
      rows: [['1', '10', 'null', '0.5'], ['2', '20', 'null', '1.5']],
    }]
    const w = mountCharts({ series: timed, summary: null, showRefs: false })
    await nextTick()
    expect(setOption).toHaveBeenCalledTimes(1)
    expect((setOption.mock.calls[0][0] as any).series[0].data).toEqual([[0.5, 10], [1.5, 20]]) // 原始采样
    expect(w.find('[data-test="bucket-select"]').exists()).toBe(true)
    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 300)
    await nextTick()
    await nextTick()
    expect(setOption).toHaveBeenCalledTimes(2)
    // 0.5/1.5 秒同落桶 0(桶宽 300s)→ x=桶起点 0,y=算术均值 15
    expect((setOption.mock.calls[1][0] as any).series[0].data).toEqual([[0, 15]])
    w.unmount()
  })
})

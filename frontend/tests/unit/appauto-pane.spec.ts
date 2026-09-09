import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// ComparisonDialog 换芯后内嵌 PerfCharts(echarts 在 jsdom 无 canvas,mock 形态沿 perf-record-pane.spec)
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

const api = vi.hoisted(() => ({
  listAppScripts: vi.fn(),
  deleteAppScript: vi.fn(),
  listAppRuns: vi.fn(),
  listAppDevices: vi.fn(),
  listDeviceCases: vi.fn(),
  importDeviceCase: vi.fn(),
  // 占位对齐 webauto 预防式写法:后续用例直调上传导入时不因 mock 缺键而 undefined 调用
  importUploadCase: vi.fn(),
  // ComparisonDialog 换芯(计划14 Task12)新增依赖
  getAppComparison: vi.fn(),
  getAppRunPerfSeries: vi.fn(),
}))

vi.mock('../../src/api/appAutomation', () => api)

import AppAutoPane from '../../src/components/appauto/AppAutoPane.vue'
import ImportDialog from '../../src/components/appauto/ImportDialog.vue'
import PerfCharts from '../../src/components/perf/PerfCharts.vue'
import PerfSummaryTable from '../../src/components/perf/PerfSummaryTable.vue'

const SCRIPT = {
  id: 7, project_id: 1, name: '下单冒烟', description: null,
  case_json: { caseName: '下单冒烟', targetAppPackage: 'com.example.shop',
               operationLog: { steps: [{}, {}] } },
  app_package: 'com.example.shop', created_at: '2026-09-07T10:00:00', updated_at: '2026-09-07T10:00:00',
}
const RUN = {
  id: 11, project_id: 1, status: 'passed', script_id: 7, script_name: '下单冒烟',
  device_serial: 'DEV-A', batch_id: null, variables: {}, pre_checks: [], post_checks: [],
  perf_items: [], run_state: 'passed', results: null, check_results: null, perf_summary: null,
  startup_summary: null, error: null, started_at: null, finished_at: null,
}

// el-table 作用域插槽形态对齐 tests/unit/webauto-pane.spec.ts 现状:装真 Element Plus,
// 不桩 el-table/el-table-column/el-dialog(手写桩无法给 #default="{ row }" 提供 row,会解构报错)
const mountPane = () =>
  mount(AppAutoPane, {
    props: { projectId: 1 },
    global: { plugins: [ElementPlus] },
  })

describe('AppAutoPane', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listAppScripts.mockResolvedValue([SCRIPT])
    api.listAppRuns.mockResolvedValue([RUN])
    api.listAppDevices.mockResolvedValue([{ serial: 'DEV-A', state: 'device' }])
    api.listDeviceCases.mockResolvedValue([{ file_name: 'case_a.json', source: 'harness' }])
  })

  it('加载脚本与运行历史', async () => {
    const w = mountPane()
    await flushPromises()
    expect(api.listAppScripts).toHaveBeenCalledWith(1)
    expect(api.listAppRuns).toHaveBeenCalledWith(1, {})
    expect(w.text()).toContain('下单冒烟')
    expect(w.text()).toContain('DEV-A')
  })

  it('删除脚本确认后调 API 并刷新', async () => {
    api.deleteAppScript.mockResolvedValue(undefined)
    const w = mountPane()
    await flushPromises()
    ;(w.vm as any).onDelete(SCRIPT)
    await (w.vm as any).doDelete()
    await flushPromises()
    expect(api.deleteAppScript).toHaveBeenCalledWith(7)
    expect(api.listAppScripts).toHaveBeenCalledTimes(2)
  })

  it('导入成功事件触发脚本列表刷新', async () => {
    api.importDeviceCase.mockResolvedValue(SCRIPT)
    const w = mountPane()
    await flushPromises()
    w.findComponent(ImportDialog).vm.$emit('imported', SCRIPT)
    await flushPromises()
    expect(api.listAppScripts).toHaveBeenCalledTimes(2)  // 挂载 1 次 + 导入后刷新 1 次
  })
})

// ── ComparisonDialog 换芯(计划14 Task12):统计表取代 JSON 折叠 + 曲线叠加带设备前缀 ──
const PERF_SUMMARY = { columns: [{ index: 'CPU', sampleCount: 2, min: 10, max: 20, mean: 15, median: 15, p90: 19 }] }
const RUN_PERF = (id: number, serial: string, withSummary: boolean) => ({
  ...RUN, id, batch_id: 'B-1', device_serial: serial,
  perf_summary: withSummary ? PERF_SUMMARY : null,
})
const SERIES = { item: 'CPU', columns: ['ts', 'total'], rows: [['0', '10'], ['1', '20']] }

// 第一个 el-table 是脚本列表,其后是执行历史;打开对比弹窗取执行历史行内的「对比」入口
const openComparison = async (w: ReturnType<typeof mountPane>) => {
  const btn = w.findAll('.el-table__row')[1]?.findAll('button').find((b) => b.text().includes('对比'))
  expect(btn, '执行历史行应有「对比」入口').toBeTruthy()
  await btn!.trigger('click')
  await flushPromises()
  await flushPromises()  // onMounted: getAppComparison → allSettled(拉 series) 链式微任务
}

describe('ComparisonDialog 换芯', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listAppScripts.mockResolvedValue([SCRIPT])
    api.listAppRuns.mockResolvedValue([])
    api.listAppDevices.mockResolvedValue([])
    api.listDeviceCases.mockResolvedValue([])
  })

  it('性能汇总列渲染统计表而非 <pre> JSON;曲线叠加单图合并且 item 名带设备前缀', async () => {
    const runs = [RUN_PERF(21, 'DEV-A', true), RUN_PERF(22, 'DEV-B', true), RUN_PERF(23, 'DEV-C', false)]
    api.listAppRuns.mockResolvedValue(runs)
    api.getAppComparison.mockResolvedValue({ batch_id: 'B-1', script_id: 7, script_name: '下单冒烟', runs })
    api.getAppRunPerfSeries
      .mockResolvedValueOnce({ series: [SERIES] })
      .mockResolvedValueOnce({ series: [SERIES] })  // 同 item 跨设备 → 靠前缀区分

    const w = mountPane()
    await flushPromises()
    await openComparison(w)

    // ① 性能汇总列:PerfSummaryTable 组件取代 <pre> JSON 折叠(有 perf_summary 的行才有,无则 —)
    expect(w.findComponent(PerfSummaryTable).exists()).toBe(true)
    expect(w.text()).not.toContain('展开')
    expect(w.find('pre').exists()).toBe(false)
    // ② 性能曲线叠加:区块存在,单个 PerfCharts 合并全部 series,item 前缀=设备号
    expect(w.find('[data-test="compare-perf-charts"]').exists()).toBe(true)
    // 无 perf_summary 的 run(23)不拉曲线
    expect(api.getAppRunPerfSeries).toHaveBeenCalledTimes(2)
    expect(api.getAppRunPerfSeries).toHaveBeenNthCalledWith(1, 21)
    expect(api.getAppRunPerfSeries).toHaveBeenNthCalledWith(2, 22)
    const charts = w.findAllComponents(PerfCharts)
    expect(charts).toHaveLength(1)
    expect(charts[0].props('series')).toEqual([
      { ...SERIES, item: 'DEV-A · CPU' },
      { ...SERIES, item: 'DEV-B · CPU' },
    ])
    w.unmount()
  })

  it('曲线拉取失败静默跳过:全部失败时叠加区块不渲染,弹窗与汇总表不受影响', async () => {
    const runs = [RUN_PERF(21, 'DEV-A', true)]
    api.listAppRuns.mockResolvedValue(runs)
    api.getAppComparison.mockResolvedValue({ batch_id: 'B-1', script_id: 7, script_name: '下单冒烟', runs })
    api.getAppRunPerfSeries.mockRejectedValue(new Error('boom'))

    const w = mountPane()
    await flushPromises()
    await openComparison(w)

    expect(w.find('[data-test="compare-perf-charts"]').exists()).toBe(false)
    expect(w.findComponent(PerfCharts).exists()).toBe(false)
    expect(w.findComponent(PerfSummaryTable).exists()).toBe(true)
    w.unmount()
  })
})

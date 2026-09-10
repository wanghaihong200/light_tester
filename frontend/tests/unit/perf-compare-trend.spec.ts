// tests/unit/perf-compare-trend.spec.ts
// 跨记录对比 PerfCompareDialog + 趋势 PerfTrendDialog(计划14 Task11)
// echarts mock 沿 perf-charts.spec(jsdom 无 canvas,只验 option 组装与编排);
// ElementPlus 全量插件 + ResizeObserver stub 沿 perf-record-pane.spec
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// jsdom 无 ResizeObserver,el-table 依赖其测量列宽(mindmap-editor.spec 同款 stub)
vi.stubGlobal('ResizeObserver', class { observe() { /* noop */ } unobserve() { /* noop */ } disconnect() { /* noop */ } })

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
  listPerfRecords: vi.fn(),
  comparePerfRecords: vi.fn(),
  getPerfTrend: vi.fn(),
}))
vi.mock('../../src/api/perf', () => api)

import PerfCompareDialog from '../../src/components/perf/PerfCompareDialog.vue'
import PerfTrendDialog from '../../src/components/perf/PerfTrendDialog.vue'
import type { AppPerfSeries, PerfRecord, TrendGroup } from '../../src/types'

// ── fixtures ─────────────────────────────────────────
function mkRecord(over: Partial<PerfRecord> = {}): PerfRecord {
  return {
    id: 1, project_id: 1, source: 'run', source_ref: null, name: '场景A@dev1', app_run_id: 5,
    script_id: 9, script_name: '场景A', device_serial: 'dev1', perf_items: ['CPU'],
    data_complete: true, perf_summary: null, started_at: null, finished_at: '2026-09-09T10:00:00',
    created_at: '2026-09-09T10:00:00',
    ...over,
  }
}

// 记录A 只有 CPU 统计;记录B 有 CPU+FPS(CPU 行数更多,验证合并后 xAxis.max 取最大)
const REC_A = mkRecord({
  id: 11, name: '记录A', perf_items: ['CPU'],
  perf_summary: { columns: [{ index: 'CPU', mean: 15, p90: 19 }] },
})
const REC_B = mkRecord({
  id: 12, name: '记录B', device_serial: 'dev2', perf_items: ['CPU', 'FPS'],
  perf_summary: { columns: [{ index: 'CPU', mean: 25, p90: 30 }, { index: 'FPS', mean: 55, p90: 58 }] },
})

const SERIES_A: AppPerfSeries[] = [{ item: 'CPU', columns: ['ts', 'total'], rows: [['0', '10'], ['1', '20']] }]
const SERIES_B: AppPerfSeries[] = [
  { item: 'CPU', columns: ['ts', 'total'], rows: [['0', '30'], ['1', '40'], ['2', '50']] },
  { item: 'FPS', columns: ['ts', 'fps'], rows: [['0', '60'], ['1', '61'], ['2', '62']] },
]

const mountCompare = (recordIds: number[] = [11, 12]) =>
  mount(PerfCompareDialog, {
    props: { projectId: 1, recordIds },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })

describe('PerfCompareDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.comparePerfRecords.mockResolvedValue({
      records: [REC_A, REC_B],
      series: { '11': SERIES_A, '12': SERIES_B },
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('开窗调 comparePerfRecords;同 item 叠加为一个子图且系列名带记录名前缀,item 取并集', async () => {
    const w = mountCompare()
    await flushPromises()
    expect(api.comparePerfRecords).toHaveBeenCalledWith(1, [11, 12])
    // item 并集 = CPU(两记录都有)+ FPS(仅记录B)→ 2 个子图各一次 setOption
    expect(setOption).toHaveBeenCalledTimes(2)
    const cpu = setOption.mock.calls[0][0] as any
    expect(cpu.title.text).toBe('CPU')
    expect(cpu.series.map((s: any) => s.name)).toEqual(['记录A · total', '记录B · total'])
    // 两记录行数不同(2 行 vs 3 行):合并后 xAxis.max 取最大(=2),min 仍 0
    expect(cpu.xAxis.max).toBe(2)
    expect(cpu.xAxis.min).toBe(0)
    const fps = setOption.mock.calls[1][0] as any
    expect(fps.title.text).toBe('FPS')
    // 记录A 缺 FPS:该子图只有记录B 的系列
    expect(fps.series.map((s: any) => s.name)).toEqual(['记录B · fps'])
    w.unmount()
    expect(mockChart.dispose).toHaveBeenCalled() // 卸载释放实例
  })

  it('统计对比表:行=各记录 columns index 并集,列=各记录名,单元格 mean/p90 并列、缺失补 —', async () => {
    const w = mountCompare()
    await flushPromises()
    const table = w.find('[data-test="compare-stat-table"]')
    expect(table.exists()).toBe(true)
    const trs = table.findAll('.el-table__row')
    expect(trs).toHaveLength(2)
    expect(trs[0].text()).toContain('CPU')
    expect(trs[0].text()).toContain('15.00 / 19.00') // 记录A
    expect(trs[0].text()).toContain('25.00 / 30.00') // 记录B
    expect(trs[1].text()).toContain('FPS')
    expect(trs[1].text()).toContain('—') // 记录A 无 FPS 统计
    expect(trs[1].text()).toContain('55.00 / 58.00') // 记录B
    w.unmount()
  })

  it('perf_summary 为 CLI 真实结构({files})时先归一再并列统计(冒烟修复)', async () => {
    const REC_FILES = mkRecord({
      id: 15, name: '真实结构', device_serial: 'dev9',
      perf_summary: {
        files: [{
          path: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789.csv',
          columns: [
            { name: 'CPU温度(度)', index: 1, kind: 'numeric', mean: 50.5, p90: 56.4 },
            { name: 'extra', index: 2, kind: 'skipped' },
          ],
        }],
      },
    })
    api.comparePerfRecords.mockResolvedValue({ records: [REC_FILES], series: { '15': [] } })
    const w = mountCompare([15])
    await flushPromises()
    const trs = w.find('[data-test="compare-stat-table"]').findAll('.el-table__row')
    expect(trs).toHaveLength(1) // skipped 列不并列
    expect(trs[0].text()).toContain('CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789::CPU温度(度)')
    expect(trs[0].text()).toContain('50.50 / 56.40')
    w.unmount()
  })

  it('全部记录无可用曲线:图表区空态,不 init', async () => {
    api.comparePerfRecords.mockResolvedValue({ records: [REC_A], series: { '11': [] } })
    const w = mountCompare([11])
    await flushPromises()
    expect(setOption).not.toHaveBeenCalled()
    expect(w.find('[data-test="charts-empty"]').exists()).toBe(true)
    w.unmount()
  })

  it('接口失败:error 提示并关窗,不渲染图表', async () => {
    api.comparePerfRecords.mockRejectedValue(new Error('记录不存在'))
    const errSpy = vi.spyOn(ElMessage, 'error').mockReturnValue({} as never)
    const w = mountCompare()
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('加载对比数据失败:记录不存在')
    expect(w.emitted('close')).toBeTruthy()
    expect(setOption).not.toHaveBeenCalled()
    w.unmount()
  })
})

// ── 趋势 ─────────────────────────────────────────────
const RUN_A = mkRecord({ id: 11, source: 'run', script_id: 9, script_name: '场景A', device_serial: 'dev1' })
const RUN_B = mkRecord({ id: 13, source: 'run', script_id: 10, script_name: '场景B', device_serial: 'dev2' })
const IMP_C = mkRecord({
  id: 14, source: 'import', source_ref: 'h1', name: '导入C',
  script_id: null, script_name: '', device_serial: 'dev3',
})

const TREND_GROUPS: TrendGroup[] = [
  {
    script_id: 9, script_name: '场景A', device_serial: 'dev1',
    points: [
      { record_id: 11, finished_at: '2026-09-01T10:00:00', series: { CPU: { mean: 15, p90: 19 } } },
      { record_id: 12, finished_at: '2026-09-02T11:30:00', series: { CPU: { mean: 18, p90: 22 } } },
    ],
  },
  { script_id: 10, script_name: '场景B', device_serial: 'dev2', points: [] },
]

const mountTrend = () =>
  mount(PerfTrendDialog, {
    props: { projectId: 1 },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })

describe('PerfTrendDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listPerfRecords.mockResolvedValue([RUN_A, RUN_B, IMP_C])
    api.getPerfTrend.mockResolvedValue({ groups: TREND_GROUPS })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('筛选下拉取 run 记录去重(脚本/设备),import 来源与空脚本不进选项', async () => {
    const w = mountTrend()
    await flushPromises()
    expect(api.listPerfRecords).toHaveBeenCalledWith(1, { source: 'run' })
    const labels = w.findAllComponents({ name: 'ElOption' }).map((o) => o.props('label'))
    expect(labels).toContain('全部脚本')
    expect(labels).toContain('场景A')
    expect(labels).toContain('场景B')
    expect(labels).toContain('全部设备')
    expect(labels).toContain('dev1')
    expect(labels).toContain('dev2')
    expect(labels).not.toContain('dev3') // import 来源不进筛选
    w.unmount()
  })

  it('趋势分组渲染:组标题=脚本@设备,每组每 series 键一个子图(mean 实线+p90 虚线),空 points 组空态', async () => {
    const w = mountTrend()
    await flushPromises()
    expect(api.getPerfTrend).toHaveBeenCalledWith(1, {})
    const groupBlocks = w.findAll('[data-test="trend-group"]')
    expect(groupBlocks).toHaveLength(2)
    expect(groupBlocks[0].text()).toContain('场景A@dev1')
    expect(groupBlocks[0].find('[data-test="trend-charts"]').exists()).toBe(true)
    // 空 points 组:显示组级空态,不 init 图
    expect(groupBlocks[1].text()).toContain('场景B@dev2')
    expect(groupBlocks[1].find('[data-test="group-empty"]').exists()).toBe(true)
    expect(setOption).toHaveBeenCalledTimes(1)
    const opt = setOption.mock.calls[0][0] as any
    expect(opt.title.text).toBe('CPU') // 子图标题 = series 键
    expect(opt.series).toHaveLength(2)
    expect(opt.series.map((s: any) => s.name)).toEqual(['mean', 'p90'])
    expect(opt.series[0].lineStyle.type).toBe('solid')
    expect(opt.series[1].lineStyle.type).toBe('dashed')
    expect(opt.series[0].data).toEqual([15, 18])
    expect(opt.series[1].data).toEqual([19, 22])
    // X=点序,label=finished_at 格式化到分
    expect(opt.xAxis.data).toEqual(['2026-09-01 10:00', '2026-09-02 11:30'])
    w.unmount()
    expect(mockChart.dispose).toHaveBeenCalled()
  })

  it('筛选联动:选脚本/设备后按条件重拉趋势;重渲染清空 host,子图容器不累积', async () => {
    const w = mountTrend()
    await flushPromises()
    // 首次渲染:host 内子图容器数 = series 键数(1)
    expect(w.find('[data-test="trend-charts"]').element.children).toHaveLength(1)
    const selects = w.findAllComponents({ name: 'ElSelect' })
    await selects[0].vm.$emit('update:modelValue', 9)
    await flushPromises()
    expect(api.getPerfTrend).toHaveBeenLastCalledWith(1, { script_id: 9 })
    await selects[1].vm.$emit('update:modelValue', 'dev1')
    await flushPromises()
    expect(api.getPerfTrend).toHaveBeenLastCalledWith(1, { script_id: 9, device_serial: 'dev1' })
    // 两次重渲染后仍 = 1:重渲染必须先清 host 旧子节点(索引键复用下不清会越积越多)
    expect(w.find('[data-test="trend-charts"]').element.children).toHaveLength(1)
    w.unmount()
  })

  it('p90 全为 null 的 series 键只画 mean 一条线', async () => {
    api.getPerfTrend.mockResolvedValue({
      groups: [{
        script_id: 9, script_name: '场景A', device_serial: 'dev1',
        points: [
          { record_id: 11, finished_at: '2026-09-01T10:00:00', series: { CPU: { mean: 15, p90: null } } },
          { record_id: 12, finished_at: '2026-09-02T10:00:00', series: { CPU: { mean: 16, p90: null } } },
        ],
      }],
    })
    const w = mountTrend()
    await flushPromises()
    expect(setOption).toHaveBeenCalledTimes(1)
    const opt = setOption.mock.calls[0][0] as any
    expect(opt.series).toHaveLength(1)
    expect(opt.series[0].name).toBe('mean')
    w.unmount()
  })

  it('趋势拉取失败:error 提示 + 全局空态', async () => {
    api.getPerfTrend.mockRejectedValue(new Error('网络错误'))
    const errSpy = vi.spyOn(ElMessage, 'error').mockReturnValue({} as never)
    const w = mountTrend()
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('加载趋势数据失败:网络错误')
    expect(w.find('[data-test="trend-empty"]').exists()).toBe(true)
    expect(setOption).not.toHaveBeenCalled()
    w.unmount()
  })
})

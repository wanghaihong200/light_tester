// tests/unit/run-detail-drawer.spec.ts
// RunDetailDrawer 最小编排验证(此前无专项 spec):perf_summary 为 CLI perf-analyze 真实结构
// {files:[…]} 时,须 normalizePerfSummary 归一为标准形再喂 PerfCharts/PerfSummaryTable
// (计划14 冒烟修复:归一化幂等,标准形原样透传)。
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// jsdom 无 ResizeObserver,el-table 依赖其测量列宽(perf-summary-table.spec 同款 stub)
vi.stubGlobal('ResizeObserver', class { observe() { /* noop */ } unobserve() { /* noop */ } disconnect() { /* noop */ } })

const setOption = vi.fn()
vi.mock('echarts/core', () => ({
  init: vi.fn(() => ({ setOption, dispose: vi.fn(), resize: vi.fn(), getDataURL: vi.fn(() => 'data:image/png;base64,AAA') })),
  use: vi.fn(),
  connect: vi.fn(),
}))
vi.mock('echarts/charts', () => ({ LineChart: {} }))
vi.mock('echarts/components', () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {},
  DataZoomComponent: {}, MarkLineComponent: {}, TitleComponent: {},
}))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

const api = vi.hoisted(() => ({
  getAppRun: vi.fn(),
  getAppRunPerfSeries: vi.fn(),
  subscribeAppRunEvents: vi.fn(),
  forceFinishAppRun: vi.fn(),
}))
vi.mock('../../src/api/appAutomation', () => api)

import RunDetailDrawer from '../../src/components/appauto/RunDetailDrawer.vue'
import PerfCharts from '../../src/components/perf/PerfCharts.vue'
import type { AppRun } from '../../src/types'

// CLI perf-analyze 真实结构(字段与 run15 落库一致)
const FILES_SUMMARY = {
  files: [{
    path: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789045016565_1789045048339.csv',
    columns: [
      { name: 'CPU温度(度)', index: 1, kind: 'numeric', mean: 50.5, p90: 56.4 },
      { name: 'extra', index: 2, kind: 'skipped' },
    ],
  }],
}

const RUN = {
  id: 5, device_serial: 'dev1', status: 'passed', run_state: 'passed', error: null,
  perf_summary: FILES_SUMMARY, check_results: null, startup_summary: null, results: null,
} as unknown as AppRun

const mountDrawer = (run: AppRun | null) =>
  mount(RunDetailDrawer, {
    props: { visible: true, run },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })

describe('RunDetailDrawer perf_summary 归一化', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getAppRunPerfSeries.mockResolvedValue({ series: [] })
    api.subscribeAppRunEvents.mockReturnValue(() => {})
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('CLI 真实结构 → PerfCharts 收到标准形 summary(index=stem::列名),统计表显短形指标', async () => {
    const w = mountDrawer(RUN)
    await flushPromises()
    const charts = w.findComponent(PerfCharts)
    expect(charts.exists()).toBe(true)
    expect(charts.props('summary')).toEqual({
      columns: [{
        index: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789045016565_1789045048339::CPU温度(度)',
        name: 'CPU温度(度)',
        file: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789045016565_1789045048339',
        fileKey: 'Temperature',
        mean: 50.5, p90: 56.4,
      }],
    })
    // 抽屉 teleport 到 body:从 body 断言统计表短形指标名与数值
    expect(document.body.textContent).toContain('Temperature · CPU温度(度)')
    expect(document.body.textContent).toContain('50.50')
    w.unmount()
  })

  it('标准形 summary 原样透传(幂等,不产生归一化字段)', async () => {
    const std = { columns: [{ index: 'CPU', mean: 15 }] }
    const w = mountDrawer({ ...RUN, perf_summary: std } as unknown as AppRun)
    await flushPromises()
    const summary = w.findComponent(PerfCharts).props('summary') as { columns?: { index: string; fileKey?: string }[] }
    expect(summary).toEqual(std)
    expect(summary.columns?.[0].fileKey).toBeUndefined() // 透传未被二次加工
    w.unmount()
  })
})

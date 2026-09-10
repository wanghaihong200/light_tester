// tests/unit/perf-record-pane.spec.ts
// APP 性能测试页(计划14 Task9):列表(来源筛选/多选对比入口/删除)+ 详情抽屉(曲线/汇总/CSV 下载)
// echarts mock 沿 perf-charts.spec(jsdom 无 canvas);ResizeObserver stub 沿 perf-summary-table.spec
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
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

// 本页消费 perf API 全套(对比/趋势对话框 Task 11 接入后,其依赖也须在 mock 内兜底)
const api = vi.hoisted(() => ({
  listPerfRecords: vi.fn(),
  deletePerfRecord: vi.fn(),
  getPerfRecordSeries: vi.fn(),
  comparePerfRecords: vi.fn(),
  getPerfTrend: vi.fn(),
}))
vi.mock('../../src/api/perf', () => api)

import PerfRecordPane from '../../src/components/perf/PerfRecordPane.vue'
import PerfCharts from '../../src/components/perf/PerfCharts.vue'
import PerfCompareDialog from '../../src/components/perf/PerfCompareDialog.vue'
import PerfTrendDialog from '../../src/components/perf/PerfTrendDialog.vue'
import PerfImportDialog from '../../src/components/perf/PerfImportDialog.vue'
import StartupSummaryCard from '../../src/components/perf/StartupSummaryCard.vue'
import type { AppPerfSeries, PerfRecord } from '../../src/types'

function mkRecord(over: Partial<PerfRecord> = {}): PerfRecord {
  return {
    id: 1, project_id: 1, source: 'run', source_ref: null, name: '场景A@dev1', app_run_id: 5,
    script_id: 9, script_name: '场景A', device_serial: 'dev1', perf_items: ['CPU'],
    data_complete: true, perf_summary: { columns: [{ index: 'CPU', mean: 15, p90: 19 }] },
    started_at: null, finished_at: '2026-09-09T10:00:00',
    created_at: '2026-09-09T10:00:00',
    ...over,
  }
}
const RUN_REC = mkRecord()
const IMPORT_REC = mkRecord({
  id: 2, source: 'import', source_ref: 'hist-7', name: '手工采集', app_run_id: null,
  script_id: null, script_name: '', device_serial: 'dev2', perf_items: ['FPS', 'Mem'],
  data_complete: false, started_at: '2026-09-09T09:00:00', finished_at: null,
  created_at: '2026-09-09T11:00:00',
})

const SERIES: AppPerfSeries[] = [{ item: 'CPU', columns: ['ts', 'total'], rows: [['0', '10'], ['1', '20']] }]

// 挂 body:el-table 测量与抽屉内查询都需要真实挂载(mock-hits-panel.spec 同款)
const mountPane = () =>
  mount(PerfRecordPane, {
    props: { projectId: 1 },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })

const rows = (w: ReturnType<typeof mountPane>) => w.findAll('.el-table__row')
const btn = (w: ReturnType<typeof mountPane>, test: string) => w.find(`[data-test="${test}"]`)
const rowBtn = (w: ReturnType<typeof mountPane>, rowIndex: number, text: string) =>
  rows(w)[rowIndex].findAll('button').find((b) => b.text().includes(text))!

describe('PerfRecordPane', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listPerfRecords.mockResolvedValue([RUN_REC, IMPORT_REC])
    api.deletePerfRecord.mockResolvedValue(undefined)
    api.getPerfRecordSeries.mockResolvedValue({ record: RUN_REC, series: SERIES })
    // Task 11 对话框兜底:对话框挂载即拉数据,不给默认值会走 error 分支污染断言
    api.comparePerfRecords.mockResolvedValue({ records: [RUN_REC, IMPORT_REC], series: { '1': SERIES, '2': SERIES } })
    api.getPerfTrend.mockResolvedValue({ groups: [] })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('列表渲染:来源 tag(run=info/import=success)/脚本/设备/采集项/起止/不完整徽标', async () => {
    const w = mountPane()
    await flushPromises()
    expect(api.listPerfRecords).toHaveBeenCalledWith(1, {})
    expect(rows(w)).toHaveLength(2)
    expect(w.text()).toContain('场景A@dev1')
    expect(w.text()).toContain('dev1')
    expect(w.text()).toContain('dev2')
    // 采集项逗号拼接
    expect(w.text()).toContain('CPU')
    expect(w.text()).toContain('FPS,Mem')
    // 起止时间:null → —;ISO 截断到分钟
    expect(w.text()).toContain('— ~ 2026-09-09 10:00')
    expect(w.text()).toContain('2026-09-09 09:00 ~ —')
    // 来源 tag:run=info「采集」/ import=success「导入」
    const tags = w.findAll('[data-test="source-tag"]')
    expect(tags[0].text()).toBe('采集')
    expect(tags[1].text()).toBe('导入')
    expect(w.html()).toContain('el-tag--info')
    expect(w.html()).toContain('el-tag--success')
    // 数据完整性:data_complete=false → 红色「数据不完整」(data-test 落在 el-tag 内部 transition 根,
    // 颜色断言查 html,与 mock-hits-panel.spec 同款)
    const badge = w.find('[data-test="incomplete-badge"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('数据不完整')
    expect(w.html()).toContain('el-tag--danger')
    w.unmount()
  })

  it('来源筛选:切 run 以 source=run 重拉,切回全部不带 source', async () => {
    const w = mountPane()
    await flushPromises()
    expect(api.listPerfRecords).toHaveBeenLastCalledWith(1, {})
    await w.findAllComponents({ name: 'ElSelect' })[0].vm.$emit('update:modelValue', 'run')
    await flushPromises()
    expect(api.listPerfRecords).toHaveBeenLastCalledWith(1, { source: 'run' })
    await w.findAllComponents({ name: 'ElSelect' })[0].vm.$emit('update:modelValue', '')
    await flushPromises()
    expect(api.listPerfRecords).toHaveBeenLastCalledWith(1, {})
    w.unmount()
  })

  it('行点击(非操作列)开详情抽屉:标题=记录名,拉 series 渲染曲线+汇总表,不渲染启动卡', async () => {
    const w = mountPane()
    await flushPromises()
    expect(api.getPerfRecordSeries).not.toHaveBeenCalled()
    await rows(w)[0].trigger('click')
    await flushPromises()
    expect(api.getPerfRecordSeries).toHaveBeenCalledWith(1)
    expect(w.find('[data-test="detail-drawer"]').exists()).toBe(true)
    expect(w.text()).toContain('场景A@dev1')
    expect(w.findComponent(PerfCharts).exists()).toBe(true)
    expect(w.find('[data-test="stat-table"]').exists()).toBe(true)
    // startup_summary 在 AppRun 上、不在 PerfRecord:本抽屉不显示启动卡(它是 RunDetailDrawer 的组件)
    expect(w.findComponent(StartupSummaryCard).exists()).toBe(false)
    w.unmount()
  })

  it('详情抽屉 summary 归一化:CLI 真实结构 {files} → PerfCharts/统计表收标准形(冒烟修复)', async () => {
    api.listPerfRecords.mockResolvedValue([mkRecord({
      perf_summary: {
        files: [{
          path: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789.csv',
          columns: [
            { name: 'CPU温度(度)', index: 1, kind: 'numeric', mean: 50.5, p90: 56.4 },
            { name: 'extra', index: 2, kind: 'skipped' },
          ],
        }],
      },
    })])
    const w = mountPane()
    await flushPromises()
    await rows(w)[0].trigger('click')
    await flushPromises()
    expect(w.findComponent(PerfCharts).props('summary')).toEqual({
      columns: [{
        index: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789::CPU温度(度)',
        name: 'CPU温度(度)', file: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789',
        fileKey: 'Temperature', mean: 50.5, p90: 56.4,
      }],
    })
    expect(w.find('[data-test="stat-table"]').exists()).toBe(true)
    w.unmount()
  })

  it('删除:confirm 后 deletePerfRecord 并刷新;取消分支不删', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const w = mountPane()
    await flushPromises()
    await rowBtn(w, 1, '删除').trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(String(confirmSpy.mock.calls[0][0])).toContain('手工采集')
    expect(api.deletePerfRecord).toHaveBeenCalledWith(2)
    expect(api.listPerfRecords).toHaveBeenCalledTimes(2) // 删除后刷新

    // 取消:confirm reject → 不调用删除
    confirmSpy.mockRejectedValueOnce('cancel')
    await rowBtn(w, 0, '删除').trigger('click')
    await flushPromises()
    expect(api.deletePerfRecord).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('对比按钮:多选 <2 禁用,勾选两条后可用,点击打开 PerfCompareDialog 并传选中 ids,@close 关窗', async () => {
    const w = mountPane()
    await flushPromises()
    expect(btn(w, 'compare-btn').exists()).toBe(true)
    expect((btn(w, 'compare-btn').element as HTMLButtonElement).disabled).toBe(true)
    w.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [RUN_REC, IMPORT_REC])
    await flushPromises()
    expect((btn(w, 'compare-btn').element as HTMLButtonElement).disabled).toBe(false)
    expect(w.findComponent(PerfCompareDialog).exists()).toBe(false)
    await btn(w, 'compare-btn').trigger('click')
    const dlg = w.findComponent(PerfCompareDialog)
    expect(dlg.exists()).toBe(true)
    expect(dlg.props('projectId')).toBe(1)
    expect(dlg.props('recordIds')).toEqual([1, 2])
    dlg.vm.$emit('close')
    await flushPromises()
    expect(w.findComponent(PerfCompareDialog).exists()).toBe(false)
    w.unmount()
  })

  it('趋势按钮打开 PerfTrendDialog;导入按钮打开 PerfImportDialog,@imported 后刷新列表并提示成功', async () => {
    const successSpy = vi.spyOn(ElMessage, 'success').mockReturnValue({} as never)
    const w = mountPane()
    await flushPromises()
    expect(api.listPerfRecords).toHaveBeenCalledTimes(1)
    // 导入:挂载向导,projectId 透传
    expect(w.findComponent(PerfImportDialog).exists()).toBe(false)
    await btn(w, 'import-btn').trigger('click')
    const dlg = w.findComponent(PerfImportDialog)
    expect(dlg.exists()).toBe(true)
    expect(dlg.props('projectId')).toBe(1)
    // 导入成功回调:关窗 + 成功提示(完整数据)+ 刷新
    dlg.vm.$emit('imported', RUN_REC)
    await flushPromises()
    expect(successSpy).toHaveBeenCalledWith('导入成功')
    expect(api.listPerfRecords).toHaveBeenCalledTimes(2)
    expect(w.findComponent(PerfImportDialog).exists()).toBe(false)
    // 不完整记录:仅由向导 warning,面板不再叠加成功提示
    await btn(w, 'import-btn').trigger('click')
    w.findComponent(PerfImportDialog).vm.$emit('imported', mkRecord({ id: 3, data_complete: false }))
    await flushPromises()
    expect(successSpy).toHaveBeenCalledTimes(1)
    expect(api.listPerfRecords).toHaveBeenCalledTimes(3)
    // 趋势:打开 PerfTrendDialog 并透传 projectId,@close 关窗
    expect(w.findComponent(PerfTrendDialog).exists()).toBe(false)
    await btn(w, 'trend-btn').trigger('click')
    const trend = w.findComponent(PerfTrendDialog)
    expect(trend.exists()).toBe(true)
    expect(trend.props('projectId')).toBe(1)
    trend.vm.$emit('close')
    await flushPromises()
    expect(w.findComponent(PerfTrendDialog).exists()).toBe(false)
    w.unmount()
  })

  it('详情抽屉「下载 CSV」:series 拼多段文本 Blob 下载,文件名=记录名', async () => {
    const createObjectURL = vi.fn(() => 'blob:csv-mock')
    const revokeObjectURL = vi.fn()
    const origCreate = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true, writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true, writable: true })
    const click = vi.fn()
    const origCreateEl = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = origCreateEl(tag) as HTMLAnchorElement
      if (tag === 'a') el.click = click
      return el
    })
    try {
      const w = mountPane()
      await flushPromises()
      await rows(w)[0].trigger('click')
      await flushPromises()
      await btn(w, 'download-csv').trigger('click')
      expect(createObjectURL).toHaveBeenCalledTimes(1)
      const blob = createObjectURL.mock.calls[0][0] as Blob
      expect(blob).toBeInstanceOf(Blob)
      // jsdom Blob 无 .text(),走 FileReader 读回校验拼装格式
      const text = await new Promise<string>((resolve) => {
        const fr = new FileReader()
        fr.onload = () => resolve(String(fr.result))
        fr.readAsText(blob)
      })
      expect(text).toBe('# item: CPU\nts,total\n0,10\n1,20')
      expect(click).toHaveBeenCalledTimes(1)
      const anchor = click.mock.instances[0] as HTMLAnchorElement
      expect(anchor.download).toBe('场景A@dev1.csv')
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:csv-mock')
      w.unmount()
    } finally {
      Object.defineProperty(URL, 'createObjectURL', { value: origCreate, configurable: true, writable: true })
      Object.defineProperty(URL, 'revokeObjectURL', { value: origRevoke, configurable: true, writable: true })
      vi.restoreAllMocks()
    }
  })

  it('CSV 硬化(Task10):内容带 UTF-8 BOM,文件名非法字符替换为 _', async () => {
    const createObjectURL = vi.fn(() => 'blob:csv-mock')
    const revokeObjectURL = vi.fn()
    const origCreate = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true, writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true, writable: true })
    const click = vi.fn()
    const origCreateEl = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = origCreateEl(tag) as HTMLAnchorElement
      if (tag === 'a') el.click = click
      return el
    })
    // 记录名含 Windows 非法字符 / : *(文件名取自行数据,故改列表);
    // 行值覆盖公式注入四类前缀 = + - @(计划14 终审)
    api.listPerfRecords.mockResolvedValue([mkRecord({ id: 9, name: 'CPU/采集:压力*1' })])
    api.getPerfRecordSeries.mockResolvedValue({
      record: mkRecord({ id: 9, name: 'CPU/采集:压力*1' }),
      series: [{ item: 'CPU', columns: ['ts', 'total'], rows: [['0', '=1+1'], ['1', '+86-555'], ['2', '@cmd'], ['-3', '20']] }],
    })
    try {
      const w = mountPane()
      await flushPromises()
      await rows(w)[0].trigger('click')
      await flushPromises()
      await btn(w, 'download-csv').trigger('click')
      const anchor = click.mock.instances[0] as HTMLAnchorElement
      expect(anchor.download).toBe('CPU_采集_压力_1.csv')
      // BOM:读原始字节,UTF-8 BOM = EF BB BF
      const blob = createObjectURL.mock.calls[0][0] as Blob
      const bytes = await new Promise<Uint8Array>((resolve) => {
        const fr = new FileReader()
        fr.onload = () => resolve(new Uint8Array(fr.result as ArrayBuffer))
        fr.readAsArrayBuffer(blob)
      })
      expect([bytes[0], bytes[1], bytes[2]]).toEqual([0xef, 0xbb, 0xbf])
      // 公式注入防御:= + - @ 开头的单元格前置 '(负数同样被视为文本,可接受的代价)
      const csvText = await new Promise<string>((resolve) => {
        const fr = new FileReader()
        fr.onload = () => resolve(String(fr.result))
        fr.readAsText(blob)
      })
      expect(csvText).toBe('# item: CPU\nts,total\n0,\'=1+1\n1,\'+86-555\n2,\'@cmd\n\'-3,20')
      w.unmount()
    } finally {
      Object.defineProperty(URL, 'createObjectURL', { value: origCreate, configurable: true, writable: true })
      Object.defineProperty(URL, 'revokeObjectURL', { value: origRevoke, configurable: true, writable: true })
      vi.restoreAllMocks()
    }
  })
})

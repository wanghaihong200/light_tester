// tests/unit/perf-import-dialog.spec.ts
// 手动导入向导(计划14 Task10):选设备 → 设备历史(已导入行禁用)→ 确认导入
// 挂载方式沿 import-dialog.spec(ElementPlus 全量插件);ResizeObserver stub 沿 perf-record-pane.spec
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// jsdom 无 ResizeObserver,el-table 依赖其测量列宽(mindmap-editor.spec 同款 stub)
vi.stubGlobal('ResizeObserver', class { observe() { /* noop */ } unobserve() { /* noop */ } disconnect() { /* noop */ } })

const apiApp = vi.hoisted(() => ({ listAppDevices: vi.fn() }))
const apiPerf = vi.hoisted(() => ({
  listDevicePerfHistory: vi.fn(),
  importPerfHistory: vi.fn(),
}))
vi.mock('../../src/api/appAutomation', () => apiApp)
vi.mock('../../src/api/perf', () => apiPerf)

import PerfImportDialog from '../../src/components/perf/PerfImportDialog.vue'
import type { DeviceInfo, DevicePerfHistoryItem, PerfRecord } from '../../src/types'

const DEVICE: DeviceInfo = { serial: 'dev1', state: 'device' }

const HISTORY: DevicePerfHistoryItem[] = [
  { id: 'performance-abc', start_time: 1725868800000, end_time: 1725868860000, file_count: 2, size_bytes: 2048, metrics: ['CPU'], imported_record_id: null },
  { id: 'performance-old', start_time: null, end_time: null, file_count: 1, size_bytes: 10, metrics: [], imported_record_id: 9 },
]
// 竞态守卫用:两台设备返回不同 metrics 的历史,以区分快/慢响应谁最终上屏
const HISTORY_A: DevicePerfHistoryItem[] = [
  { id: 'performance-A1', start_time: 1725868800000, end_time: 1725868860000, file_count: 9, size_bytes: 100, metrics: ['CPU'], imported_record_id: null },
]
const HISTORY_B: DevicePerfHistoryItem[] = [
  { id: 'performance-B1', start_time: 1725868800000, end_time: 1725868860000, file_count: 8, size_bytes: 200, metrics: ['MEM'], imported_record_id: null },
]

function mkRecord(over: Partial<PerfRecord> = {}): PerfRecord {
  return {
    id: 100, project_id: 1, source: 'import', source_ref: 'performance-abc', name: '设备导入 performance-',
    app_run_id: null, script_id: null, script_name: '', device_serial: 'dev1', perf_items: ['CPU'],
    data_complete: true, perf_summary: null, started_at: null, finished_at: null,
    created_at: '2026-09-09T10:00:00',
    ...over,
  }
}

const mountDialog = () =>
  mount(PerfImportDialog, {
    props: { projectId: 1 },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })

// 走到「确认导入」步:选设备 → 勾第一条可用历史(选中即自动进确认步)
async function gotoConfirmStep(w: ReturnType<typeof mountDialog>) {
  await w.find('[data-test="device-option"]').trigger('click')
  await flushPromises()
  const rows = w.findAll('tbody tr')
  await rows[0].find('input').setValue(true)
  await flushPromises()
}

describe('PerfImportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiApp.listAppDevices.mockResolvedValue([DEVICE])
    apiPerf.listDevicePerfHistory.mockResolvedValue({ items: HISTORY })
    apiPerf.importPerfHistory.mockResolvedValue(mkRecord())
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('设备→历史→导入 全流程:已导入行禁用,默认名=设备导入+id前20位(对齐后端截断),可改名', async () => {
    const successSpy = vi.spyOn(ElMessage, 'success').mockReturnValue({} as never)
    const w = mountDialog()
    await flushPromises()
    expect(apiApp.listAppDevices).toHaveBeenCalledTimes(1)

    // 步1:点设备选项 → 拉该设备历史(limit=200,防长历史漏单)
    await w.find('[data-test="device-option"]').trigger('click')
    await flushPromises()
    expect(apiPerf.listDevicePerfHistory).toHaveBeenCalledWith('dev1', 200)
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    // 历史行:大小人类可读(2048B → 2.0 KB);已导入行打「已导入」tag 且 checkbox 禁用
    expect(rows[0].text()).toContain('2.0 KB')
    expect(rows[1].text()).toContain('已导入')
    expect((rows[1].find('input').element as HTMLInputElement).disabled).toBe(true)

    // 勾可用行 → 自动进确认步,名称默认「设备导入 <id 前 20 位>」
    await rows[0].find('input').setValue(true)
    await flushPromises()
    const nameInput = () => w.find('[data-test="import-name"] input')
    expect((nameInput().element as HTMLInputElement).value).toBe('设备导入 performance-abc')

    // 名称可编辑,确认后按编辑值提交并 emit imported + close
    await nameInput().setValue('9月回归基线')
    await w.find('[data-test="confirm-import"]').trigger('click')
    await flushPromises()
    expect(apiPerf.importPerfHistory).toHaveBeenCalledTimes(1)
    expect(apiPerf.importPerfHistory).toHaveBeenCalledWith(1, {
      serial: 'dev1', history_id: 'performance-abc', name: '9月回归基线',
    })
    // 完整数据的成功提示由 PerfRecordPane 在 @imported 后弹(避免双 toast),向导自身静默
    expect(successSpy).not.toHaveBeenCalled()
    expect(w.emitted('imported')).toBeTruthy()
    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('409 重复导入:error 透传后端 detail 文案,不关窗不 emit imported', async () => {
    apiPerf.importPerfHistory.mockRejectedValueOnce(
      Object.assign(new Error('该历史已导入过(记录 #9)'), { status: 409 }))
    const errSpy = vi.spyOn(ElMessage, 'error').mockReturnValue({} as never)
    const w = mountDialog()
    await flushPromises()
    await gotoConfirmStep(w)
    await w.find('[data-test="confirm-import"]').trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('该历史已导入过(记录 #9)')
    expect(w.emitted('imported')).toBeFalsy()
    expect(w.emitted('close')).toBeFalsy() // 留在窗内,用户可返回上一步
    w.unmount()
  })

  it('data_complete=false:导入成功但 warning 提示数据不完整', async () => {
    apiPerf.importPerfHistory.mockResolvedValueOnce(mkRecord({ id: 101, data_complete: false }))
    const warnSpy = vi.spyOn(ElMessage, 'warning').mockReturnValue({} as never)
    const w = mountDialog()
    await flushPromises()
    await gotoConfirmStep(w)
    await w.find('[data-test="confirm-import"]').trigger('click')
    await flushPromises()
    expect(warnSpy).toHaveBeenCalledWith('导入成功,但数据不完整(设备端已截断)')
    expect(w.emitted('imported')).toBeTruthy()
    w.unmount()
  })

  it('历史拉取失败:error 提示并停在历史步(空表)', async () => {
    apiPerf.listDevicePerfHistory.mockRejectedValue(new Error('设备已离线'))
    const errSpy = vi.spyOn(ElMessage, 'error').mockReturnValue({} as never)
    const w = mountDialog()
    await flushPromises()
    await w.find('[data-test="device-option"]').trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('加载设备历史失败:设备已离线')
    expect(w.emitted('close')).toBeFalsy()
    w.unmount()
  })

  it('快速切换设备:慢的旧设备响应不覆盖新设备的历史(pickDevice 序号守卫)', async () => {
    let resolveA!: (v: { items: DevicePerfHistoryItem[] }) => void
    apiPerf.listDevicePerfHistory.mockImplementation((serial: string) => {
      if (serial === 'devA') return new Promise((res) => { resolveA = res }) // devA 响应挂起
      return Promise.resolve({ items: HISTORY_B }) // devB 立即返回
    })
    apiApp.listAppDevices.mockResolvedValue([
      { serial: 'devA', state: 'device' },
      { serial: 'devB', state: 'device' },
    ])
    const w = mountDialog()
    await flushPromises()
    const options = w.findAll('[data-test="device-option"]')
    await options[0].trigger('click') // 进 devA(挂起)
    await options[1].trigger('click') // 切 devB(立即返回)
    await flushPromises()
    resolveA({ items: HISTORY_A }) // devA 的旧响应后到
    await flushPromises()
    // 表内仍是 devB 的历史(MEM),过期响应被丢弃且不弹错误
    expect(w.text()).toContain('设备 devB')
    expect(w.text()).toContain('MEM')
    expect(w.text()).not.toContain('CPU')
    w.unmount()
  })

  it('确认步取消勾选:确认按钮禁用 + 提示(不必退步),重新勾选后恢复可导入', async () => {
    const w = mountDialog()
    await flushPromises()
    await gotoConfirmStep(w)
    expect((w.find('[data-test="confirm-import"]').element as HTMLButtonElement).disabled).toBe(false)
    // 历史表在确认步保持挂载:直接取消勾选 → selected 清空,按钮禁用 + 提示,无需退步
    const rows = w.findAll('tbody tr')
    await rows[0].find('input').setValue(false)
    await flushPromises()
    expect((w.find('[data-test="confirm-import"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(w.find('[data-test="confirm-hint"]').exists()).toBe(true)
    await w.find('[data-test="confirm-import"]').trigger('click')
    expect(apiPerf.importPerfHistory).not.toHaveBeenCalled()
    // 重新勾选同一行:恢复确认态,可正常导入
    await w.findAll('tbody tr')[0].find('input').setValue(true)
    await flushPromises()
    expect((w.find('[data-test="confirm-import"]').element as HTMLButtonElement).disabled).toBe(false)
    expect(w.find('[data-test="confirm-hint"]').exists()).toBe(false)
    await w.find('[data-test="confirm-import"]').trigger('click')
    await flushPromises()
    expect(apiPerf.importPerfHistory).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})

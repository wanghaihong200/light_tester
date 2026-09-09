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

  it('设备→历史→导入 全流程:已导入行禁用,默认名=设备导入+id前12位,可改名', async () => {
    const successSpy = vi.spyOn(ElMessage, 'success').mockReturnValue({} as never)
    const w = mountDialog()
    await flushPromises()
    expect(apiApp.listAppDevices).toHaveBeenCalledTimes(1)

    // 步1:点设备选项 → 拉该设备历史(默认 limit=50)
    await w.find('[data-test="device-option"]').trigger('click')
    await flushPromises()
    expect(apiPerf.listDevicePerfHistory).toHaveBeenCalledWith('dev1', 50)
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    // 历史行:大小人类可读(2048B → 2.0 KB);已导入行打「已导入」tag 且 checkbox 禁用
    expect(rows[0].text()).toContain('2.0 KB')
    expect(rows[1].text()).toContain('已导入')
    expect((rows[1].find('input').element as HTMLInputElement).disabled).toBe(true)

    // 勾可用行 → 自动进确认步,名称默认「设备导入 <id 前 12 位>」
    await rows[0].find('input').setValue(true)
    await flushPromises()
    const nameInput = () => w.find('[data-test="import-name"] input')
    expect((nameInput().element as HTMLInputElement).value).toBe('设备导入 performance-')

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
})

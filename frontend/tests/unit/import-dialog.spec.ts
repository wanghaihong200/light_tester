import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ImportDialog from '../../src/components/appauto/ImportDialog.vue'
import { listAppDevices, listDeviceCases } from '../../src/api/appAutomation'

vi.mock('../../src/api/appAutomation', () => ({
  // ImportDialog 具名引入的 4 个导出都要给,缺一个整个模块 mock 失败
  listAppDevices: vi.fn().mockResolvedValue([
    { serial: 'EMU-1', state: 'device' },
    { serial: 'EMU-2', state: 'offline' },
  ]),
  listDeviceCases: vi.fn().mockResolvedValue([]),
  importDeviceCase: vi.fn(),
  importUploadCase: vi.fn(),
}))

// 以 visible=false 挂载再置 true:组件真实用法是常挂载、弹窗开关切换,watch(visible) 才会触发
const mount_ = (visible = false) => mount(ImportDialog, {
  props: { projectId: 1, visible },
  global: { plugins: [ElementPlus] },
})

beforeEach(() => { vi.clearAllMocks() })

describe('ImportDialog 设备用例同步', () => {
  it('① 弹窗每次打开都自动同步(重开 serial 不变也要重新拉取)', async () => {
    ;(listDeviceCases as any).mockResolvedValue([{ file_name: 'a.json', source: 'export' }])
    const w = mount_(false)
    await w.setProps({ visible: true }) // 首开:无 serial → 选首台 device 设备 → watch(serial) 拉取
    await flushPromises()
    expect(listDeviceCases).toHaveBeenCalledTimes(1)
    expect(listDeviceCases).toHaveBeenCalledWith(1, 'EMU-1')
    await w.setProps({ visible: false })
    await w.setProps({ visible: true }) // 重开:serial 未变,仍须自动同步
    await flushPromises()
    expect(listDeviceCases).toHaveBeenCalledTimes(2)
  })

  it('①b 自动拉取失败静默(不弹 ElMessage.error)', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    ;(listDeviceCases as any).mockRejectedValue(new Error('设备已离线'))
    const w = mount_(false)
    await w.setProps({ visible: true })
    await flushPromises()
    expect(errSpy).not.toHaveBeenCalled()
  })
})

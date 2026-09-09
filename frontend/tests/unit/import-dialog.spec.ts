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

  it('② 点「同步」重新拉取,请求期间按钮 loading', async () => {
    let resolve!: (v: any[]) => void
    ;(listDeviceCases as any).mockImplementation(() => new Promise((r) => (resolve = r)))
    const w = mount_(false)
    await w.setProps({ visible: true }) // 首开自动同步,故意挂起以便观察 loading
    await w.vm.$nextTick()
    const btn = w.findAll('button').find((b) => b.text().includes('同步'))!
    expect(btn.classes()).toContain('is-loading')
    resolve([{ file_name: 'a.json', source: 'export' }])
    await flushPromises()
    expect(btn.classes()).not.toContain('is-loading')
    // 再手动点一次(走 DOM click,验证按钮真的绑了 refreshCases(true))
    ;(listDeviceCases as any).mockImplementation(() => new Promise((r) => (resolve = r)))
    await btn.trigger('click')
    await w.vm.$nextTick()
    expect(listDeviceCases).toHaveBeenCalledTimes(2)
    expect(btn.classes()).toContain('is-loading')
    resolve([])
    await flushPromises()
    expect((w.vm as any).syncing).toBe(false)
  })

  it('③ 手动同步失败弹 error 透出原因;自动路径不弹', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    ;(listDeviceCases as any).mockRejectedValue(new Error('设备已离线'))
    const w = mount_(false)
    await w.setProps({ visible: true })
    await flushPromises()
    expect(errSpy).not.toHaveBeenCalled() // 自动静默
    await (w.vm as any).refreshCases(true)
    expect(errSpy).toHaveBeenCalledWith('设备已离线')
  })

  it('④ 手动同步成功但 0 条 → info 提示;自动路径不弹', async () => {
    const infoSpy = vi.spyOn(ElMessage, 'info')
    ;(listDeviceCases as any).mockResolvedValue([])
    const w = mount_(false)
    await w.setProps({ visible: true })
    await flushPromises()
    expect(infoSpy).not.toHaveBeenCalled()
    await (w.vm as any).refreshCases(true)
    expect(infoSpy).toHaveBeenCalledWith('未在设备上发现已导出的用例')
  })

  it('⑤ 未选设备时「同步」按钮禁用;选上后可用', async () => {
    ;(listDeviceCases as any).mockResolvedValue([])
    // 设备清单也挂起:钉住"serial 为空"的中间态(已决 promise 的微任务可能抢在 nextTick 前恢复,
    // 导致 serial 已被赋值、断言时刻不再是未选设备态)
    let resolveDevices!: (v: any[]) => void
    ;(listAppDevices as any).mockImplementation(() => new Promise((r) => (resolveDevices = r)))
    const w = mount_(false)
    await w.setProps({ visible: true }) // 开窗 → watch(visible) 挂起等待设备清单
    await w.vm.$nextTick()              // 设备未到、serial 仍空 → 按钮禁用
    const btn = w.findAll('button').find((b) => b.text().includes('同步'))!
    expect(btn.classes()).toContain('is-disabled')
    resolveDevices([{ serial: 'EMU-1', state: 'device' }])
    await flushPromises()               // devices 就绪 → 首台设备选中 → 同步完成 → 按钮可用
    expect(btn.classes()).not.toContain('is-disabled')
  })
})

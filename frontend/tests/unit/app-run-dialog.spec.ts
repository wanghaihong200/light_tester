import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listAppDevices: vi.fn(),
  listPerfItems: vi.fn(),
  createAppRuns: vi.fn(),
}))
vi.mock('../../src/api/appAutomation', () => api)

import AppRunDialog from '../../src/components/appauto/AppRunDialog.vue'

const SCRIPT = {
  id: 7, project_id: 1, name: '冒烟', description: null,
  case_json: { caseName: '冒烟', targetAppPackage: 'com.a', operationLog: { steps: [] } },
  app_package: 'com.a', created_at: '', updated_at: '',
}

// 桩形态对齐 T14 先例(appauto-pane.spec.ts):装真 Element Plus 而非手写桩——
// brief 的 'el-select' 桩模板含非法片段 `multiple?` 无法编译;断言点保持 brief 不变
const mountDlg = (multi = false) =>
  mount(AppRunDialog, { props: { projectId: 1, scripts: [SCRIPT], multi, visible: true },
                        global: { plugins: [ElementPlus] } })

describe('AppRunDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listAppDevices.mockResolvedValue([
      { serial: 'DEV-A', state: 'device' }, { serial: 'DEV-B', state: 'device' },
      { serial: 'DEV-C', state: 'unauthorized' }])
    api.listPerfItems.mockResolvedValue({ items: ['CPU', 'FPS', 'Memory'] })
    api.createAppRuns.mockResolvedValue([])
  })

  it('单设备:只列可用设备,执行调 createAppRuns 传 1 个 serial', async () => {
    const w = mountDlg(false)
    await flushPromises()
    expect((w.vm as any).devices.map((d: any) => d.serial)).toEqual(['DEV-A', 'DEV-B'])
    ;(w.vm as any).serials = ['DEV-A']
    ;(w.vm as any).scriptId = 7
    await (w.vm as any).run()
    expect(api.createAppRuns).toHaveBeenCalledWith(1, expect.objectContaining({
      script_id: 7, device_serials: ['DEV-A'] }))
    expect(w.emitted('started')).toBeTruthy()
  })

  it('批量:多设备同 batch 发起', async () => {
    const w = mountDlg(true)
    await flushPromises()
    ;(w.vm as any).scriptId = 7
    ;(w.vm as any).serials = ['DEV-A', 'DEV-B']
    ;(w.vm as any).perfSelected = ['CPU']
    await (w.vm as any).run()
    const body = api.createAppRuns.mock.calls[0][1]
    expect(body.device_serials).toEqual(['DEV-A', 'DEV-B'])
    expect(body.perf_items).toEqual(['CPU'])
  })
})

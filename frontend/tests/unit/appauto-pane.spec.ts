import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listAppScripts: vi.fn(),
  deleteAppScript: vi.fn(),
  listAppRuns: vi.fn(),
  listAppDevices: vi.fn(),
  listDeviceCases: vi.fn(),
  importDeviceCase: vi.fn(),
}))

vi.mock('../../src/api/appAutomation', () => api)

import AppAutoPane from '../../src/components/appauto/AppAutoPane.vue'
import ImportDialog from '../../src/components/appauto/ImportDialog.vue'

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
    api.listDeviceCases.mockResolvedValue([{ file_name: 'case_a.json' }])
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

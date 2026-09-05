import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import type { UiRun, UiScript } from '../../src/types'

// 挂载/mock 方式照抄 webauto-pane.spec.ts:hoisted mocks + 模块级 vi.mock
const mocks = vi.hoisted(() => ({
  listScripts: vi.fn(async () => [] as unknown[]),
  listRuns: vi.fn(async () => [] as unknown[]),
  delScript: vi.fn(async () => undefined),
  createScript: vi.fn(async () => ({})),
  updateScript: vi.fn(async () => ({})),
  listAuth: vi.fn(async () => [] as unknown[]),
  collectSnap: vi.fn(async () => ({})),
  delAuth: vi.fn(async () => undefined),
}))
vi.mock('../../src/api/crossAutomation', () => ({
  listCrossScripts: mocks.listScripts,
  listRunsByTarget: mocks.listRuns,
  listAuthStates: mocks.listAuth,
  collectAndroidSnapshot: mocks.collectSnap,
}))
vi.mock('../../src/api/uiAutomation', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  createUiScript: mocks.createScript,
  updateUiScript: mocks.updateScript,
  deleteUiScript: mocks.delScript,
  deleteUiAuthState: mocks.delAuth,
  getUiRun: vi.fn(async () => null),
  subscribeRunEvents: vi.fn(() => () => {}),
}))

import CrossAutoPane from '../../src/components/crossauto/CrossAutoPane.vue'

// mock 返回结构对齐 types.UiScript / types.UiRun 真实契约(含计划10的 driver_target/ai_usage)
function mkScript(id: number, name: string, target: 'web' | 'android' | 'harmony'): UiScript {
  const meta: UiScript['script']['meta'] = { start_url: target === 'web' ? 'https://x' : '', target }
  if (target !== 'web') meta.launch_target = 'com.example.app'
  return {
    id,
    project_id: 1,
    name,
    description: null,
    script: { version: 2, meta, variables: [], steps: [{ id: 's1', action: 'ai_tap', params: { target: '登录按钮' } }] },
    created_at: '2026-09-05T10:00:00',
    updated_at: '2026-09-05T10:00:00',
  }
}

function mkRun(over: Partial<UiRun> = {}): UiRun {
  return {
    id: 9, project_id: 1, status: 'completed', script_id: 1, script_name: 'Web冒烟',
    mode: 'headless', variables: {}, step_results: [], steps_total: 2, steps_passed: 2,
    steps_failed: 0, error: null, started_at: '2026-09-05T10:01:00', finished_at: '2026-09-05T10:01:05',
    driver_target: 'web', ai_usage: null,
    ...over,
  }
}

const webScript = mkScript(1, 'Web冒烟', 'web')
const androidScript = mkScript(2, 'App冒烟', 'android')

function mountPane() {
  return mount(CrossAutoPane, {
    props: { projectId: 1 },
    // 编辑器/运行框是弹层,桩掉避免干扰;AppSnapshotsPane 是内嵌面板,保留真实渲染
    global: { plugins: [ElementPlus], stubs: { CrossScriptEditor: true } },
  })
}
// 在某个子组件范围内找按钮(同屏多张表都有「删除」,必须收窄范围)
const btnIn = (w: ReturnType<typeof mountPane>, name: string, text: string) =>
  w.findComponent({ name }).findAll('button').find((b) => b.text().includes(text))!

beforeEach(() => {
  vi.clearAllMocks()
  mocks.listScripts.mockResolvedValue([webScript, androidScript])
  // listRunsByTarget 的过滤发生在服务端(driver_target 查询参数),mock 按参数返回对应端的执行记录
  mocks.listRuns.mockImplementation(async (_pid: number, t?: string) =>
    t === 'android'
      ? [mkRun({ id: 10, script_name: 'App冒烟', driver_target: 'android' })]
      : [mkRun()])
  mocks.listAuth.mockResolvedValue([
    { id: 7, project_id: 1, name: '首页快照', created_at: '2026-09-05T10:00:00', kind: 'android_snapshot', app_package: 'com.example.app' },
  ])
})

describe('CrossAutoPane', () => {
  it('① 挂载后调 listCrossScripts 并按当前端(Web)过滤脚本列表', async () => {
    const w = mountPane()
    await flushPromises()
    expect(mocks.listScripts).toHaveBeenCalledWith(1)
    expect(mocks.listRuns).toHaveBeenCalledWith(1, 'web')
    expect(w.text()).toContain('Web冒烟')
    expect(w.text()).not.toContain('App冒烟') // android 脚本被按端过滤
  })

  it('② 切端到 Android:重拉脚本/历史并渲染 AppSnapshotsPane', async () => {
    const w = mountPane()
    await flushPromises()
    await w.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'android')
    await flushPromises()
    expect(mocks.listRuns).toHaveBeenCalledWith(1, 'android') // 切端即按端 reload
    expect(w.findComponent({ name: 'AppSnapshotsPane' }).exists()).toBe(true)
    expect(mocks.listAuth).toHaveBeenCalledWith(1, 'android_snapshot')
    expect(w.text()).toContain('首页快照')
    expect(w.text()).not.toContain('Web冒烟') // Web 脚本不再展示
  })

  it('③ 点「运行」打开 CrossRunDialog 并传入所选脚本', async () => {
    const w = mountPane()
    await flushPromises()
    expect(w.findComponent({ name: 'CrossRunDialog' }).props('script')).toBeNull()
    await btnIn(w, 'CrossAutoPane', '运行').trigger('click')
    await flushPromises()
    const dlg = w.findComponent({ name: 'CrossRunDialog' })
    expect(dlg.exists()).toBe(true)
    expect(dlg.props('script') as UiScript).toMatchObject({ id: 1, name: 'Web冒烟' })
  })

  it('AppSnapshotsPane:采集表单提交 collectAndroidSnapshot 并刷新快照列表', async () => {
    const w = mountPane()
    await flushPromises()
    await w.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'android')
    await flushPromises()
    const pane = w.findComponent({ name: 'AppSnapshotsPane' })
    const inputs = pane.findAll('input')
    await inputs.find((i) => (i.element as HTMLInputElement).placeholder.includes('快照名称'))!.setValue('首页快照')
    await inputs.find((i) => (i.element as HTMLInputElement).placeholder.includes('com.'))!.setValue('com.example.app')
    await btnIn(w, 'AppSnapshotsPane', '采集').trigger('click')
    await flushPromises()
    expect(mocks.collectSnap).toHaveBeenCalledWith(1, { name: '首页快照', app_package: 'com.example.app' })
    expect(mocks.listAuth).toHaveBeenCalledTimes(2) // 采集成功后刷新
  })

  it('AppSnapshotsPane:采集 409(无设备/adb 不可用)时把 detail 用 ElMessage 展示', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    mocks.collectSnap.mockRejectedValueOnce(new ApiError(409, '未检测到 Android 设备'))
    const w = mountPane()
    await flushPromises()
    await w.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'android')
    await flushPromises()
    const inputs = w.findComponent({ name: 'AppSnapshotsPane' }).findAll('input')
    await inputs.find((i) => (i.element as HTMLInputElement).placeholder.includes('快照名称'))!.setValue('首页快照')
    await inputs.find((i) => (i.element as HTMLInputElement).placeholder.includes('com.'))!.setValue('com.example.app')
    await btnIn(w, 'AppSnapshotsPane', '采集').trigger('click')
    await flushPromises()
    expect(String(errSpy.mock.calls[0][0])).toContain('未检测到 Android 设备')
  })

  it('AppSnapshotsPane:删除快照走二次确认,确认后调 deleteUiAuthState 并刷新', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const w = mountPane()
    await flushPromises()
    await w.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'android')
    await flushPromises()
    await btnIn(w, 'AppSnapshotsPane', '删除').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalled() // 二次确认
    expect(String(vi.mocked(ElMessageBox.confirm).mock.calls[0][0])).toContain('首页快照')
    expect(mocks.delAuth).toHaveBeenCalledWith(7)
    expect(mocks.listAuth).toHaveBeenCalledTimes(2)
  })
})

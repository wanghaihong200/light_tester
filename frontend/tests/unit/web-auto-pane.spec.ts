import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只 mock 数据拉取;RecorderPanel 用保留 props 的具名 stub 替身——
// 编排逻辑(弹框时机/透传 authStateId)在 WebAutoPane,录制行为本身归 recorder-panel.spec
const mocks = vi.hoisted(() => ({
  listScripts: vi.fn(async () => []),
  listRuns: vi.fn(async () => []),
  listAuth: vi.fn(async () => [] as { id: number; project_id: number; name: string; created_at: string }[]),
  createScript: vi.fn(async () => ({ id: 1 })),
  deleteScript: vi.fn(async () => undefined),
}))
vi.mock('../../src/api/uiAutomation', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  listUiScripts: mocks.listScripts,
  listUiRuns: mocks.listRuns,
  listUiAuthStates: mocks.listAuth,
  createUiScript: mocks.createScript,
  deleteUiScript: mocks.deleteScript,
}))

import WebAutoPane from '../../src/components/webauto/WebAutoPane.vue'

const AUTH = { id: 3, project_id: 1, name: 'testerhome', created_at: '2026-09-03T10:00:00' }

function mountPane() {
  return mount(WebAutoPane, {
    props: { projectId: 1 },
    global: {
      plugins: [ElementPlus],
      stubs: {
        RecorderPanel: {
          name: 'RecorderPanelStub',
          props: ['projectId', 'authStateId'],
          template: '<div class="recorder-stub" />',
        },
        RunDialog: {
          name: 'RunDialogStub',
          props: ['projectId', 'queue', 'history'],
          template: '<div class="run-dialog-stub" />',
        },
      },
    },
  })
}

describe('WebAutoPane 录制入口', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('项目存在登录态:点「新建录制」先弹登录态选择框,确认后带 authStateId 挂录制面板', async () => {
    mocks.listAuth.mockResolvedValueOnce([AUTH])
    const w = mountPane()
    await flushPromises()

    await w.findAll('button').find((b) => b.text().includes('新建录制'))!.trigger('click')
    await flushPromises()
    expect(w.findComponent({ name: 'RecorderPanelStub' }).exists()).toBe(false) // 未确认不进录制
    expect(w.text()).toContain('录制浏览器将以该身份打开页面')

    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 3)
    await flushPromises()
    await w.findAll('button').find((b) => b.text().trim() === '开始录制')!.trigger('click')
    await flushPromises()
    const panel = w.findComponent({ name: 'RecorderPanelStub' })
    expect(panel.exists()).toBe(true)
    expect(panel.props('authStateId')).toBe(3)
  })

  it('项目无登录态:点「新建录制」直接进录制面板,不弹选择框、不带登录态', async () => {
    const w = mountPane()
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('新建录制'))!.trigger('click')
    await flushPromises()
    expect(w.text()).not.toContain('录制浏览器将以该身份打开页面')
    expect(w.findComponent({ name: 'RecorderPanelStub' }).props('authStateId')).toBeUndefined()
  })

  it('登录态拉取失败:不阻塞录制,直接进面板(与执行链路「拉不到不阻塞」同口径)', async () => {
    mocks.listAuth.mockRejectedValueOnce(new Error('network down'))
    const w = mountPane()
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('新建录制'))!.trigger('click')
    await flushPromises()
    expect(w.findComponent({ name: 'RecorderPanelStub' }).exists()).toBe(true)
  })

  it('执行方式切换:默认无头;切「有头执行」后执行/批量都带 mode=headed(功能4)', async () => {
    mocks.listScripts.mockResolvedValueOnce([{
      id: 1, project_id: 1, name: '冒烟脚本', description: null,
      script: { version: 1, meta: { start_url: '' }, variables: [], steps: [] },
      created_at: '2026-09-03T10:00:00', updated_at: '2026-09-03T10:00:00',
    }])
    const w = mountPane()
    await flushPromises()
    const runBtn = () => w.findAll('button').find((b) => b.text().trim() === '执行')!
    await runBtn().trigger('click')
    await flushPromises()
    const dialog = () => w.findComponent({ name: 'RunDialogStub' })
    expect(dialog().props('queue')[0].mode).toBe('headless') // 默认无头

    await w.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'headed')
    await runBtn().trigger('click')
    await flushPromises()
    expect(dialog().props('queue')[0].mode).toBe('headed') // 单脚本执行带上有头

    await w.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'headless')
    // 勾选一行 → 批量执行
    await w.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [mocks.listScripts.mock.results[0].value[0]])
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('批量执行'))!.trigger('click')
    await flushPromises()
    expect(dialog().props('queue')[0].mode).toBe('headless') // 批量同样跟随切换
  })
})

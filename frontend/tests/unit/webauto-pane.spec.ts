import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

// mock 返回结构对齐真实 API 契约:script 是 {version,meta,variables,steps} 文档,steps 为数组
const mocks = vi.hoisted(() => ({
  list: vi.fn(async () => [
    {
      id: 1,
      project_id: 1,
      name: '登录脚本',
      description: null,
      script: { version: 1, meta: { start_url: 'https://x' }, variables: [], steps: [{ id: 's1', action: 'click' }] },
      created_at: '2026-09-02T10:00:00',
      updated_at: '2026-09-02T10:00:00',
    },
  ]),
  del: vi.fn(async () => undefined),
  create: vi.fn(async () => ({})),
  listRuns: vi.fn(async () => [
    {
      id: 9,
      project_id: 1,
      status: 'completed',
      script_id: 1,
      script_name: '登录脚本',
      mode: 'headless',
      variables: {},
      step_results: [],
      steps_total: 1,
      steps_passed: 1,
      steps_failed: 0,
      error: null,
      started_at: '2026-09-02T10:01:00',
      finished_at: '2026-09-02T10:01:05',
    },
  ]),
}))
vi.mock('../../src/api/uiAutomation', () => ({
  listUiScripts: mocks.list,
  deleteUiScript: mocks.del,
  createUiScript: mocks.create,
  listUiRuns: mocks.listRuns,
  // 其余函数占位,避免 import 报错
  updateUiScript: vi.fn(), startRecording: vi.fn(), insertAssert: vi.fn(),
  stopRecording: vi.fn(), cancelRecording: vi.fn(), createUiRun: vi.fn(),
  getUiRun: vi.fn(), listUiAuthStates: vi.fn(async () => []),
  deleteUiAuthState: vi.fn(), collectAuthState: vi.fn(), saveAuthState: vi.fn(),
  cancelAuthCollect: vi.fn(), subscribeRecordingEvents: vi.fn(() => () => {}),
  subscribeRunEvents: vi.fn(() => () => {}),
}))

import WebAutoPane from '../../src/components/webauto/WebAutoPane.vue'

function mountPane() {
  return mount(WebAutoPane, {
    props: { projectId: 1 },
    global: { plugins: [ElementPlus], stubs: { RunDialog: true } },
  })
}

describe('WebAutoPane', () => {
  it('加载并列出脚本,显示步骤数', async () => {
    const w = mountPane()
    await flushPromises()
    expect(mocks.list).toHaveBeenCalledWith(1)
    expect(w.text()).toContain('登录脚本')
    expect(w.text()).toContain('1') // 步骤数
  })

  it('批量执行按钮在无选中时禁用', async () => {
    const w = mountPane()
    await flushPromises()
    const btn = w.findAll('button').find((b) => b.text().includes('批量执行'))!
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.classes()).toContain('is-disabled')
  })

  it('点击「历史」按脚本拉取执行记录并进入历史模式', async () => {
    const w = mountPane()
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('历史'))!.trigger('click')
    await flushPromises()
    expect(mocks.listRuns).toHaveBeenCalledWith(1, 1)
    expect(w.html()).toContain('run-dialog-stub')
  })
})

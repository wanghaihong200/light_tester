import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// InstanceDialog 同 MockPane:projectId 从路由取参(覆写 useRoute,不挂真实路由)
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '3' }, name: 'project-mock-http', path: '/projects/3/mock/http' }),
}))

const api = vi.hoisted(() => ({
  createMockInstance: vi.fn(),
  updateMockInstance: vi.fn(),
}))

vi.mock('../../src/api/mock', () => api)

import InstanceDialog from '../../src/components/mock/InstanceDialog.vue'
import type { MockInstance } from '../../src/types'

function mkInstance(over: Partial<MockInstance> = {}): MockInstance {
  return {
    id: 1, project_id: 3, name: '订单Mock', description: null, port: 18081,
    cors_enabled: true, default_status: 200, default_body: null,
    desired: 'running', status: 'running', error_message: null,
    created_at: '2026-09-08T10:00:00', updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
const RUNNING = mkInstance()
const STOPPED = mkInstance({ id: 2, name: '支付Mock', port: 18082, desired: 'stopped', status: 'stopped' })

// 与 mock-pane.spec 同形态:装真 Element Plus,对话框挂 document.body 后按文本定位按钮
const mountDialog = (instance: MockInstance | null) =>
  mount(InstanceDialog, { props: { instance }, global: { plugins: [ElementPlus] }, attachTo: document.body })

const saveBtn = () =>
  [...document.querySelectorAll('.el-dialog button')].find((b) => b.textContent?.trim() === '保存')!

const nameInput = () =>
  document.querySelector<HTMLInputElement>('.el-dialog input[placeholder="实例名称"]')!

describe('InstanceDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.updateMockInstance.mockResolvedValue({ ...RUNNING })
    api.createMockInstance.mockResolvedValue({ ...STOPPED })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('edit 模式:running/starting 实例 port 控件禁用,保存走 updateMockInstance', async () => {
    const w = mountDialog(RUNNING)
    await flushPromises()
    const portInput = document.querySelector<HTMLInputElement>('.el-dialog input[placeholder="留空自动分配"]')!
    expect(portInput.disabled).toBe(true)
    expect(portInput.value).toBe('18081')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.updateMockInstance).toHaveBeenCalledWith(1, expect.objectContaining({ name: '订单Mock', port: 18081 }))
    expect(api.createMockInstance).not.toHaveBeenCalled()
    expect(w.emitted('saved')).toBeTruthy()
    w.unmount()
  })

  it('edit 模式:stopped 实例 port 控件可用', async () => {
    const w = mountDialog(STOPPED)
    await flushPromises()
    const portInput = document.querySelector<HTMLInputElement>('.el-dialog input[placeholder="留空自动分配"]')!
    expect(portInput.disabled).toBe(false)
    w.unmount()
  })

  it('新建:名称+兜底配置随保存提交;2026-09-13 起透传不在实例对话框(已移规则组级)', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await new DOMWrapper(nameInput()).setValue('库存Mock')
    // 实例对话框不再渲染透传配置(开关/上游地址都在 GroupDialog)
    expect(w.find('[data-test="passthrough-switch"]').exists()).toBe(false)
    expect(w.find('[data-test="upstream-url"]').exists()).toBe(false)
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockInstance).toHaveBeenCalledWith(3, expect.objectContaining({
      name: '库存Mock', cors_enabled: false, default_status: 200, default_body: null,
    }))
    const body = api.createMockInstance.mock.calls[0][1] as Record<string, unknown>
    expect('passthrough_enabled' in body).toBe(false)  // body 不携带已移除的字段
    w.unmount()
  })

  it('编辑:描述与默认响应体随 updateMockInstance 提交', async () => {
    const w = mountDialog(mkInstance({ description: 'd', default_body: '{"x":1}' }))
    await flushPromises()
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.updateMockInstance).toHaveBeenCalledWith(1, expect.objectContaining({
      description: 'd', default_body: '{"x":1}',
    }))
    w.unmount()
  })
})

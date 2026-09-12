import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
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
    passthrough_enabled: false, upstream_base_url: null,
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

// el-input 会把非 prop 属性(含 data-test)透传到内部原生 <input>(EP 行为);
// 逗号选择器同时兼容「落在组件根 div」与「落在原生 input」两种落点
const upstreamInput = (w: ReturnType<typeof mountDialog>) =>
  w.find('input[data-test="upstream-url"], [data-test="upstream-url"] input')

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

  it('新建:透传开关开启后须先填上游地址才能保存(前端校验),补齐后两字段随 body 提交', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await new DOMWrapper(nameInput()).setValue('库存Mock')
    expect(w.find('[data-test="upstream-url"]').exists()).toBe(false) // 开关默认关:不渲染上游地址
    await w.find('[data-test="passthrough-switch"]').find('.el-switch__core').trigger('click')
    expect(w.find('[data-test="upstream-url"]').exists()).toBe(true) // 开关开:条件渲染上游地址
    // 开关开且地址为空 → 保存被前端校验拦截,不发请求
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockInstance).not.toHaveBeenCalled()
    // 补齐上游地址 → 两字段随保存提交
    await upstreamInput(w).setValue('http://real:8080')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockInstance).toHaveBeenCalledWith(3, expect.objectContaining({
      name: '库存Mock', passthrough_enabled: true, upstream_base_url: 'http://real:8080',
    }))
    w.unmount()
  })

  it('新建:透传开关关闭时保存不带上游地址(passthrough_enabled=false, upstream_base_url=null)', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await new DOMWrapper(nameInput()).setValue('库存Mock')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockInstance).toHaveBeenCalledWith(3, expect.objectContaining({
      passthrough_enabled: false, upstream_base_url: null,
    }))
    w.unmount()
  })

  it('上游地址非空时须 http(s):// 开头:scheme 不符保存被拦并 warning(对齐后端 400 文案语义)', async () => {
    const warnSpy = vi.spyOn(ElMessage, 'warning')
    const w = mountDialog(null)
    await flushPromises()
    await new DOMWrapper(nameInput()).setValue('库存Mock')
    await w.find('[data-test="passthrough-switch"]').find('.el-switch__core').trigger('click')
    await upstreamInput(w).setValue('real-api:8080') // 无 scheme → 拦
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockInstance).not.toHaveBeenCalled()
    expect(String(warnSpy.mock.calls[0][0])).toContain('http:// 或 https://')
    // 补上 scheme → 放行提交
    await upstreamInput(w).setValue('https://real:8443')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockInstance).toHaveBeenCalledWith(3, expect.objectContaining({
      passthrough_enabled: true, upstream_base_url: 'https://real:8443',
    }))
    w.unmount()
  })

  it('编辑:透传字段从实例初始化并随 updateMockInstance 提交', async () => {
    const w = mountDialog(mkInstance({ passthrough_enabled: true, upstream_base_url: 'http://real:9999' }))
    await flushPromises()
    const upstream = upstreamInput(w)
    expect((upstream.element as HTMLInputElement).value).toBe('http://real:9999')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.updateMockInstance).toHaveBeenCalledWith(1, expect.objectContaining({
      passthrough_enabled: true, upstream_base_url: 'http://real:9999',
    }))
    w.unmount()
  })
})

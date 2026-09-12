import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// MockPane 按 brief 无 projectId prop、从路由取参:覆写 useRoute;「详情」跳转需 useRouter(appauto-entry.spec 同款形态)
const routerPush = vi.hoisted(() => vi.fn())
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '3' }, name: 'project-mock-http', path: '/projects/3/mock/http' }),
  useRouter: () => ({ push: routerPush }),
}))

const api = vi.hoisted(() => ({
  listMockInstances: vi.fn(),
  createMockInstance: vi.fn(),
  updateMockInstance: vi.fn(),
  deleteMockInstance: vi.fn(),
  startMockInstance: vi.fn(),
  stopMockInstance: vi.fn(),
}))

vi.mock('../../src/api/mock', () => api)

import MockPane from '../../src/components/mock/MockPane.vue'
import type { MockInstance, MockInstanceStatus } from '../../src/types'

function mkInstance(over: Partial<MockInstance> = {}): MockInstance {
  return {
    id: 1, project_id: 3, name: '订单Mock', description: null, port: 18081,
    cors_enabled: true, default_status: 200, default_body: null,
    passthrough_enabled: false, upstream_base_url: null,
    desired: 'stopped', status: 'stopped', error_message: null,
    created_at: '2026-09-08T10:00:00', updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
const RUNNING = mkInstance({ id: 1, name: '订单Mock', port: 18081, desired: 'running', status: 'running' })
const STOPPED = mkInstance({ id: 2, name: '支付Mock', port: 18082 })
const ERRORED = mkInstance({
  id: 3, name: '库存Mock', port: 18083, desired: 'running', status: 'error' as MockInstanceStatus,
  error_message: '端口 18083 被占用',
})

// el-table 作用域插槽形态对齐 appauto-pane.spec:装真 Element Plus,不桩 el-table/el-dialog
const mountPane = () =>
  mount(MockPane, { global: { plugins: [ElementPlus] }, attachTo: document.body })

const btn = (w: ReturnType<typeof mountPane>, text: string) =>
  w.findAll('button').find((b) => b.text().includes(text))!

const rowBtn = (w: ReturnType<typeof mountPane>, rowIndex: number, text: string) => {
  const cells = w.findAll('.el-table__row')[rowIndex].findAll('button')
  return cells.find((b) => b.text().includes(text))!
}

// 计划15 T9:MockPane 瘦身为纯实例列表,规则/命中下钻到独立路由(本 spec 只测实例列表)
describe('MockPane', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listMockInstances.mockResolvedValue([RUNNING, STOPPED, ERRORED])
    api.startMockInstance.mockResolvedValue({ ...STOPPED, desired: 'running', status: 'starting' })
    api.stopMockInstance.mockResolvedValue({ ...RUNNING, desired: 'stopped', status: 'stopped' })
    api.deleteMockInstance.mockResolvedValue(undefined)
    api.createMockInstance.mockImplementation(async (_pid: number, body: { name: string }) => ({
      ...mkInstance({ id: 9, name: body.name, port: 19000 }),
    }))
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('列表渲染名称/端口/状态 tag/base_url 与复制按钮;error 行展示 error_message', async () => {
    const w = mountPane()
    await flushPromises()
    expect(api.listMockInstances).toHaveBeenCalledWith(3)
    expect(w.text()).toContain('订单Mock')
    expect(w.text()).toContain('18081')
    expect(w.text()).toContain('18082')
    // base_url 用 location.hostname 拼装(jsdom=localhost),带复制按钮
    expect(w.text()).toContain('http://localhost:18081')
    expect(w.text()).toContain('http://localhost:18082')
    expect(w.text()).toContain('复制')
    // 状态 tag:running=success / stopped=info / error=danger
    expect(w.html()).toContain('el-tag--success')
    expect(w.html()).toContain('el-tag--info')
    expect(w.html()).toContain('el-tag--danger')
    // error 态行内展示 error_message
    expect(w.text()).toContain('端口 18083 被占用')
    w.unmount()
  })

  it('操作列「详情」跳转规则组详情路由(project-mock-http-detail)', async () => {
    const w = mountPane()
    await flushPromises()
    expect(routerPush).not.toHaveBeenCalled()
    await w.find('[data-test="instance-detail-18081"]').trigger('click')
    expect(routerPush).toHaveBeenCalledTimes(1)
    // instanceId 取自行数据(RUNNING.id=1),目标路由名即 T10 详情页契约;
    // params 须含父级 id(缺它在真实浏览器抛 Missing required param「id」),完整形状防回归
    expect(routerPush).toHaveBeenCalledWith({
      name: 'project-mock-http-detail', params: { id: 3, instanceId: 1 },
    })
    w.unmount()
  })

  it('实例列表页不再内嵌规则表/命中面板;每行操作列都有详情入口', async () => {
    const w = mountPane()
    await flushPromises()
    expect(w.find('[data-test="rules-table"]').exists()).toBe(false)
    expect(w.find('[data-test="hits-table"]').exists()).toBe(false)
    expect(w.text()).not.toContain('选择左侧实例查看规则与命中')
    expect(w.findAll('[data-test^="instance-detail-"]').length).toBe(3)
    w.unmount()
  })

  it('启动/停止按钮分别调用 start/stop API 并刷新列表', async () => {
    const w = mountPane()
    await flushPromises()
    // 行序与 fixture 一致:0=running(显示停止) 1=stopped(显示启动) 2=error(显示启动)
    await rowBtn(w, 1, '启动').trigger('click')
    await flushPromises()
    expect(api.startMockInstance).toHaveBeenCalledWith(2)
    expect(api.listMockInstances).toHaveBeenCalledTimes(2)
    await rowBtn(w, 0, '停止').trigger('click')
    await flushPromises()
    expect(api.stopMockInstance).toHaveBeenCalledWith(1)
    expect(api.listMockInstances).toHaveBeenCalledTimes(3)
    w.unmount()
  })

  it('删除走 elMessageBox.confirm,确认后调 deleteMockInstance 并刷新', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const w = mountPane()
    await flushPromises()
    await rowBtn(w, 0, '删除').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(String(vi.mocked(ElMessageBox.confirm).mock.calls[0][0])).toContain('订单Mock')
    expect(api.deleteMockInstance).toHaveBeenCalledWith(1)
    expect(api.listMockInstances).toHaveBeenCalledTimes(2)
    w.unmount()
  })

  it('新建实例对话框保存调用 createMockInstance(port 留空=null)并刷新列表', async () => {
    const w = mountPane()
    await flushPromises()
    await btn(w, '新建实例').trigger('click')
    await flushPromises()
    const dlg = [...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('新建实例'))!
    const nameInput = dlg.querySelector<HTMLInputElement>('input[placeholder="实例名称"]')!
    await new DOMWrapper(nameInput).setValue('库存Mock')
    const saveBtn = [...dlg.querySelectorAll('button')].find((b) => b.textContent?.trim() === '保存')!
    await new DOMWrapper(saveBtn).trigger('click')
    await flushPromises()
    expect(api.createMockInstance).toHaveBeenCalledWith(3, expect.objectContaining({
      name: '库存Mock', port: null, cors_enabled: false, default_status: 200,
    }))
    expect(api.listMockInstances).toHaveBeenCalledTimes(2) // 保存成功后刷新
    // saved 后对话框关闭
    expect([...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('新建实例'))).toBeUndefined()
    w.unmount()
  })

  it('轮询:存在 running 实例时每 5s 刷新,卸载清理;全部 stopped 不启动定时器', async () => {
    vi.useFakeTimers()
    let w = mountPane()
    await vi.advanceTimersByTimeAsync(0) // 让 onMounted 的异步 reload 落地
    expect(api.listMockInstances).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.listMockInstances).toHaveBeenCalledTimes(2)
    w.unmount()
    await vi.advanceTimersByTimeAsync(15000)
    expect(api.listMockInstances).toHaveBeenCalledTimes(2) // 卸载后定时器已清理

    api.listMockInstances.mockResolvedValue([STOPPED])
    w = mountPane()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(15000)
    expect(api.listMockInstances).toHaveBeenCalledTimes(3) // 无 starting/running 不轮询,仅挂载那 1 次
    w.unmount()
  })

  it('卸载时在途 reload resolve 后不复活轮询定时器(disposed 守卫)', async () => {
    vi.useFakeTimers()
    let resolveList: (v: MockInstance[]) => void = () => {}
    api.listMockInstances.mockImplementation(
      () => new Promise((res) => { resolveList = res as (v: MockInstance[]) => void }),
    )
    const w = mountPane()
    await vi.advanceTimersByTimeAsync(0) // onMounted 的 reload 已发出但仍挂起
    expect(api.listMockInstances).toHaveBeenCalledTimes(1)
    w.unmount() // 此刻卸载:timer 尚未建立,disposed 置位
    resolveList([RUNNING]) // 在途请求卸载后才 resolve
    await vi.advanceTimersByTimeAsync(0) // 让 resolve 后的续段(syncPolling)执行
    await vi.advanceTimersByTimeAsync(15000)
    // 修复前:syncPolling 见 running → 重新 setInterval → 这里会被再调,永久泄漏
    expect(api.listMockInstances).toHaveBeenCalledTimes(1)
  })
})

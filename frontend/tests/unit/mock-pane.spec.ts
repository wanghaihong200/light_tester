import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// MockPane/InstanceDialog 均按 brief 无 projectId prop、从路由取参:覆写 useRoute(appauto-entry.spec 同款形态)
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '3' }, name: 'project-mock-http', path: '/projects/3/mock/http' }),
}))

const api = vi.hoisted(() => ({
  listMockInstances: vi.fn(),
  createMockInstance: vi.fn(),
  updateMockInstance: vi.fn(),
  deleteMockInstance: vi.fn(),
  startMockInstance: vi.fn(),
  stopMockInstance: vi.fn(),
  // 占位对齐 webauto-pane.spec 预防式写法:规则/命中 API 本 spec 不消费
  listMockRules: vi.fn(), createMockRule: vi.fn(), updateMockRule: vi.fn(), deleteMockRule: vi.fn(),
  reorderMockRules: vi.fn(), listMockHits: vi.fn(), getMockHit: vi.fn(), clearMockHits: vi.fn(),
}))

vi.mock('../../src/api/mock', () => api)

import InstanceDialog from '../../src/components/mock/InstanceDialog.vue'
import MockPane from '../../src/components/mock/MockPane.vue'
import type { MockInstance, MockInstanceStatus, MockRule } from '../../src/types'

function mkInstance(over: Partial<MockInstance> = {}): MockInstance {
  return {
    id: 1, project_id: 3, name: '订单Mock', description: null, port: 18081,
    cors_enabled: true, default_status: 200, default_body: null,
    desired: 'stopped', status: 'stopped', error_message: null,
    created_at: '2026-09-08T10:00:00', updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
const RUNNING = mkInstance({ id: 1, name: '订单Mock', port: 18081, desired: 'running', status: 'running' })
const STOPPED = mkInstance({ id: 2, name: '支付Mock', port: 18082, desired: 'stopped', status: 'stopped' })
const ERRORED = mkInstance({
  id: 3, name: '库存Mock', port: 18083, desired: 'running', status: 'error' as MockInstanceStatus,
  error_message: '端口 18083 被占用',
})

function mkRule(over: Partial<MockRule> = {}): MockRule {
  return {
    id: 11, instance_id: 1, method: 'GET', path_template: '/users/{id}',
    conditions: [{ scope: 'query', key: 'id', match: 'eq', value: '42' }],
    enabled: true, response_status: 200, response_headers: {}, response_body: null,
    enable_template: false, delay_ms: 0, timeout_enabled: false, timeout_seconds: 30,
    sort_order: 0, updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
const R1 = mkRule({ id: 11, method: 'GET', path_template: '/users/{id}' })
const R2 = mkRule({ id: 12, method: 'POST', path_template: '/orders', conditions: [], response_status: 201, delay_ms: 300 })
const R3 = mkRule({ id: 13, method: 'DELETE', path_template: '/items/{id}', timeout_enabled: true, timeout_seconds: 10 })

// el-table 作用域插槽形态对齐 appauto-pane.spec:装真 Element Plus,不桩 el-table/el-dialog
const mountPane = () =>
  mount(MockPane, { global: { plugins: [ElementPlus] }, attachTo: document.body })

const btn = (w: ReturnType<typeof mountPane>, text: string) =>
  w.findAll('button').find((b) => b.text().includes(text))!

const rowBtn = (w: ReturnType<typeof mountPane>, rowIndex: number, text: string) => {
  const cells = w.findAll('.el-table__row')[rowIndex].findAll('button')
  return cells.find((b) => b.text().includes(text))!
}

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
    api.listMockRules.mockResolvedValue([R1, R2, R3])
    api.listMockHits.mockResolvedValue([]) // 选中实例即挂 HitsPanel(T11):默认空命中,个别用例自覆写
    api.reorderMockRules.mockImplementation(async (_iid: number, ids: number[]) => {
      const byId = new Map([R1, R2, R3].map((r) => [r.id, r]))
      return ids.map((id) => byId.get(id)!)
    })
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

  it('选中实例后右侧详情展示头部、规则真实列表与 HitsPanel(T11 占位已替换)', async () => {
    const w = mountPane()
    await flushPromises()
    expect(w.find('[data-test="rules-placeholder"]').exists()).toBe(false) // 未选中时不渲染详情
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', RUNNING)
    await flushPromises()
    expect(w.text()).toContain('订单Mock')
    expect(w.text()).toContain('http://localhost:18081')
    expect(w.text()).toContain('命中记录')
    // 两个占位都已被真实组件替换(T10 规则 / T11 命中)
    expect(w.find('[data-test="rules-placeholder"]').exists()).toBe(false)
    expect(w.find('[data-test="hits-placeholder"]').exists()).toBe(false)
    // HitsPanel 挂载即按选中实例拉命中(全部过滤;limit 走 api 默认 200)
    expect(api.listMockHits).toHaveBeenCalledWith(1, 'all')
    expect(w.find('[data-test="hits-table"]').exists()).toBe(true)
    w.unmount()
  })

  it('选中行在 reload(同 id 全新对象引用)后详情区保持,row-key 按 id 恢复 currentRow', async () => {
    const w = mountPane()
    await flushPromises()
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', RUNNING)
    await flushPromises()
    expect(w.find('[data-test="rules-table"]').exists()).toBe(true)
    // 模拟轮询/操作刷新:同 id 全新对象引用整体替换数组(评审指出的引用失效场景)
    api.listMockInstances.mockResolvedValue([
      mkInstance({ id: 1, name: '订单Mock', port: 18081, desired: 'running', status: 'running' }),
      mkInstance({ id: 2, name: '支付Mock', port: 18082 }),
    ])
    await rowBtn(w, 0, '停止').trigger('click')
    await flushPromises()
    // 修复前:旧引用不在新数组 → EP 将 currentRow 置 null 并 emit current-change(null) → 详情坍缩
    expect(w.find('[data-test="rules-table"]').exists()).toBe(true)
    expect(w.text()).toContain('订单Mock')
    expect(w.text()).not.toContain('选择左侧实例查看规则与命中')
    w.unmount()
  })

  it('规则页签:选中实例拉取并渲染规则行(排序钮/method+path/条件数/状态码/开关/延迟/超时),换选实例重拉', async () => {
    const w = mountPane()
    await flushPromises()
    expect(api.listMockRules).not.toHaveBeenCalled() // 未选中实例不拉规则
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', RUNNING)
    await flushPromises()
    expect(api.listMockRules).toHaveBeenCalledWith(1)
    const routes = () => w.findAll('[data-test="rule-route"]').map((r) => r.text())
    expect(routes()).toEqual(['GET /users/{id}', 'POST /orders', 'DELETE /items/{id}'])
    // R1 一条条件 → 条件数列出现 1;R2 延迟 300ms;R3 超时标记 warning tag
    expect(w.findAll('.rules-tab .el-table__row')[0].text()).toContain('1')
    expect(w.text()).toContain('300ms')
    expect(w.html()).toContain('el-tag--warning')
    // 启用开关一列一行一个
    expect(w.findAll('.rules-tab .el-switch').length).toBe(3)
    // 排序钮:首行禁↑尾行禁↓
    const rows = () => w.findAll('.rules-tab .el-table__row')
    expect(rows()[0].find('[data-test="rule-up"]').attributes('disabled')).toBeDefined()
    expect(rows()[0].find('[data-test="rule-down"]').attributes('disabled')).toBeUndefined()
    expect(rows()[2].find('[data-test="rule-down"]').attributes('disabled')).toBeDefined()
    expect(rows()[2].find('[data-test="rule-up"]').attributes('disabled')).toBeUndefined()
    // 换选另一实例 → 以新 id 重拉
    api.listMockRules.mockClear()
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', STOPPED)
    await flushPromises()
    expect(api.listMockRules).toHaveBeenCalledTimes(1)
    expect(api.listMockRules).toHaveBeenCalledWith(2)
    w.unmount()
  })

  it('排序:点击行内↓以新序全量调 reorderMockRules 并应用返回列表', async () => {
    const w = mountPane()
    await flushPromises()
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', RUNNING)
    await flushPromises()
    api.reorderMockRules.mockClear()
    await w.findAll('.rules-tab .el-table__row')[0].find('[data-test="rule-down"]').trigger('click')
    await flushPromises()
    // 载荷是交换后的完整新序(不是 delta),instanceId 来自选中实例
    expect(api.reorderMockRules).toHaveBeenCalledTimes(1)
    expect(api.reorderMockRules).toHaveBeenCalledWith(1, [12, 11, 13])
    // 应用 reorder 返回的新列表
    expect(w.findAll('[data-test="rule-route"]').map((r) => r.text()))
      .toEqual(['POST /orders', 'GET /users/{id}', 'DELETE /items/{id}'])
    w.unmount()
  })

  it('启用开关:点击直接 updateMockRule 只传 enabled,成功后按返回回贴', async () => {
    const w = mountPane()
    await flushPromises()
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', RUNNING)
    await flushPromises()
    api.updateMockRule.mockResolvedValue({ ...R1, enabled: false })
    await w.findAll('.rules-tab .el-table__row')[0].find('.el-switch').trigger('click')
    await flushPromises()
    expect(api.updateMockRule).toHaveBeenCalledTimes(1)
    expect(api.updateMockRule).toHaveBeenCalledWith(11, { enabled: false })
    w.unmount()
  })

  it('删除规则:confirm 文案含 method+path,确认后 deleteMockRule 并重拉规则', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const w = mountPane()
    await flushPromises()
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', RUNNING)
    await flushPromises()
    expect(api.listMockRules).toHaveBeenCalledTimes(1)
    await w.findAll('.rules-tab .el-table__row')[0].findAll('button')
      .find((b) => b.text().includes('删除'))!.trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(String(vi.mocked(ElMessageBox.confirm).mock.calls[0][0])).toContain('GET /users/{id}')
    expect(api.deleteMockRule).toHaveBeenCalledWith(11)
    expect(api.listMockRules).toHaveBeenCalledTimes(2) // 删除后重拉
    w.unmount()
  })

  it('「新建规则」入口开 RuleDialog,取消后关闭', async () => {
    const w = mountPane()
    await flushPromises()
    w.findComponent({ name: 'ElTable' }).vm.$emit('current-change', RUNNING)
    await flushPromises()
    await w.find('[data-test="new-rule"]').trigger('click')
    await flushPromises()
    const openDlg = [...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('新建规则'))
    expect(openDlg).toBeTruthy()
    const cancel = [...openDlg!.querySelectorAll('button')].find((b) => b.textContent?.trim() === '取消')!
    await new DOMWrapper(cancel).trigger('click')
    await flushPromises()
    expect([...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('新建规则'))).toBeUndefined()
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

describe('InstanceDialog', () => {
  const mountDialog = (instance: MockInstance | null) =>
    mount(InstanceDialog, {
      props: { instance },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })

  const portInput = () =>
    document.querySelector<HTMLInputElement>('.el-dialog input[placeholder="留空自动分配"]')!

  beforeEach(() => {
    vi.clearAllMocks()
    api.updateMockInstance.mockResolvedValue({ ...RUNNING })
    api.createMockInstance.mockResolvedValue({ ...STOPPED })
  })

  it('edit 模式:running/starting 实例 port 控件禁用,保存走 updateMockInstance', async () => {
    const w = mountDialog(RUNNING)
    await flushPromises()
    expect(portInput().disabled).toBe(true)
    expect(portInput().value).toBe('18081')
    const saveBtn = [...document.querySelectorAll('.el-dialog button')]
      .find((b) => b.textContent?.trim() === '保存')!
    await new DOMWrapper(saveBtn).trigger('click')
    await flushPromises()
    expect(api.updateMockInstance).toHaveBeenCalledWith(1, expect.objectContaining({ name: '订单Mock', port: 18081 }))
    expect(api.createMockInstance).not.toHaveBeenCalled()
    expect(w.emitted('saved')).toBeTruthy()
    w.unmount()
  })

  it('edit 模式:stopped 实例 port 控件可用', async () => {
    const w = mountDialog(STOPPED)
    await flushPromises()
    expect(portInput().disabled).toBe(false)
    w.unmount()
  })
})

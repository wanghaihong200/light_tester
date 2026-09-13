import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

// RuleGroupPane 同 MockPane:instanceId/projectId 从路由取参;openHits 跳命中页需 useRouter
const routerPush = vi.hoisted(() => vi.fn())
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({
    params: { id: '3', instanceId: '5' },
    name: 'project-mock-http-detail', path: '/projects/3/mock/http/5',
  }),
  useRouter: () => ({ push: routerPush }),
}))

// 桩对象需覆盖整棵组件树(RuleGroupPane→GroupDialog/RuleDialog)用到的全部 api/mock 导出
const api = vi.hoisted(() => ({
  getMockInstance: vi.fn(),
  listMockRuleGroups: vi.fn(),
  createMockRuleGroup: vi.fn(),
  updateMockRuleGroup: vi.fn(),
  deleteMockRuleGroup: vi.fn(),
  reorderMockGroups: vi.fn(),
  reorderMockGroupRules: vi.fn(),
  createMockRule: vi.fn(),
  updateMockRule: vi.fn(),
  deleteMockRule: vi.fn(),
}))

vi.mock('../../src/api/mock', () => api)

import GroupDialog from '../../src/components/mock/GroupDialog.vue'
import RuleDialog from '../../src/components/mock/RuleDialog.vue'
import RuleGroupPane from '../../src/components/mock/RuleGroupPane.vue'
import type { MockInstance, MockRule, MockRuleGroup } from '../../src/types'

function mkInstance(over: Partial<MockInstance> = {}): MockInstance {
  return {
    id: 5, project_id: 3, name: '订单Mock', description: null, port: 18081,
    cors_enabled: true, default_status: 200, default_body: null,
    passthrough_enabled: false, upstream_base_url: null,
    desired: 'running', status: 'running', error_message: null,
    created_at: '2026-09-08T10:00:00', updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
function mkRule(over: Partial<MockRule> = {}): MockRule {
  return {
    id: 11, instance_id: 5, group_id: 1,
    conditions: [{ scope: 'query', key: 'id', match: 'eq', value: '42' }],
    enabled: true, response_status: 200, response_headers: {},
    response_body: null, enable_template: false, delay_ms: 0,
    timeout_enabled: false, timeout_seconds: 30, sort_order: 0, updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
function mkGroup(over: Partial<MockRuleGroup> = {}): MockRuleGroup {
  return {
    id: 1, instance_id: 5, method: 'GET', path_template: '/api/user/{id}',
    description: '查用户', enabled: true, passthrough_enabled: false, upstream_base_url: null, sort_order: 0, rules: [],
    updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}

// 默认两组各一规则;需要多规则/空组的用例在用例内覆写
const INSTANCE = mkInstance()
const G1 = mkGroup({ id: 1, rules: [mkRule({ id: 11, group_id: 1 })] })
const G2 = mkGroup({
  id: 2, method: 'POST', path_template: '/orders', description: null, sort_order: 1,
  rules: [mkRule({ id: 21, group_id: 2, enabled: false, response_status: 201 })],
})

// 与 mock-pane.spec 同形态:装真 Element Plus,attach 到 document.body
const mountPane = () =>
  mount(RuleGroupPane, { global: { plugins: [ElementPlus] }, attachTo: document.body })

// 组头工具区按钮(命中记录详情/编辑组/↑/↓/删除组/新建规则),按组 id 收敛
const gTools = (w: ReturnType<typeof mountPane>, gid: number) =>
  w.find(`[data-test="group-card-${gid}"] .g-tools`)
const gToolBtn = (w: ReturnType<typeof mountPane>, gid: number, text: string) =>
  gTools(w, gid).findAll('button').find((b) => b.text().trim() === text)!

describe('RuleGroupPane', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getMockInstance.mockResolvedValue(INSTANCE)
    api.listMockRuleGroups.mockResolvedValue([G1, G2])
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('组卡片渲染 method/path/描述,空描述不渲染占位;倒三角独占折叠控制(2026-09-13 验收反馈)', async () => {
    const w = mountPane()
    await flushPromises()
    expect(api.getMockInstance).toHaveBeenCalledWith(5)
    expect(api.listMockRuleGroups).toHaveBeenCalledWith(5)
    // 头部:实例名 + base_url tag
    expect(w.text()).toContain('订单Mock · 规则与命中记录')
    expect(w.text()).toContain('http://localhost:18081')
    // 组路由 mono 文案按序渲染
    const routes = w.findAll('[data-test="group-route"]').map((n) => n.text())
    expect(routes).toEqual(['GET /api/user/{id}', 'POST /orders'])
    // 描述有则显示;无则整个元素不渲染(不再有 '—' 占位)
    const descs = w.findAll('[data-test="group-desc"]').map((n) => n.text())
    expect(descs).toEqual(['查用户'])
    // 倒三角是唯一折叠入口:内容区点击不再切换折叠,点倒三角收起后再点展开
    expect(w.find('[data-test="group-toggle"]').text()).toBe('▾') // 默认全展开
    await w.find('[data-test="group-card-1"] [data-test="group-route"]').trigger('click')
    expect(w.find('[data-test="group-toggle"]').text()).toBe('▾') // 点路由文本不折叠
    await w.find('[data-test="group-card-1"] [data-test="group-toggle"]').trigger('click')
    expect(w.find('[data-test="group-toggle"]:first-of-type').text()).toBe('▸') // 倒三角收起
    w.unmount()
  })

  it('组级启停走 updateMockRuleGroup({enabled}) 且失败回原态', async () => {
    api.updateMockRuleGroup.mockRejectedValueOnce(new Error('后端不可用'))
    const w = mountPane()
    await flushPromises()
    const sw = () => w.find('[data-test="group-switch-1"]')
    expect(sw().classes()).toContain('is-checked') // 初始 enabled=true
    await sw().find('.el-switch__core').trigger('click')
    await flushPromises()
    expect(api.updateMockRuleGroup).toHaveBeenCalledWith(1, { enabled: false })
    expect(document.querySelector('.el-message')?.textContent).toContain('更新规则组失败')
    // 受控 switch:失败不翻面,回原态
    expect(sw().classes()).toContain('is-checked')
    // 成功:后端回贴后翻面
    api.updateMockRuleGroup.mockResolvedValue({ ...G1, enabled: false })
    await sw().find('.el-switch__core').trigger('click')
    await flushPromises()
    expect(sw().classes()).not.toContain('is-checked')
    w.unmount()
  })

  it('「命中记录详情」按钮跳命中页并带 group 查询参', async () => {
    const w = mountPane()
    await flushPromises()
    expect(routerPush).not.toHaveBeenCalled()
    await w.find('[data-test="group-hits"]').trigger('click')
    expect(routerPush).toHaveBeenCalledTimes(1)
    // 完整形状断言:params 须含父级 id(缺它在真实浏览器抛 Missing required param「id」)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'project-mock-http-hits', params: { id: 3 }, query: { group: String(G1.id) },
    })
    w.unmount()
  })

  it('组间↑↓调 reorderMockGroups 全量新序并回贴', async () => {
    const w = mountPane()
    await flushPromises()
    // 边界:首组 ↑ 与末组 ↓ 禁用
    expect(gToolBtn(w, 1, '↑').attributes('disabled')).toBeDefined()
    expect(gToolBtn(w, 2, '↓').attributes('disabled')).toBeDefined()
    api.reorderMockGroups.mockResolvedValueOnce([G2, G1])
    await gToolBtn(w, 1, '↓').trigger('click')
    await flushPromises()
    expect(api.reorderMockGroups).toHaveBeenCalledWith(5, [2, 1]) // 全量新序
    const routes = w.findAll('[data-test="group-route"]').map((n) => n.text())
    expect(routes).toEqual(['POST /orders', 'GET /api/user/{id}']) // 后端返回直接回贴
    w.unmount()
  })

  it('组内规则↑↓调 reorderMockGroupRules 并回贴', async () => {
    const G1X = mkGroup({
      id: 1, rules: [mkRule({ id: 11, group_id: 1 }), mkRule({ id: 12, group_id: 1, sort_order: 1 })],
    })
    api.listMockRuleGroups.mockResolvedValue([G1X, G2])
    const w = mountPane()
    await flushPromises()
    await w.find('[data-test="rules-of-1"] [data-test="rule-down"]').trigger('click')
    await flushPromises()
    expect(api.reorderMockGroupRules).toHaveBeenCalledWith(1, [12, 11]) // 组内全量新序
    expect(api.listMockRuleGroups).toHaveBeenCalledTimes(2) // 排序后 reload 回贴
    w.unmount()
  })

  it('删除组二次确认后调 deleteMockRuleGroup 并刷新', async () => {
    const conf = vi.spyOn(ElMessageBox, 'confirm')
    conf.mockRejectedValueOnce(new Error('cancel')) // 第一次:用户取消
    const w = mountPane()
    await flushPromises()
    await gToolBtn(w, 1, '删除组').trigger('click')
    await flushPromises()
    expect(api.deleteMockRuleGroup).not.toHaveBeenCalled()
    conf.mockResolvedValue({} as never) // 第二次:确认
    await gToolBtn(w, 1, '删除组').trigger('click')
    await flushPromises()
    // 确认文案带组路由与组内规则数
    const msg = String(conf.mock.calls[1][0])
    expect(msg).toContain('GET /api/user/{id}')
    expect(msg).toContain('1 条规则')
    expect(api.deleteMockRuleGroup).toHaveBeenCalledWith(1)
    expect(api.listMockRuleGroups).toHaveBeenCalledTimes(2) // 删除后 reload
    w.unmount()
  })

  it('删空组内规则:组保留并显空态占位', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    api.listMockRuleGroups.mockResolvedValueOnce([G1, G2]) // 初次:组1有一条规则
    api.listMockRuleGroups.mockResolvedValue([mkGroup({ id: 1, rules: [] }), G2]) // 删除后 reload
    const w = mountPane()
    await flushPromises()
    const delBtn = w.findAll('[data-test="rules-of-1"] button')
      .find((b) => b.text().trim() === '删除')!
    await delBtn.trigger('click')
    await flushPromises()
    expect(api.deleteMockRule).toHaveBeenCalledWith(11)
    // 删除后 reload:组卡片仍在(空组保留),组内显空态占位
    expect(w.find('[data-test="group-card-1"]').exists()).toBe(true)
    expect(w.text()).toContain('组内暂无规则')
    w.unmount()
  })

  it('复制规则(2026-09-13 验收新增):全字段照搬走创建端点,挂同组不带 id/sort_order,复制后 reload', async () => {
    const w = mountPane()
    await flushPromises()
    await w.find('[data-test="rules-of-1"] [data-test="rule-copy-11"]').trigger('click')
    await flushPromises()
    expect(api.createMockRule).toHaveBeenCalledTimes(1)
    const [iid, body] = api.createMockRule.mock.calls[0] as [number, Record<string, unknown>]
    expect(iid).toBe(5)                       // 挂同实例
    expect(body.group_id).toBe(1)             // 挂同组
    expect(body.conditions).toEqual([{ scope: 'query', key: 'id', match: 'eq', value: '42' }])
    expect(body.response_status).toBe(200)
    expect(body.enabled).toBe(true)
    expect('id' in body).toBe(false)          // 新建语义:id/sort_order 不随模板带过去
    expect('sort_order' in body).toBe(false)
    expect(api.listMockRuleGroups).toHaveBeenCalledTimes(2) // 复制后 reload 回贴组内末位
    w.unmount()
  })

  it('保存组/保存规则后的刷新失败:ElMessage.error 透出不静默(计划15 T11 顺手项)', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    const w = mountPane()
    await flushPromises()
    // 组保存回调 onGroupSaved → reload 失败须透出,不静默
    api.listMockRuleGroups.mockRejectedValueOnce(new Error('网络抖动'))
    await w.find('[data-test="new-group"]').trigger('click')
    w.findComponent(GroupDialog).vm.$emit('saved', G1)
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('刷新规则组失败:网络抖动')
    // 规则保存回调 onRuleSaved → reload 失败同样透出
    api.listMockRuleGroups.mockRejectedValueOnce(new Error('再抖'))
    await gToolBtn(w, 1, '新建规则').trigger('click')
    w.findComponent(RuleDialog).vm.$emit('saved', mkRule())
    await flushPromises()
    expect(errSpy).toHaveBeenLastCalledWith('刷新规则组失败:再抖')
    w.unmount()
  })
})

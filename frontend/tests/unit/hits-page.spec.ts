import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// HitsPage:instanceId/query.group 从路由取参,返回按钮走 useRouter.push
const routerState = vi.hoisted(() => ({
  push: vi.fn(),
  params: { id: '3', instanceId: '9' } as Record<string, string>,
  query: {} as Record<string, string>,
}))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: routerState.params, query: routerState.query }),
  useRouter: () => ({ push: routerState.push }),
}))

// HitsPage 拉实例+组列表;内嵌 HitsPanel 消费命中三件套(全量桩,风格同 rule-group-pane.spec)
const api = vi.hoisted(() => ({
  getMockInstance: vi.fn(),
  listMockRuleGroups: vi.fn(),
  listMockHits: vi.fn(),
  getMockHit: vi.fn(),
  clearMockHits: vi.fn(),
}))
vi.mock('../../src/api/mock', () => api)

import HitsPage from '../../src/components/mock/HitsPage.vue'
import type { MockHit, MockInstance, MockRuleGroup } from '../../src/types'

function mkInstance(over: Partial<MockInstance> = {}): MockInstance {
  return {
    id: 9, project_id: 3, name: '订单Mock', description: null, port: 18081,
    cors_enabled: true, default_status: 200, default_body: null,
    passthrough_enabled: false, upstream_base_url: null,
    desired: 'running', status: 'running', error_message: null,
    created_at: '2026-09-08T10:00:00', updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
function mkGroup(over: Partial<MockRuleGroup> = {}): MockRuleGroup {
  return {
    id: 7, instance_id: 9, method: 'GET', path_template: '/api/user/{id}',
    description: '查用户', enabled: true, passthrough_enabled: false, upstream_base_url: null, sort_order: 0, rules: [],
    updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}
function mkHit(over: Partial<MockHit> = {}): MockHit {
  return {
    id: 101, instance_id: 9, rule_id: 11, method: 'GET', path: '/users/42',
    query: 'a=1', matched: true, outcome: 'matched', response_status: 200,
    delay_ms: 0, elapsed_ms: 12, error: null, created_at: '2026-09-08T10:00:00',
    ...over,
  }
}

const INSTANCE = mkInstance({ id: 9, name: '订单Mock' })
const G1 = mkGroup({ id: 7 })
const G2 = mkGroup({ id: 8, method: 'POST', path_template: '/orders', sort_order: 1 })

// 与 mock-hits-panel.spec 同形态:装真 Element Plus,attach 到 body(组下拉 teleport 到 document)
const mountPage = () =>
  mount(HitsPage, { global: { plugins: [ElementPlus] }, attachTo: document.body })

const optionLabels = () =>
  [...document.querySelectorAll('.el-select-dropdown__item')].map((el) => el.textContent?.trim() ?? '')

describe('HitsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerState.params = { id: '3', instanceId: '9' }
    routerState.query = {}
    api.getMockInstance.mockResolvedValue(INSTANCE)
    api.listMockRuleGroups.mockResolvedValue([G1, G2])
    api.listMockHits.mockResolvedValue([])
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('挂载拉实例与组列表:标题/组下拉渲染全部组选项;无 query.group 默认全部(不带 group_id)', async () => {
    const w = mountPage()
    await flushPromises()
    expect(api.getMockInstance).toHaveBeenCalledWith(9)
    expect(api.listMockRuleGroups).toHaveBeenCalledWith(9)
    expect(w.text()).toContain('订单Mock · 命中记录')
    // 组下拉选项 = 组列表(按 method+path_template 展示),选项数=组数
    expect(optionLabels()).toEqual(['GET /api/user/{id}', 'POST /orders'])
    // 未选组:HitsPanel 首拉不带 group_id(第 4 参 undefined)
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, undefined)
    // 占位文案
    expect(w.find('[data-test="group-filter"]').text()).toContain('全部规则组')
    w.unmount()
  })

  it('query.group 预选:命中组列表则选中该组,HitsPanel 以 group_id 重拉', async () => {
    routerState.query = { group: '7' }
    const w = mountPage()
    await flushPromises()
    // EP 2.9 el-select 选中值渲染在 .el-select__placeholder span(非原生 input value)
    expect(w.find('[data-test="group-filter"]').text()).toContain('GET /api/user/{id}')
    expect(w.find('[data-test="group-filter"]').text()).not.toContain('全部规则组')
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, 7)
    w.unmount()
  })

  it('query.group 不在组列表中:回落「全部规则组」(不带 group_id)', async () => {
    routerState.query = { group: '99' }
    const w = mountPage()
    await flushPromises()
    expect(w.find('[data-test="group-filter"]').text()).toContain('全部规则组')
    expect(w.find('[data-test="group-filter"]').text()).not.toContain('GET /api/user/{id}')
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, undefined)
    w.unmount()
  })

  it('点选组 → HitsPanel 以所选组重拉;清空(emit null)→ 回全部', async () => {
    const w = mountPage()
    await flushPromises()
    api.listMockHits.mockClear()
    ;[...document.querySelectorAll('.el-select-dropdown__item')]
      .find((el) => el.textContent?.includes('POST /orders'))!
      .click()
    await flushPromises()
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, 8)
    // clearable 清空分支:EP clear 落到 v-model 的是 undefined/null=全部
    w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', null)
    await flushPromises()
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, undefined)
    w.unmount()
  })

  it('「← 返回规则组」回 project-mock-http-detail(params 带链上全部参数 id+instanceId)', async () => {
    const w = mountPage()
    await flushPromises()
    expect(routerState.push).not.toHaveBeenCalled()
    await w.findAll('button').find((b) => b.text().includes('← 返回'))!.trigger('click')
    // 完整形状断言(不用 objectContaining):缺父级 id 会在真实浏览器抛 Missing required param「id」
    expect(routerState.push).toHaveBeenCalledWith({
      name: 'project-mock-http-detail', params: { id: 3, instanceId: 9 },
    })
    w.unmount()
  })
})

import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ createMockRule: vi.fn(), updateMockRule: vi.fn() }))

vi.mock('../../src/api/mock', () => api)

// 真装 Element Plus(对齐 mock-pane.spec 形态):校验 textarea/number input 的真实回填与解析
import RuleDialog from '../../src/components/mock/RuleDialog.vue'
import type { MockRule, MockRuleGroup } from '../../src/types'

// 计划15 T10:规则挂组后 method/path 由组决定——RuleDialog 改挂组(props group),
// 不再有 method/path 输入;保存新建带 group_id、编辑走 Partial 不带
function mkGroup(over: Partial<MockRuleGroup> = {}): MockRuleGroup {
  return {
    id: 7, instance_id: 5, method: 'POST', path_template: '/orders/{id}',
    description: null, enabled: true, sort_order: 0, rules: [],
    updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}

function mkRule(over: Partial<MockRule> = {}): MockRule {
  return {
    id: 21, instance_id: 5, group_id: 7,
    conditions: [{ scope: 'header', key: 'X-Tenant', match: 'regex', value: '^t\\d+$' }],
    enabled: false, response_status: 201, response_headers: { A: 'b', 'C-Trace': 'd' },
    response_body: '{"ok":1}', enable_template: true, delay_ms: 300,
    timeout_enabled: true, timeout_seconds: 10, sort_order: 0, updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}

const GROUP = mkGroup()
const mountDialog = (rule: MockRule | null, group: MockRuleGroup = GROUP) =>
  mount(RuleDialog, { props: { group, rule }, global: { plugins: [ElementPlus] }, attachTo: document.body })

const dlg = () => document.querySelector('.el-dialog')!
const saveBtn = () => [...dlg().querySelectorAll('button')].find((b) => b.textContent?.trim() === '保存')!
const headersTextarea = () => dlg().querySelector<HTMLTextAreaElement>('textarea[placeholder="每行一条:Key: Value"]')!
const condRows = () => [...dlg().querySelectorAll('[data-test="cond-row"]')]
const numInput = (cls: string) => dlg().querySelector<HTMLInputElement>(`.${cls} input`)!

async function fill(selector: () => Element | null, value: string) {
  await new DOMWrapper(selector()!).setValue(value)
}

describe('RuleDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.createMockRule.mockResolvedValue(mkRule({ id: 99 }))
    api.updateMockRule.mockResolvedValue(mkRule())
    document.body.innerHTML = ''
  })

  it('新建模式:只读组路由展示;默认值渲染(启用/状态码200/延迟0/超时关30s/无条件);提交体含 group_id 且不含 method/path_template', async () => {
    const w = mountDialog(null)
    await flushPromises()
    // 只读组路由:方法与路径由所属规则组决定
    expect(w.text()).toContain('POST /orders/{id}')
    expect(w.text()).toContain('方法与路径由所属规则组决定')
    expect(numInput('status-input').value).toBe('200')
    expect(numInput('delay-input').value).toBe('0')
    expect(dlg().querySelector('.timeout-input')).toBeNull()
    expect(condRows().length).toBe(0)
    expect(w.text()).toContain("支持 {{ path.id }}、{{ jpath('$.x') }}、{{ uuid4() }}")
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockRule).toHaveBeenCalledTimes(1)
    const [instanceId, body] = api.createMockRule.mock.calls[0]
    expect(instanceId).toBe(5) // instance_id 取自所属组(group.instance_id)
    expect(body).toEqual(expect.objectContaining({
      group_id: 7, enabled: true, conditions: [], response_status: 200,
      response_headers: {}, response_body: null,
      enable_template: false, delay_ms: 0, timeout_enabled: false, timeout_seconds: 30,
    }))
    expect(body).not.toHaveProperty('method')
    expect(body).not.toHaveProperty('path_template')
    expect(w.emitted('saved')).toBeTruthy()
    w.unmount()
  })

  it('编辑模式:全字段回填,只读组路由展示;保存走 updateMockRule 且 body 不带 method/path_template/group_id', async () => {
    const w = mountDialog(mkRule())
    await flushPromises()
    expect(dlg().textContent).toContain('编辑规则')
    expect(w.text()).toContain('POST /orders/{id}')
    expect(headersTextarea().value).toBe('A: b\nC-Trace: d') // headers Record 反向拼回 textarea
    expect(numInput('status-input').value).toBe('201')
    expect(numInput('delay-input').value).toBe('300')
    expect(numInput('timeout-input').value).toBe('10')
    expect(condRows().length).toBe(1)
    expect(condRows()[0].querySelector<HTMLInputElement>('input[placeholder="参数名"]')!.value).toBe('X-Tenant')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.updateMockRule).toHaveBeenCalledWith(21, expect.objectContaining({
      enabled: false,
      conditions: [{ scope: 'header', key: 'X-Tenant', match: 'regex', value: '^t\\d+$' }],
    }))
    const body = api.updateMockRule.mock.calls[0][1]
    expect(body).not.toHaveProperty('method')
    expect(body).not.toHaveProperty('path_template')
    expect(body).not.toHaveProperty('group_id') // 编辑走 Partial,不带 group_id
    expect(api.createMockRule).not.toHaveBeenCalled()
    w.unmount()
  })

  it('headers 解析:两行 "A: b" / "C-Trace: v:1"(值含冒号按首个冒号切),空行与无冒号行跳过', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await fill(headersTextarea, 'A: b\nC-Trace: v:1\n  \nno-colon-line')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockRule).toHaveBeenCalledWith(5, expect.objectContaining({
      group_id: 7,
      response_headers: { A: 'b', 'C-Trace': 'v:1' },
    }))
    w.unmount()
  })

  it('conditions 动态行:+添加两行/填值/-删除首行,保存载荷只余末行', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await new DOMWrapper(dlg().querySelector('[data-test="cond-add"]')!).trigger('click')
    await new DOMWrapper(dlg().querySelector('[data-test="cond-add"]')!).trigger('click')
    expect(condRows().length).toBe(2)
    const keys = () => [...dlg().querySelectorAll<HTMLInputElement>('input[placeholder="参数名"]')]
    const vals = () => [...dlg().querySelectorAll<HTMLInputElement>('input[placeholder="匹配值"]')]
    await new DOMWrapper(keys()[0]).setValue('id')
    await new DOMWrapper(vals()[0]).setValue('42')
    await new DOMWrapper(keys()[1]).setValue('kw')
    await new DOMWrapper(vals()[1]).setValue('登录')
    await new DOMWrapper(condRows()[0].querySelector('[data-test="cond-remove"]')!).trigger('click')
    expect(condRows().length).toBe(1)
    expect(keys()[0].value).toBe('kw')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    // scope/match 未动过,保持默认 query/eq
    expect(api.createMockRule).toHaveBeenCalledWith(5, expect.objectContaining({
      conditions: [{ scope: 'query', key: 'kw', match: 'eq', value: '登录' }],
    }))
    w.unmount()
  })

  it('body 作用域可发现性:key 占位符提示 JSONPath 填法、作用域下拉显中文标签、条件区说明可见', async () => {
    const w = mountDialog(mkRule({ conditions: [{ scope: 'body', key: '$.id', match: 'eq', value: '1' }] }))
    await flushPromises()
    expect(condRows()[0].querySelector<HTMLInputElement>('input[placeholder^="JSONPath"]')!.value).toBe('$.id')
    expect(condRows()[0].textContent).toContain('请求体')
    expect(w.text()).toContain('JSONPath')
    w.unmount()
  })

  it('后端 400 透出:ElMessage.error 显示后端文案,对话框保持打开、不 emit saved', async () => {
    api.createMockRule.mockRejectedValue(new Error('条件正则不合法'))
    const w = mountDialog(null)
    await flushPromises()
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(document.querySelector('.el-message')?.textContent).toContain('条件正则不合法')
    expect(w.emitted('saved')).toBeFalsy()
    expect(dlg()).toBeTruthy() // 对话框未关闭
    w.unmount()
  })
})

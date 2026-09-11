import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createMockRule: vi.fn(),
  updateMockRule: vi.fn(),
}))

vi.mock('../../src/api/mock', () => api)

// 真装 Element Plus(对齐 mock-pane.spec 形态):校验 textarea/number input 的真实回填与解析
import RuleDialog from '../../src/components/mock/RuleDialog.vue'
import type { MockRule } from '../../src/types'

function mkRule(over: Partial<MockRule> = {}): MockRule {
  return {
    id: 21, instance_id: 5, method: 'POST', path_template: '/orders/{id}',
    conditions: [{ scope: 'header', key: 'X-Tenant', match: 'regex', value: '^t\\d+$' }],
    enabled: false, response_status: 201, response_headers: { A: 'b', C: 'd' },
    response_body: '{"ok":1}', enable_template: true, delay_ms: 300,
    timeout_enabled: true, timeout_seconds: 10, sort_order: 0, updated_at: '2026-09-08T10:00:00',
    ...over,
  }
}

const mountDialog = (rule: MockRule | null) =>
  mount(RuleDialog, { props: { instanceId: 5, rule }, global: { plugins: [ElementPlus] }, attachTo: document.body })

const dlg = () => document.querySelector('.el-dialog')!
const saveBtn = () => [...dlg().querySelectorAll('button')].find((b) => b.textContent?.trim() === '保存')!
const headersTextarea = () => dlg().querySelector<HTMLTextAreaElement>('textarea[placeholder="每行一条:Key: Value"]')!
const pathInput = () => dlg().querySelector<HTMLInputElement>('input[placeholder="/users/{id}"]')!
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

  it('新建模式:默认值渲染(GET/启用/状态码200/延迟0/超时关30s/无条件),模板提示文案可见', async () => {
    const w = mountDialog(null)
    await flushPromises()
    expect(pathInput().value).toBe('')
    expect(numInput('status-input').value).toBe('200')
    expect(numInput('delay-input').value).toBe('0')
    // 超时默认关:秒数输入隐藏;开关未选中
    expect(dlg().querySelector('.timeout-input')).toBeNull()
    expect(condRows().length).toBe(0)
    // 模板语法提示(含 {{ }} 字面量,经 v-pre 原样展示)
    expect(w.text()).toContain("支持 {{ path.id }}、{{ jpath('$.x') }}、{{ uuid4() }}")
    // path 必填只拦空值:填上后直接保存 → 其余字段全为默认值
    await fill(pathInput, '/users/{id}')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockRule).toHaveBeenCalledTimes(1)
    expect(api.createMockRule).toHaveBeenCalledWith(5, expect.objectContaining({
      method: 'GET', path_template: '/users/{id}', enabled: true, conditions: [],
      response_status: 200, response_headers: {}, response_body: null,
      enable_template: false, delay_ms: 0, timeout_enabled: false, timeout_seconds: 30,
    }))
    expect(w.emitted('saved')).toBeTruthy()
    w.unmount()
  })

  it('编辑模式:全字段回填(headers Record 反向拼回 textarea,两行 Key: Value)', async () => {
    const w = mountDialog(mkRule())
    await flushPromises()
    expect(dlg().textContent).toContain('编辑规则')
    expect(pathInput().value).toBe('/orders/{id}')
    expect(headersTextarea().value).toBe('A: b\nC: d')
    expect(numInput('status-input').value).toBe('201')
    expect(numInput('delay-input').value).toBe('300')
    expect(numInput('timeout-input').value).toBe('10')
    expect(condRows().length).toBe(1)
    expect(condRows()[0].querySelector<HTMLInputElement>('input[placeholder="参数名"]')!.value).toBe('X-Tenant')
    // 保存走 updateMockRule,conditions 原样带回
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.updateMockRule).toHaveBeenCalledWith(21, expect.objectContaining({
      method: 'POST', path_template: '/orders/{id}', enabled: false,
      conditions: [{ scope: 'header', key: 'X-Tenant', match: 'regex', value: '^t\\d+$' }],
      response_headers: { A: 'b', C: 'd' },
    }))
    expect(api.createMockRule).not.toHaveBeenCalled()
    w.unmount()
  })

  it('headers textarea 解析:两行 "A: b" / "C-Trace: v:1"(值含冒号按首个冒号切),空行与无冒号行跳过', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await fill(pathInput, '/trace')
    await fill(headersTextarea, 'A: b\nC-Trace: v:1\n  \nno-colon-line')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockRule).toHaveBeenCalledWith(5, expect.objectContaining({
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
    // 删除第一行(带 data-test 的删除钮在行内)
    await new DOMWrapper(condRows()[0].querySelector('[data-test="cond-remove"]')!).trigger('click')
    expect(condRows().length).toBe(1)
    expect(keys()[0].value).toBe('kw')
    await fill(pathInput, '/login')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    // scope/match 未动过,保持默认 query/eq
    expect(api.createMockRule).toHaveBeenCalledWith(5, expect.objectContaining({
      conditions: [{ scope: 'query', key: 'kw', match: 'eq', value: '登录' }],
    }))
    w.unmount()
  })

  it('body 作用域可发现性:key 占位符提示 JSONPath 填法、作用域显示中文标签、条件区带说明(后端 body key 本就是 JSONPath)', async () => {
    const w = mountDialog(mkRule({ conditions: [{ scope: 'body', key: '$.id', match: 'eq', value: '1' }] }))
    await flushPromises()
    // body 行 key 占位符 = JSONPath 示例;非 body 作用域仍为「参数名」(header 行既有断言覆盖)
    expect(condRows()[0].querySelector<HTMLInputElement>('input[placeholder^="JSONPath"]')!.value).toBe('$.id')
    // 作用域下拉选中项显示中文(请求体),不再裸英文 body
    expect(condRows()[0].textContent).toContain('请求体')
    // 条件区说明文案教用户:body 的 key 填 JSONPath,eq/regex 作用于定位到的值
    expect(w.text()).toContain('JSONPath')
    w.unmount()
  })

  it('轻校验:path_template 为空时拦截保存,不调 API', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(api.createMockRule).not.toHaveBeenCalled()
    expect(document.querySelector('.el-message')?.textContent).toContain('路径')
    w.unmount()
  })

  it('后端 400 文案直接 ElMessage.error 透出,对话框保持打开不 emit saved', async () => {
    api.createMockRule.mockRejectedValue(new Error('路径模板段 {xx} 不合法'))
    const w = mountDialog(null)
    await flushPromises()
    await fill(pathInput, '/users/{xx}')
    await new DOMWrapper(saveBtn()).trigger('click')
    await flushPromises()
    expect(document.querySelector('.el-message')?.textContent).toContain('路径模板段 {xx} 不合法')
    expect(w.emitted('saved')).toBeFalsy()
    expect(dlg()).toBeTruthy() // 对话框未关闭
    w.unmount()
  })
})

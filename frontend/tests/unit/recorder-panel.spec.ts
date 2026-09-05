import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// mock api:捕获 SSE 回调以便注入事件;orig 展开保持模块其他导出真实可用(import 不炸)
const mocks = vi.hoisted(() => {
  let cb: (e: Record<string, unknown>) => void = () => {}
  return {
    start: vi.fn(async () => ({ recording_id: 7 })),
    stop: vi.fn(async () => ({ meta: { start_url: 'http://x' }, variables: [], steps: [] })),
    create: vi.fn(async () => ({ id: 1 })),
    insertAssert: vi.fn(async () => ({ steps: [] })),
    cancel: vi.fn(async () => undefined),
    close: vi.fn(),
    subscribe: vi.fn((_id: number, c: (e: Record<string, unknown>) => void) => { cb = c; return mocks.close }),
    fire: (e: Record<string, unknown>) => cb(e),
  }
})
vi.mock('../../src/api/uiAutomation', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  startRecording: mocks.start,
  stopRecording: mocks.stop,
  createUiScript: mocks.create,
  insertAssert: mocks.insertAssert,
  cancelRecording: mocks.cancel,
  subscribeRecordingEvents: mocks.subscribe,
}))

import RecorderPanel from '../../src/components/webauto/RecorderPanel.vue'

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(RecorderPanel, {
    props: { projectId: 1, ...props },
    global: { plugins: [ElementPlus] },
  })
}

describe('RecorderPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('挂载即启动录制并订阅 SSE,action 事件实时追加步骤文案', async () => {
    const w = mountPanel()
    await flushPromises()
    expect(mocks.start).toHaveBeenCalledWith(1, undefined)
    expect(mocks.subscribe).toHaveBeenCalledWith(7, expect.any(Function))

    mocks.fire({ type: 'action', step: { id: 's1', action: 'click', locator: { strategy: 'css', value: '#go' } } })
    mocks.fire({ type: 'action', step: { id: 's2', action: 'scroll', params: { dx: 0, dy: 600 } } })
    await flushPromises()
    expect(w.text()).toContain('点击 #go')
    expect(w.text()).toContain('滚动 横向0 纵向600') // scroll 步骤摘要(滚轮/拖滚动条录制)
    expect(w.findAll('.rec-step').length).toBe(2)
  })

  it('带登录态启动:authStateId prop 透传给 startRecording,录制浏览器以该身份打开', async () => {
    mountPanel({ authStateId: 3 })
    await flushPromises()
    expect(mocks.start).toHaveBeenCalledWith(1, 3)
  })

  it('连续同 id 的 action 原位刷新,不重复追加(逐字输入合并)', async () => {
    const w = mountPanel()
    await flushPromises()
    mocks.fire({
      type: 'action',
      step: { id: 'f1', action: 'fill', locator: { strategy: 'css', value: '#u' }, params: { text: 'a' } },
    })
    mocks.fire({
      type: 'action',
      step: { id: 'f1', action: 'fill', locator: { strategy: 'css', value: '#u' }, params: { text: 'abc' } },
    })
    await flushPromises()
    expect(w.findAll('.rec-step').length).toBe(1)
    expect(w.find('.rec-step').text()).toContain('输入 #u=abc')
  })

  it('assert_candidate 弹出断言选择,确认调 insertAssert', async () => {
    const w = mountPanel()
    await flushPromises()
    const target = { tag: 'div', id: 'out', text: '查询结果' }
    mocks.fire({ type: 'assert_candidate', target })
    await flushPromises()
    expect(w.text()).toContain('文本包含')
    expect(w.text()).toContain('元素存在')

    // 选「文本包含」并补输入文本 → 确定
    const radioGroup = w.findComponent({ name: 'ElRadioGroup' })
    await radioGroup.vm.$emit('update:modelValue', 'contains')
    await flushPromises()
    const input = w.findAllComponents({ name: 'ElInput' })[0]
    await input.vm.$emit('update:modelValue', '查询结果')
    await w.findAll('button').find((b) => b.text().trim() === '确定')!.trigger('click')
    await flushPromises()
    expect(mocks.insertAssert).toHaveBeenCalledWith(7, {
      target, assert_type: 'assert_text', text: '查询结果', mode: 'contains',
    })
    // 断言步骤由后端以 action 事件推回,前端不本地拼
    mocks.fire({ type: 'action', step: { id: 'a1', action: 'assert_text', params: { text: '查询结果', mode: 'contains' } } })
    await flushPromises()
    expect(w.text()).toContain('断言 文本包含 查询结果')
  })

  it('停止并保存:调 stopRecording → 弹名字输入 → createUiScript 后 emit saved', async () => {
    const promptSpy = vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '冒烟脚本' } as never)
    const w = mountPanel()
    await flushPromises()
    mocks.fire({ type: 'action', step: { id: 'g1', action: 'goto', params: { url: 'http://x' } } })
    mocks.fire({ type: 'action', step: { id: 's1', action: 'click', locator: { strategy: 'css', value: '#go' } } })
    mocks.stop.mockResolvedValue({
      meta: { start_url: 'http://x' },
      variables: [{ name: 'kw', default: 'x' }],
      steps: [
        { id: 'g1', action: 'goto', params: { url: 'http://x' } },
        { id: 's1', action: 'click', locator: { strategy: 'css', value: '#go' } },
      ],
    })

    await w.findAll('button').find((b) => b.text().includes('停止并保存'))!.trigger('click')
    await flushPromises()
    expect(mocks.stop).toHaveBeenCalledWith(7)
    expect(mocks.close).toHaveBeenCalled() // 终态即断流,避免 EventSource 重连 404 误报「连接中断」
    // 草稿就绪后按钮切为「保存已录步骤」,再点击才弹名字输入
    await w.findAll('button').find((b) => b.text().includes('保存已录步骤'))!.trigger('click')
    await flushPromises()
    expect(promptSpy).toHaveBeenCalled()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      name: '冒烟脚本',
      script: {
        version: 1,
        meta: { start_url: 'http://x' },
        variables: [{ name: 'kw', default: 'x' }],
        steps: [
          { id: 'g1', action: 'goto', params: { url: 'http://x' } },
          { id: 's1', action: 'click', locator: { strategy: 'css', value: '#go' } },
        ],
      },
    })
    expect(w.emitted('saved')).toBeTruthy()
  })

  it('带登录态录制保存:meta 写入 auth_state_id,执行默认带上(功能1)', async () => {
    vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '带态脚本' } as never)
    const w = mountPanel({ authStateId: 3 })
    await flushPromises()
    mocks.fire({ type: 'action', step: { id: 'g1', action: 'goto', params: { url: 'http://x' } } })
    mocks.fire({ type: 'stopped' })
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('保存已录步骤'))!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      name: '带态脚本',
      script: {
        version: 1,
        meta: { start_url: 'http://x', auth_state_id: 3 },
        variables: [],
        steps: [{ id: 'g1', action: 'goto', params: { url: 'http://x' } }],
      },
    })
  })

  it('stopped 事件(用户直接关浏览器窗)→ 出现「保存已录步骤」,保存走本地草稿不再调 stop', async () => {
    vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '关窗脚本' } as never)
    const w = mountPanel()
    await flushPromises()
    mocks.fire({ type: 'action', step: { id: 'g1', action: 'goto', params: { url: 'http://x' } } })
    mocks.fire({ type: 'stopped' })
    await flushPromises()
    expect(w.text()).toContain('保存已录步骤')
    expect(mocks.close).toHaveBeenCalled() // 用户关浏览器窗同理,终态即断流

    await w.findAll('button').find((b) => b.text().includes('保存已录步骤'))!.trigger('click')
    await flushPromises()
    expect(mocks.stop).not.toHaveBeenCalled()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      name: '关窗脚本',
      script: {
        version: 1,
        meta: { start_url: 'http://x' },
        variables: [],
        steps: [{ id: 'g1', action: 'goto', params: { url: 'http://x' } }],
      },
    })
  })

  it('放弃 → 调 cancelRecording 并 emit closed', async () => {
    const w = mountPanel()
    await flushPromises()
    await w.findAll('button').find((b) => b.text().trim() === '放弃')!.trigger('click')
    await flushPromises()
    expect(mocks.cancel).toHaveBeenCalledWith(7)
    expect(w.emitted('closed')).toBeTruthy()
  })

  it('主动停止在途:stopped 先到也断流,error 不误报「连接中断」,草稿仍以 stop API 为准', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    let resolveStop!: (v: unknown) => void
    mocks.stop.mockImplementation(() => new Promise((res) => { resolveStop = res }))
    const w = mountPanel()
    await flushPromises()
    mocks.fire({ type: 'action', step: { id: 'g1', action: 'goto', params: { url: 'http://x' } } })
    await w.findAll('button').find((b) => b.text().includes('停止并保存'))!.trigger('click')

    // stop API 尚未返回,后端 _on_close 先经 SSE 推终态 → 立即断流;error 不误报
    mocks.fire({ type: 'stopped' })
    mocks.fire({ type: 'error', message: '连接中断' })
    await flushPromises()
    expect(mocks.close).toHaveBeenCalled()
    expect(errSpy).not.toHaveBeenCalledWith('连接中断')
    expect(w.text()).not.toContain('保存已录步骤') // 在途不本地兜底,等待权威草稿

    resolveStop({ meta: { start_url: 'http://x' }, variables: [], steps: [{ id: 'g1', action: 'goto', params: { url: 'http://x' } }] })
    await flushPromises()
    expect(w.text()).toContain('保存已录步骤')
  })

  it('断言确认防重复提交:await 期间再点确定只插一条', async () => {
    let resolveInsert!: (v: unknown) => void
    mocks.insertAssert.mockImplementation(() => new Promise((res) => { resolveInsert = res }))
    const w = mountPanel()
    await flushPromises()
    mocks.fire({ type: 'assert_candidate', target: { tag: 'div', id: 'out' } })
    await flushPromises()
    const confirmBtn = () => w.findAll('button').find((b) => b.text().trim() === '确定')!
    await confirmBtn().trigger('click') // 第一次:进入 await
    await confirmBtn().trigger('click') // 第二次:守卫早退
    resolveInsert({ steps: [] })
    await flushPromises()
    expect(mocks.insertAssert).toHaveBeenCalledTimes(1)
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { fakeInstance, MindMapCtor, FakeResizeObserver } = vi.hoisted(() => {
  const fakeInstance = { on: vi.fn(), setData: vi.fn(), destroy: vi.fn(), render: vi.fn(), resize: vi.fn() }
  const MindMapCtor = vi.fn(() => fakeInstance)
  // jsdom 无 ResizeObserver 也无布局:stub 出可控的假实现,由测试手动触发回调
  class FakeResizeObserver {
    static instances: FakeResizeObserver[] = []
    cb: ResizeObserverCallback
    constructor(cb: ResizeObserverCallback) { this.cb = cb; FakeResizeObserver.instances.push(this) }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  return { fakeInstance, MindMapCtor, FakeResizeObserver }
})
vi.mock('simple-mind-map', () => ({ default: MindMapCtor }))

import MindmapEditor from '../../src/components/MindmapEditor.vue'
import type { MindmapNode } from '../../src/adapters/tree'

const sample: MindmapNode = { data: { text: '项目', uid: 'root', nodeType: 'root' }, children: [] }
const sample2: MindmapNode = { data: { text: '改名', uid: 'root', nodeType: 'root' }, children: [] }

describe('MindmapEditor 封装', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom 无布局,offsetWidth/Height 恒 0:默认给可见尺寸,保持"挂载即初始化"的既有契约
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 800 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 600 })
    FakeResizeObserver.instances.length = 0
  })

  afterEach(() => {
    // 恢复 jsdom 原生(0)取值,避免污染其它 spec
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 0 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 0 })
    vi.unstubAllGlobals()
  })

  it('挂载时用 props.data 实例化 MindMap', () => {
    mount(MindmapEditor, { props: { data: sample } })
    expect(MindMapCtor).toHaveBeenCalledTimes(1)
    expect(MindMapCtor.mock.calls[0][0].data).toEqual(sample)
    expect(MindMapCtor.mock.calls[0][0].disableDBClickTapNode).toBe(true)
  })

  it('容器 0 尺寸(隐藏 tab 下挂载)时不初始化,显示出来后再初始化', async () => {
    // 复现:暂存区入库 → 切「用例导图」tab,pane display:none 容器 0×0
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 0 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 0 })
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    mount(MindmapEditor, { props: { data: sample } })
    await flushPromises()
    // 不构造(旧实现在此抛"容器元素el的宽高不能为0"并炸掉 Vue 调度器)
    expect(MindMapCtor).not.toHaveBeenCalled()

    // tab 激活 → 容器有尺寸 → ResizeObserver 回调 → 初始化
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 800 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 600 })
    const ro = FakeResizeObserver.instances.at(-1)!
    ro.cb([], ro as unknown as ResizeObserver)
    await flushPromises()
    expect(MindMapCtor).toHaveBeenCalledTimes(1)
    expect(MindMapCtor.mock.calls[0][0].data).toEqual(sample)
    // 只初始化一次(重复 resize 不重复构造)
    ro.cb([], ro as unknown as ResizeObserver)
    await flushPromises()
    expect(MindMapCtor).toHaveBeenCalledTimes(1)
  })

  it('隐藏挂载、显示后初始化的实例,卸载时同样销毁', async () => {
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 0 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 0 })
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)
    const wrapper = mount(MindmapEditor, { props: { data: sample } })
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 800 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 600 })
    const ro = FakeResizeObserver.instances.at(-1)!
    ro.cb([], ro as unknown as ResizeObserver)
    await flushPromises()
    wrapper.unmount()
    expect(fakeInstance.destroy).toHaveBeenCalled()
  })

  it('data prop 变化时调用 setData', async () => {
    const wrapper = mount(MindmapEditor, { props: { data: sample } })
    await wrapper.setProps({ data: sample2 })
    expect(fakeInstance.setData).toHaveBeenCalledWith(sample2)
  })

  it('node_click 转发为 nodeActive 事件(重复点击已激活节点也要转发)', async () => {
    const wrapper = mount(MindmapEditor, { props: { data: sample } })
    const handler = fakeInstance.on.mock.calls.find((c) => c[0] === 'node_click')![1] as (node: unknown) => void
    const node = { getData: (k: string) => (k === 'nodeType' ? 'case' : 42) }
    handler(node)
    handler(node) // 同一节点再次点击仍应转发
    await flushPromises()
    expect(wrapper.emitted('nodeActive')).toHaveLength(2)
    expect(wrapper.emitted('nodeActive')![0]).toEqual([{ nodeType: 'case', refId: 42 }])
  })

  it('根节点点击只带 nodeType', async () => {
    const wrapper = mount(MindmapEditor, { props: { data: sample } })
    const handler = fakeInstance.on.mock.calls.find((c) => c[0] === 'node_click')![1] as (node: unknown) => void
    handler({ getData: (k: string) => (k === 'nodeType' ? 'root' : undefined) })
    await flushPromises()
    expect(wrapper.emitted('nodeActive')![0]).toEqual([{ nodeType: 'root' }])
  })

  it('无 nodeType 数据的节点不触发', async () => {
    const wrapper = mount(MindmapEditor, { props: { data: sample } })
    const handler = fakeInstance.on.mock.calls.find((c) => c[0] === 'node_click')![1] as (node: unknown) => void
    handler({ getData: () => undefined })
    await flushPromises()
    expect(wrapper.emitted('nodeActive')).toBeUndefined()
  })

  it('卸载时销毁实例', () => {
    const wrapper = mount(MindmapEditor, { props: { data: sample } })
    wrapper.unmount()
    expect(fakeInstance.destroy).toHaveBeenCalled()
  })
})

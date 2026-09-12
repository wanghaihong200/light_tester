import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// HitsPanel 只消费命中三件套;api/mock 其余导出本 spec 不用(mock-pane.spec 已覆盖)
const api = vi.hoisted(() => ({
  listMockHits: vi.fn(),
  getMockHit: vi.fn(),
  clearMockHits: vi.fn(),
}))
vi.mock('../../src/api/mock', () => api)

import HitsPanel from '../../src/components/mock/HitsPanel.vue'
import type { MockHit, MockHitDetail } from '../../src/types'

function mkHit(over: Partial<MockHit> = {}): MockHit {
  return {
    id: 101, instance_id: 1, rule_id: 11, method: 'GET', path: '/users/42',
    query: 'a=1', matched: true, outcome: 'matched', response_status: 200,
    delay_ms: 0, elapsed_ms: 12, error: null, created_at: '2026-09-08T10:00:00',
    ...over,
  }
}
const H_MATCHED = mkHit({ id: 101 })
const H_MISSED = mkHit({
  id: 102, rule_id: null, method: 'POST', path: '/nope', query: null,
  matched: false, outcome: 'fallback', response_status: 404, elapsed_ms: 3,
  created_at: '2026-09-08T10:00:05',
})
// 详情 = 列表行 + 请求头/请求体;带 error 覆盖抽屉内错误展示(response_body 由用例按需覆写)
const DETAIL: MockHitDetail = {
  ...H_MATCHED, request_headers: { 'Content-Type': 'application/json', 'X-Trace': 't-1' },
  request_body: '{"user":"hai"}', response_body: null, error: '客户端提前断开',
}

// 挂 body:抽屉/表格测量与 document 级查询都需要真实挂载
const mountPanel = (props: Record<string, unknown> = {}) =>
  mount(HitsPanel, {
    props: { instanceId: 1, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })

const rows = (w: ReturnType<typeof mountPanel>) => w.findAll('.el-table__row')
const btn = (w: ReturnType<typeof mountPanel>, text: string) =>
  w.findAll('button').find((b) => b.text().includes(text))!
const drawer = () => document.querySelector('.el-drawer')

describe('HitsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listMockHits.mockResolvedValue([H_MATCHED, H_MISSED])
    api.getMockHit.mockResolvedValue(DETAIL)
    api.clearMockHits.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('挂载即拉取并渲染:四态过滤器/时间 YYYY-MM-DD HH:mm:ss/方法/路径+query/命中 tag 绿红/耗时 ms', async () => {
    const w = mountPanel()
    await flushPromises()
    // 计划15 T11:limit 显式传 200;无组筛选时第 4 参 undefined(api 不拼 group_id)
    expect(api.listMockHits).toHaveBeenCalledWith(1, 'all', 200, undefined)
    // 过滤器四态:全部/命中/未命中/透传(计划15 加「透传」)
    const labels = w.findAll('.el-radio__label').map((l) => l.text())
    expect(labels).toEqual(['全部', '命中', '未命中', '透传'])
    // 时间列手工格式化为 YYYY-MM-DD HH:mm:ss(不用 toLocaleString,格式跨环境稳定)
    const times = w.findAll('[data-test="hit-time"]').map((t) => t.text())
    expect(times).toEqual(['2026-09-08 10:00:00', '2026-09-08 10:00:05'])
    // 方法 + 路径(有 query 拼 ?query,无 query 只 path)
    const paths = w.findAll('[data-test="hit-path"]').map((p) => p.text())
    expect(paths).toEqual(['/users/42?a=1', '/nope'])
    expect(rows(w)[0].text()).toContain('GET')
    expect(rows(w)[1].text()).toContain('POST')
    // 命中 tag:命中绿「命中→200」/ 未命中红「未命中→404」
    // (data-test 落在 el-tag 内部 transition 根上,颜色断言查 html,与 mock-pane.spec 同款)
    const tags = w.findAll('[data-test="hit-tag"]')
    expect(tags[0].text()).toBe('命中→200')
    expect(tags[1].text()).toBe('未命中→404')
    expect(w.html()).toContain('el-tag--success')
    expect(w.html()).toContain('el-tag--danger')
    // 耗时 ms + 行尾「详情」link 按钮
    expect(w.text()).toContain('12ms')
    expect(w.text()).toContain('3ms')
    expect(w.find('[data-test="hit-detail"]').exists()).toBe(true)
    w.unmount()
  })

  it('透传行显蓝「透传→201」,兜底行显红「未命中→404」', async () => {
    api.listMockHits.mockResolvedValue([
      mkHit({ id: 201, matched: false, outcome: 'forwarded', response_status: 201 }),
      mkHit({ id: 202, matched: false, outcome: 'fallback', response_status: 404, rule_id: null }),
    ])
    const w = mountPanel()
    await flushPromises()
    const tags = w.findAll('[data-test="hit-tag"]')
    expect(tags[0].text()).toBe('透传→201')
    expect(tags[1].text()).toBe('未命中→404')
    expect(w.html()).toContain('el-tag--primary')
    expect(w.html()).toContain('el-tag--danger')
    w.unmount()
  })

  it('过滤切换:点「未命中」以 filter=unmatched 重拉,点「全部」回 all', async () => {
    const w = mountPanel()
    await flushPromises()
    api.listMockHits.mockClear()
    const radioByText = (text: string) =>
      w.findAll('.el-radio').find((r) => r.text() === text)!.find('input')
    await radioByText('未命中').setValue(true)
    await flushPromises()
    expect(api.listMockHits).toHaveBeenCalledTimes(1)
    expect(api.listMockHits).toHaveBeenCalledWith(1, 'unmatched', 200, undefined)
    await radioByText('全部').setValue(true)
    await flushPromises()
    expect(api.listMockHits).toHaveBeenLastCalledWith(1, 'all', 200, undefined)
    w.unmount()
  })

  it('groupId 变化触发带 group_id 的重拉;清空组回全部(第 4 参 undefined)', async () => {
    vi.useFakeTimers()
    const w = mountPanel({ instanceId: 9 })
    await vi.advanceTimersByTimeAsync(0)
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, undefined)
    await w.setProps({ groupId: 7 })
    await vi.advanceTimersByTimeAsync(0)
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, 7)
    // null/undefined 同义=全部:重拉不带 group_id,旧定时器不残留(3s 后恰好一次)
    await w.setProps({ groupId: null })
    await vi.advanceTimersByTimeAsync(0)
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, undefined)
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.listMockHits).toHaveBeenCalledTimes(4)
    expect(api.listMockHits).toHaveBeenLastCalledWith(9, 'all', 200, undefined)
    w.unmount()
  })

  it('行点击:getMockHit 拉全量并打开抽屉(请求头 kv/请求体 pre/状态/延迟/耗时/error)', async () => {
    const w = mountPanel()
    await flushPromises()
    expect(api.getMockHit).not.toHaveBeenCalled() // 未点击前不拉详情
    await rows(w)[0].trigger('click')
    await flushPromises()
    expect(api.getMockHit).toHaveBeenCalledWith(101)
    const d = drawer()!
    expect(d.textContent).toContain('命中 #101 详情')
    expect(d.textContent).toContain('GET')
    expect(d.textContent).toContain('/users/42?a=1')
    // 请求头 kv 表
    expect(d.textContent).toContain('Content-Type')
    expect(d.textContent).toContain('application/json')
    expect(d.textContent).toContain('X-Trace')
    expect(d.textContent).toContain('t-1')
    // 请求体 pre 块(原样展示)
    expect(d.querySelector('[data-test="hit-body"]')?.textContent).toBe('{"user":"hai"}')
    // 响应状态/延迟/耗时/error
    expect(d.textContent).toContain('200')
    expect(d.textContent).toContain('0ms')
    expect(d.textContent).toContain('12ms')
    expect(d.textContent).toContain('客户端提前断开')
    // 无 response_body:响应体段显「无」占位,不渲染 pre
    expect(d.querySelector('[data-test="hit-resp-body"]')).toBeNull()
    expect(d.textContent).toContain('响应体')
    w.unmount()
  })

  it('详情抽屉渲染响应体段:有 body 显 pre[data-test=hit-resp-body]', async () => {
    const w = mountPanel()
    await flushPromises()
    api.getMockHit.mockResolvedValueOnce({ ...DETAIL, response_body: '{"echo":"ok"}' })
    await rows(w)[0].trigger('click')
    await flushPromises()
    expect(drawer()!.querySelector('[data-test="hit-resp-body"]')?.textContent).toBe('{"echo":"ok"}')
    w.unmount()
  })

  it('行尾「详情」按钮:打开抽屉且 @click.stop 不冒泡成行点击(只拉一次)', async () => {
    const w = mountPanel()
    await flushPromises()
    await w.find('[data-test="hit-detail"]').trigger('click')
    await flushPromises()
    expect(api.getMockHit).toHaveBeenCalledTimes(1)
    expect(api.getMockHit).toHaveBeenCalledWith(101)
    w.unmount()
  })

  it('清空:confirm 确认后 clearMockHits 并重拉;取消分支不调用不清列表', async () => {
    vi.useFakeTimers()
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const w = mountPanel()
    await vi.advanceTimersByTimeAsync(0)
    expect(rows(w).length).toBe(2)
    await btn(w, '清空').trigger('click')
    await vi.advanceTimersByTimeAsync(0)
    expect(String(confirmSpy.mock.calls[0][0])).toContain('清空')
    expect(api.clearMockHits).toHaveBeenCalledWith(1)
    expect(api.listMockHits).toHaveBeenCalledTimes(2) // 清空成功后刷新

    // 取消:reject → 不调 clearMockHits、不重拉
    confirmSpy.mockRejectedValueOnce('cancel')
    await btn(w, '清空').trigger('click')
    await vi.advanceTimersByTimeAsync(0)
    expect(api.clearMockHits).toHaveBeenCalledTimes(1)
    expect(api.listMockHits).toHaveBeenCalledTimes(2)
    w.unmount()
  })

  it('3s 轮询:挂载后每 3s 重拉,卸载后定时器清理不再调用', async () => {
    vi.useFakeTimers()
    let w = mountPanel()
    await vi.advanceTimersByTimeAsync(0) // 让 onMounted 的异步首拉落地
    expect(api.listMockHits).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.listMockHits).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.listMockHits).toHaveBeenCalledTimes(3)
    w.unmount()
    await vi.advanceTimersByTimeAsync(15000)
    expect(api.listMockHits).toHaveBeenCalledTimes(3) // 卸载后停止

    w = mountPanel()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(9000)
    // 同一 spy 跨面板累计:前一面板 3 次 + 新面板首拉 1 次 + 3 次轮询
    expect(api.listMockHits).toHaveBeenCalledTimes(7)
    w.unmount()
  })

  it('watch(instanceId):换实例以新 id 重拉且旧定时器不残留(3s 后恰好一次)', async () => {
    vi.useFakeTimers()
    const w = mountPanel()
    await vi.advanceTimersByTimeAsync(0)
    expect(api.listMockHits).toHaveBeenCalledTimes(1)
    await w.setProps({ instanceId: 2 })
    await vi.advanceTimersByTimeAsync(0)
    expect(api.listMockHits).toHaveBeenCalledTimes(2)
    expect(api.listMockHits).toHaveBeenLastCalledWith(2, 'all', 200, undefined)
    // 若旧定时器未清,这里会双跳(旧 t=3s + 新 t=3s 各一次)
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.listMockHits).toHaveBeenCalledTimes(3)
    expect(api.listMockHits).toHaveBeenLastCalledWith(2, 'all', 200, undefined)
    w.unmount()
  })

  it('列表加载失败静默:不弹全局错、保留旧列表、轮询不中断', async () => {
    vi.useFakeTimers()
    const errSpy = vi.spyOn(ElMessage, 'error')
    const w = mountPanel()
    await vi.advanceTimersByTimeAsync(0)
    expect(rows(w).length).toBe(2)
    api.listMockHits.mockRejectedValue(new Error('boom'))
    await vi.advanceTimersByTimeAsync(3000)
    expect(errSpy).not.toHaveBeenCalled()
    expect(rows(w).length).toBe(2) // 失败保留旧列表不清空
    expect(api.listMockHits).toHaveBeenCalledTimes(2) // 轮询未因失败停摆
    w.unmount()
  })
})

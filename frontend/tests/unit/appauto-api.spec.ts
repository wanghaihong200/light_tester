import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { exportAppScript, subscribeAppRunEvents } from '../../src/api/appAutomation'
import type { AppRunEvent } from '../../src/api/appAutomation'

// ── 终审 I3:导出 api 封装(端点/方法/包体一行断言) ──
describe('appAutomation api', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({}), { status: 200 })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('exportAppScript POST /app-scripts/{id}/export', async () => {
    await exportAppScript(7, { branch: 'main', commit_message: '导出' })
    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(String(url)).toContain('/app-scripts/7/export')
    expect((init as RequestInit).method).toBe('POST')
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ branch: 'main', commit_message: '导出' })
  })
})

// ── 终审 T13①:subscribeAppRunEvents 断线兜底(onerror 关流 + 回读终态给 snapshot) ──
class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  constructor(public url: string) { FakeEventSource.instances.push(this) }
  close() { this.closed = true }
}

const RUN_BASE = {
  id: 11, project_id: 1, script_id: 7, script_name: '下单冒烟', device_serial: 'DEV-A',
  batch_id: null, variables: {}, pre_checks: [], post_checks: [], perf_items: [],
  results: null, check_results: null, perf_summary: null, startup_summary: null,
  started_at: null, finished_at: null,
}

describe('subscribeAppRunEvents onerror 兜底', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('断线时关流;run 已终态 → 回调 snapshot', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ ...RUN_BASE, status: 'passed', run_state: 'passed', error: null }),
      { status: 200 })))
    const events: AppRunEvent[] = []
    subscribeAppRunEvents(11, (e) => events.push(e))
    const inst = FakeEventSource.instances[0]
    expect(String(inst.url)).toContain('/api/app-runs/11/events')
    inst.onerror!()
    await vi.waitFor(() => expect(events).toHaveLength(1))
    expect(inst.closed).toBe(true) // 先关流,防 EventSource 自动重连
    expect(events[0]).toEqual({ type: 'snapshot', status: 'passed', run_state: 'passed', error: null })
  })

  it('断线时 run 未终态 → 回调 error(SSE 连接断开)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ ...RUN_BASE, status: 'running', run_state: null, error: null }),
      { status: 200 })))
    const events: AppRunEvent[] = []
    subscribeAppRunEvents(11, (e) => events.push(e))
    FakeEventSource.instances[0].onerror!()
    await vi.waitFor(() => expect(events).toHaveLength(1))
    expect(events[0]).toEqual({ type: 'error', message: 'SSE 连接断开' })
  })
})

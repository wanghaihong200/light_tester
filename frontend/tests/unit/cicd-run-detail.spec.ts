// frontend/tests/unit/cicd-run-detail.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getCiRun: vi.fn(),
  stopCiRun: vi.fn(),
  rerunCiRun: vi.fn(),
  ciRunEventsUrl: vi.fn((id: number) => `/ci-runs/${id}/events`),
}))
vi.mock('../../src/api/cicd', () => api)
vi.mock('../../src/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/api/client')>()),
  withSseToken: (u: string) => `${u}?token=x`,
}))
const routerState = vi.hoisted(() => ({ back: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { runId: '5' } }), useRouter: () => routerState }))

import RunDetailPage from '../../src/components/cicd/RunDetailPage.vue'

class FakeEventSource {
  static last: FakeEventSource | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  closed = false
  constructor(public url: string) { FakeEventSource.last = this }
  close(): void { this.closed = true }
}
vi.stubGlobal('EventSource', FakeEventSource)

const TERMINAL = {
  id: 5, project_id: 3, plan_id: 1, plan_name: '接口回归', kind: 'api' as const, branch: 'master',
  selection: [{ ref: 'com.x.A#dead', class_name: 'com.x.A', method: 'dead', skipped: true, skip_reason: 'stale' }],
  status: 'success' as const, jenkins_job: 'j1', build_number: 4,
  jenkins_url: 'http://jk/job/j/4/', total: 2, passed: 1, failed: 1, skipped: 0,
  results: [
    { class_name: 'com.x.A', name: 'ok1', status: 'passed', time_s: 0.1, message: null },
    { class_name: 'com.x.A', name: 'bad1', status: 'failed', time_s: 0.2, message: 'assert 1 == 2' },
  ],
  console_bytes: 20, error: null, freshness: null,
  created_at: '2026-09-16T10:00:00', finished_at: '2026-09-16T10:01:00',
}

describe('RunDetailPage', () => {
  it('终态:渲染汇总/用例行/快照 skipped 标注/外链,开 SSE 回放日志尾部', async () => {
    api.getCiRun.mockResolvedValue(TERMINAL)
    const w = mount(RunDetailPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('接口回归')
    expect(w.text()).toContain('assert 1 == 2')
    expect(w.text()).toContain('未执行');  // skipped 快照行
    expect(w.text()).toContain('com.x.A#dead')
    expect(FakeEventSource.last).not.toBeNull()  // 终态也开流:后端回放 console 尾部+快照即关(2026-09-17 冒烟缺陷)
    FakeEventSource.last!.onmessage?.({ data: JSON.stringify({ type: 'log', text: 'ERROR: auth failed for origin' }) })
    await flushPromises()
    expect(w.find('.console').text()).toContain('ERROR: auth failed for origin')
  })

  it('活跃:开 SSE,log 事件追加日志,done 重拉结果', async () => {
    api.getCiRun.mockClear()  // hoisted mock 跨用例累积调用,绝对计数须先清(同 T19 惯例)
    api.getCiRun.mockResolvedValueOnce({ ...TERMINAL, status: 'running', results: null, total: 0, passed: 0, failed: 0 })
    api.getCiRun.mockResolvedValueOnce(TERMINAL)
    const w = mount(RunDetailPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(FakeEventSource.last).not.toBeNull()
    FakeEventSource.last!.onmessage?.({ data: JSON.stringify({ type: 'log', text: 'hello build' }) })
    await flushPromises()
    expect(w.find('.console').text()).toContain('hello build')
    FakeEventSource.last!.onmessage?.({ data: JSON.stringify({ type: 'done', status: 'success' }) })
    await flushPromises()
    expect(api.getCiRun).toHaveBeenCalledTimes(2)
    expect((w.vm as unknown as { run: { status: string } }).run.status).toBe('success')
  })
})

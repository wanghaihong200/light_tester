// frontend/tests/unit/cicd-run-detail.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getCiRun: vi.fn(),
  getCiRunConsole: vi.fn(),
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
  it('终态:REST 拉全量日志渲染 console;开 SSE 只收 status+snapshot 后收流', async () => {
    api.getCiRun.mockResolvedValue(TERMINAL)
    api.getCiRunConsole.mockResolvedValue('Started by user hi\nERROR: auth failed for origin\nFULL')
    const w = mount(RunDetailPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('接口回归')
    expect(w.text()).toContain('assert 1 == 2')
    expect(w.text()).toContain('未执行')  // skipped 快照行(标注并入 message)
    expect(w.text()).toContain('A#dead')  // api 类 skipped 行的类组短名(完整 ref 在 title tooltip)
    expect(w.find('.console').text()).toContain('FULL')  // 全量日志来自 REST
    expect(FakeEventSource.last).not.toBeNull()  // 终态仍开流(status+snapshot 即关)
    FakeEventSource.last!.onmessage?.({ data: JSON.stringify({ type: 'snapshot', status: 'success' }) })
    await flushPromises()
    expect(FakeEventSource.last!.closed).toBe(true)  // 快照后必须收流,防自动重连循环
  })

  it('活跃:开 SSE,log 事件追加直播日志,done 后全量重拉 console 为替换不叠加', async () => {
    api.getCiRun.mockClear()
    api.getCiRunConsole.mockClear()
    api.getCiRun.mockResolvedValueOnce({ ...TERMINAL, status: 'running', results: null, total: 0, passed: 0, failed: 0 })
    api.getCiRun.mockResolvedValueOnce(TERMINAL)
    api.getCiRunConsole.mockResolvedValueOnce('live-so-far\n')
    api.getCiRunConsole.mockResolvedValueOnce('live-so-far\nFinished: SUCCESS\n')
    const w = mount(RunDetailPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(FakeEventSource.last).not.toBeNull()
    FakeEventSource.last!.onmessage?.({ data: JSON.stringify({ type: 'log', text: 'hello build\n' }) })
    await flushPromises()
    expect(w.find('.console').text()).toContain('hello build')
    FakeEventSource.last!.onmessage?.({ data: JSON.stringify({ type: 'done', status: 'success' }) })
    await flushPromises()
    expect(api.getCiRun).toHaveBeenCalledTimes(2)
    expect(api.getCiRunConsole).toHaveBeenCalledTimes(2)
    expect((w.vm as unknown as { run: { status: string } }).run.status).toBe('success')
    // done 后 REST 全量替换:直播拼接文本被完整日志覆盖,不产生重叠
    expect(w.find('.console').text()).toContain('Finished: SUCCESS')
    expect(w.find('.console').text()).not.toContain('hello build')
  })

  it('点击用例定位:console 内命中高亮,重复点击循环', async () => {
    api.getCiRun.mockClear()
    api.getCiRunConsole.mockClear()
    api.getCiRun.mockResolvedValue(TERMINAL)
    api.getCiRunConsole.mockResolvedValue('start\nbad1 line A\nmid\nbad1 line B\nend\n')
    const w = mount(RunDetailPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    const leaf = w.findAll('.row.leaf').find((r) => r.text().includes('bad1'))
    await leaf!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('命中 2 处')
    expect(w.find('.console').html()).toContain('<mark')
    // 再点一次 → 循环到下一条
    await leaf!.trigger('click')
    await flushPromises()
    const cur = w.find('mark.cur')
    expect(cur.exists()).toBe(true)
    expect(cur.text()).toBe('bad1')
  })

  it('数据驱动用例定位回退:完整名未命中时回退到去后缀方法名', async () => {
    api.getCiRun.mockClear()
    api.getCiRunConsole.mockClear()
    // 日志只有 SELECTION 里的 base 方法名,无 [参数](序号) 完整名——数据驱动通过用例的典型形态
    api.getCiRun.mockResolvedValue({
      ...TERMINAL,
      selection: [{ ref: 'com.x.B#dd', class_name: 'com.x.B', method: 'dd', skipped: false }],
      results: [
        { class_name: 'com.x.B', name: 'dd[admin](1)', status: 'passed', time_s: 0.3, message: null },
      ],
    })
    api.getCiRunConsole.mockResolvedValue('mvn -Dtest=com.x.B#dd\nRunning com.x.B\n')
    const w = mount(RunDetailPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    // 全通过类默认收起:先展开类组,再展开方法组,叶子才可见
    await w.findAll('.case-tree .row').find((r) => r.find('.name').text() === 'B')!.trigger('click')
    await flushPromises()
    await w.findAll('.case-tree .row').find((r) => r.find('.name').text() === 'dd')!.trigger('click')
    await flushPromises()
    const leaf = w.findAll('.row.leaf').find((r) => r.text().includes('dd[admin](1)'))
    await leaf!.trigger('click')
    await flushPromises()
    // 回退命中 base 名,定位条展示实际命中的文本
    expect(w.text()).toContain('定位「dd」命中 1 处')
    expect(w.find('mark.cur').text()).toBe('dd')
  })

  it('ui 未执行行(计划17 nodeid 快照):分组头=文件转 junit 点号惯例并入同文件已执行行,行名=函数名', async () => {
    api.getCiRun.mockClear()
    api.getCiRunConsole.mockClear()
    // ui run:同文件一函数已执行、一函数 stale 未执行(快照为 nodeid 键名 {file_path, function})
    api.getCiRun.mockResolvedValue({
      ...TERMINAL,
      kind: 'ui' as const,
      selection: [{ file_path: 'tests/test_login.py', function: 'test_stale', skipped: true, skip_reason: 'stale' }],
      results: [
        { class_name: 'tests.test_login', name: 'test_ok', status: 'passed', time_s: 0.2, message: null },
      ],
    })
    api.getCiRunConsole.mockResolvedValue('$ python -m pytest tests/test_login.py::test_stale --junitxml=report.xml\n')
    const w = mount(RunDetailPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('未执行')  // skipped 快照行标注仍在
    expect(w.text()).toContain('test_login')  // 分组头=文件名段(file_path 转 junit classname 点号惯例)
    expect(w.text()).toContain('test_stale')  // 行名=函数名(不再退化「脚本」)
    expect(w.text()).not.toContain('(未分类)')  // 不再落 CaseTree 未分类兜底
    expect(w.text()).not.toContain('脚本')
  })
})

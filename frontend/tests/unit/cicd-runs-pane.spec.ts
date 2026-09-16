// frontend/tests/unit/cicd-runs-pane.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listCiRuns: vi.fn() }))
vi.mock('../../src/api/cicd', () => api)
const routerState = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => routerState }))

import RunsPane from '../../src/components/cicd/RunsPane.vue'

const RUN = {
  id: 5, project_id: 3, plan_id: 1, plan_name: '接口回归', kind: 'api' as const, branch: 'master',
  selection: [], status: 'running' as const, jenkins_job: 'light_tester_p3_api', build_number: 4,
  jenkins_url: 'http://jk/job/j/4/', total: 2, passed: 1, failed: 1, skipped: 0, results: null,
  console_bytes: 100, error: null, freshness: null, created_at: '2026-09-16T10:00:00', finished_at: null,
}

describe('RunsPane', () => {
  it('渲染执行记录与状态标签,点行跳详情', async () => {
    api.listCiRuns.mockResolvedValue([RUN])
    const w = mount(RunsPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('接口回归')
    // 状态列渲染 STATUS_LABEL 文案('执行中'),原始 status 值不进 DOM——brief 断言按实现修正
    expect(w.text()).toContain('执行中')
    // EP 2.14 的 class-name 会同时落表头 TH 与表体 TD,须圈定在数据行内(仓内惯例 .el-table__row)
    await w.find('.el-table__row .row-click').trigger('click')
    // goDetail 传 String(id)(真实路由 :runId(\d+) 交付 string 参数),断言对齐实现
    expect(routerState.push).toHaveBeenCalledWith({ name: 'project-cicd-run-detail', params: { runId: '5' } })
    w.unmount() // 仓内惯例:清真实 3s 轮询定时器,避免泄到下一条用例
  })

  it('存在活跃记录时启动轮询,全终态后停止', async () => {
    vi.useFakeTimers()
    api.listCiRuns.mockClear() // hoisted mock 跨用例累积调用,绝对计数断言前先清零
    api.listCiRuns.mockResolvedValue([{ ...RUN, status: 'queued' }])
    const w = mount(RunsPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] } })
    await vi.advanceTimersByTimeAsync(0)
    expect(api.listCiRuns).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3100)
    expect(api.listCiRuns).toHaveBeenCalledTimes(2)
    api.listCiRuns.mockResolvedValue([{ ...RUN, status: 'success' }])
    await vi.advanceTimersByTimeAsync(3100)
    const calls = api.listCiRuns.mock.calls.length
    await vi.advanceTimersByTimeAsync(7000)
    expect(api.listCiRuns.mock.calls.length).toBe(calls) // 终态不再轮询
    vi.useRealTimers()
    w.unmount()
  })
})

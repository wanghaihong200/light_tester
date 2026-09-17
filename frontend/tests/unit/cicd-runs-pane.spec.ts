// frontend/tests/unit/cicd-runs-pane.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listCiRuns: vi.fn() }))
vi.mock('../../src/api/cicd', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/api/cicd')>()),  // 保留 ciRunDurationText 等纯函数
  listCiRuns: api.listCiRuns,
}))
const routerState = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => routerState }))

import RunsPane from '../../src/components/cicd/RunsPane.vue'

const RUN = {
  id: 5, project_id: 3, plan_id: 1, plan_name: '接口回归', kind: 'api' as const, branch: 'master',
  selection: [], status: 'running' as const, jenkins_job: 'light_tester_p3_api', build_number: 4,
  jenkins_url: 'http://jk/job/j/4/', total: 2, passed: 1, failed: 1, skipped: 0, results: null,
  console_bytes: 100, error: null, freshness: null,
  started_at: '2026-09-16T10:00:10', created_at: '2026-09-16T10:00:00', finished_at: null,
}

const DONE = {
  ...RUN, id: 6, status: 'success' as const,
  started_at: '2026-09-16T11:00:00', finished_at: '2026-09-16T11:01:30',
}

describe('RunsPane', () => {
  it('渲染执行记录与状态标签;点行不跳转,点「详情」按钮才跳', async () => {
    api.listCiRuns.mockResolvedValue([{ ...RUN, created_at: '2026-09-17T14:09:52' }])
    const w = mount(RunsPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('接口回归')
    // 状态列渲染 STATUS_LABEL 文案('执行中'),原始 status 值不进 DOM——brief 断言按实现修正
    expect(w.text()).toContain('执行中')
    // 触发时间格式:ISO 的 T 分隔换为空格(2026-09-17 用户拍板)
    expect(w.text()).toContain('2026-09-17 14:09:52')
    // 点数据行任意处不跳转(2026-09-17 用户拍板:仅「详情」按钮跳转)
    await w.find('.el-table__row').trigger('click')
    expect(routerState.push).not.toHaveBeenCalled()
    // 点「详情」按钮才跳;goDetail 传 String(id)(真实路由 :runId(\d+) 交付 string 参数)
    const btn = w.findAll('button').find((b) => b.text().includes('详情'))
    await btn!.trigger('click')
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

  it('时长列:90 秒的终态记录显示 1分30秒,无 started_at 显示 -', async () => {
    api.listCiRuns.mockClear()
    api.listCiRuns.mockResolvedValue([DONE, RUN])
    const w = mount(RunsPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('1分30秒')
    expect(w.text()).toContain('-')
    w.unmount()
  })

  it('分页:默认每页 10 条,超出部分进第二页', async () => {
    api.listCiRuns.mockClear()
    api.listCiRuns.mockResolvedValue(Array.from({ length: 12 }, (_, i) => ({ ...DONE, id: i + 1 })))
    const w = mount(RunsPane, {
      props: { projectId: 3 },
      global: { plugins: [[ElementPlus, { locale: zhCn }]] },  // 与 main.ts 同 locale,分页文案才是中文
    })
    await flushPromises()
    expect(w.findAll('.el-table__row')).toHaveLength(10) // 第一页只有 10 行
    expect(w.text()).toMatch(/共\s*12\s*条/)
    // 切到第二页 → 剩 2 行
    const next = w.find('.el-pagination .btn-next')
    await next.trigger('click')
    await flushPromises()
    expect(w.findAll('.el-table__row')).toHaveLength(2)
    w.unmount()
  })
})

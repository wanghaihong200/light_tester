// frontend/tests/unit/cicd-api.spec.ts
import { afterEach, describe, expect, it, vi } from 'vitest'

const calls: { path: string; init?: RequestInit }[] = []
vi.mock('../../src/api/client', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../../src/api/client')>()
  return {
    ...orig,
    getText: vi.fn(async (path: string) => { calls.push({ path }); return 'TEXT' }),
    http: {
      ...orig.http,
      get: vi.fn(async (path: string) => { calls.push({ path }); return { ok: true, path } }),
      post: vi.fn(async (path: string, body?: unknown) => { calls.push({ path, init: { body } }); return { ok: true, path, body } }),
      put: vi.fn(async (path: string, body: unknown) => { calls.push({ path, init: { body } }); return { ok: true, path, body } }),
      del: vi.fn(async (path: string) => { calls.push({ path }); return undefined }),
    },
  }
})

import { preflight, triggerRuns, ciRunEventsUrl, deletePlan, getCiRunConsole } from '../../src/api/cicd'

describe('api/cicd', () => {
  afterEach(() => { calls.length = 0 })

  it('preflight 走 ci-runs/preflight 且 body 为 plan_ids', async () => {
    await preflight(3, [7, 8])
    expect(calls[0].path).toBe('/projects/3/ci-runs/preflight')
    expect(calls[0].init?.body).toEqual({ plan_ids: [7, 8] })
  })

  it('triggerRuns 携带 confirm_stale', async () => {
    await triggerRuns(3, [7], true)
    expect(calls[0].path).toBe('/projects/3/ci-runs')
    expect(calls[0].init?.body).toEqual({ plan_ids: [7], confirm_stale: true })
  })

  it('deletePlan 与 SSE 地址', async () => {
    await deletePlan(9)
    expect(calls[0].path).toBe('/ci-plans/9')
    // 裸 EventSource 不走 http 客户端(无 /api baseURL),必须自带 /api 前缀——
    // 缺前缀时 vite 不代理,EventSource 404,详情页 console 全空(2026-09-17 冒烟缺陷)
    expect(ciRunEventsUrl(5)).toBe('/api/ci-runs/5/events')
  })

  it('console 全量日志走 getText 的 /ci-runs/{id}/console(/api 前缀由 client.getText 统一补)', async () => {
    await getCiRunConsole(7)
    expect(calls.at(-1)?.path).toBe('/ci-runs/7/console')
  })
})

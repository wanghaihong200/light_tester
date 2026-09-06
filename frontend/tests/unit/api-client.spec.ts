import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, http } from '../../src/api/client'

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => vi.unstubAllGlobals())

describe('http client', () => {
  it('GET 解析 JSON 响应体', async () => {
    const fn = stubFetch(200, [{ id: 1, name: '商城' }])
    const data = await http.get<{ id: number; name: string }[]>('/projects')
    expect(data).toEqual([{ id: 1, name: '商城' }])
    expect(fn.mock.calls[0][0]).toBe('/api/projects')
  })

  it('204 返回 undefined', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(http.del('/modules/1')).resolves.toBeUndefined()
  })

  it('非 2xx 抛 ApiError 且 message 取 detail', async () => {
    stubFetch(409, { detail: 'project name already exists' })
    const err = await http.post('/projects', { name: 'x' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(409)
    expect(err.message).toBe('project name already exists')
  })

  // 钉死生产端 body 传播:dict detail(plan11 导出校验 {errors:[…]})必须随 ApiError.body 抛出,
  // 否则弹窗侧错误清单静默退化为 [object Object](message 语义保持 String(detail) 不变)
  it('非 2xx 把解析后的 body 挂到 ApiError.body,message 语义不变', async () => {
    stubFetch(400, { detail: { errors: ['步骤1: ai_tap 无法导出'] } })
    const err = await http.post('/ui-scripts/42/export', { branch: 'main' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(400)
    expect((err as ApiError).body).toEqual({ detail: { errors: ['步骤1: ai_tap 无法导出'] } })
    expect(err.message).toBe('[object Object]')
  })

  it('非 2xx 且无 JSON body 时 message 回退为 HTTP 状态码', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })))
    const err = await http.get('/projects').catch((e) => e)
    expect((err as ApiError).status).toBe(500)
    expect(err.message).toBe('HTTP 500')
  })

  it('upload 走 FormData 且不设 Content-Type', async () => {
    const fn = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fn)
    const file = new File(['# 需求'], 'req.md', { type: 'text/markdown' })
    await http.upload('/projects/1/documents', file)
    const [, init] = fn.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.headers).toBeUndefined()
  })
})

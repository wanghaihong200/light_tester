import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  downloadFile,
  fetchBlobUrl,
  getToken,
  http,
  setToken,
  withSseToken,
} from '../../src/api/client'

function stubFetch(res: Response) {
  const fn = vi.fn().mockResolvedValue(res)
  vi.stubGlobal('fetch', fn)
  return fn
}

// jsdom 未实现 blob objectURL:换可预测替身,断言只关心「带鉴权发起请求 + 返回/下载产物」
const origObjectUrls = { create: URL.createObjectURL, revoke: URL.revokeObjectURL }
function stubObjectUrls() {
  let seq = 0
  const create = vi.fn(() => `blob:shot-${++seq}`)
  const revoke = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', { value: create, configurable: true, writable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: revoke, configurable: true, writable: true })
  return { create, revoke }
}

// 原生缺位时回填 no-op:避免 downloadFile 延迟 revoke 在替身撤除后打到 undefined
function restoreObjectUrls() {
  Object.defineProperty(URL, 'createObjectURL', {
    value: typeof origObjectUrls.create === 'function' ? origObjectUrls.create : () => '',
    configurable: true,
    writable: true,
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    value: typeof origObjectUrls.revoke === 'function' ? origObjectUrls.revoke : () => {},
    configurable: true,
    writable: true,
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  restoreObjectUrls()
  localStorage.clear()
  location.hash = '#/'
})

function headersOf(init: RequestInit): Record<string, string> {
  return (init.headers ?? {}) as Record<string, string>
}

describe('http 鉴权注入', () => {
  it('有 token:GET 自动带 Authorization: Bearer <token>,JSON Content-Type 保留', async () => {
    setToken('jwt-abc')
    const fn = stubFetch(
      new Response(JSON.stringify({ ok: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    await http.get('/projects')
    const [url, init] = fn.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/projects')
    const h = headersOf(init)
    expect(h.Authorization).toBe('Bearer jwt-abc')
    expect(h['Content-Type']).toBe('application/json')
  })

  it('无 token:不产生 Authorization 键(匿名请求语义不变)', async () => {
    const fn = stubFetch(new Response(JSON.stringify([]), { status: 200 }))
    await http.get('/projects')
    expect(headersOf(fn.mock.calls[0][1] as RequestInit).Authorization).toBeUndefined()
  })

  it('upload 带 token 时补 Authorization 且仍不设 Content-Type(multipart 边界交浏览器)', async () => {
    setToken('jwt-abc')
    const fn = stubFetch(new Response(null, { status: 204 }))
    await http.upload('/projects/1/documents', new File(['# 需求'], 'req.md', { type: 'text/markdown' }))
    const [, init] = fn.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBeInstanceOf(FormData)
    const h = headersOf(init)
    expect(h.Authorization).toBe('Bearer jwt-abc')
    expect(h['Content-Type']).toBeUndefined()
  })
})

describe('401 踢登录', () => {
  it('非登录页 401:清 token、跳 #/login 并抛 ApiError', async () => {
    setToken('jwt-abc')
    location.hash = '#/projects/1'
    stubFetch(new Response(JSON.stringify({ detail: '未登录或登录已过期' }), { status: 401 }))
    const err = await http.get('/projects').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(401)
    expect(err.message).toBe('未登录或登录已过期')
    expect(getToken()).toBeNull()
    expect(location.hash).toBe('#/login')
  })

  it('登录页路径下 401:不再跳转(防循环),保留 detail 与 token 交表单展示', async () => {
    setToken('jwt-abc')
    location.hash = '#/login'
    stubFetch(new Response(JSON.stringify({ detail: '用户名或密码错误' }), { status: 401 }))
    const err = await http.post('/auth/login', { username: 'a', password: 'b' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(401)
    expect(err.message).toBe('用户名或密码错误')
    expect(getToken()).toBe('jwt-abc')
    expect(location.hash).toBe('#/login')
  })
})

describe('直连资源鉴权(Step 0:img/a/window.open 带不了 Authorization)', () => {
  it('fetchBlobUrl 带 Authorization 取流并返回 objectURL', async () => {
    setToken('jwt-abc')
    const { create } = stubObjectUrls()
    const fn = stubFetch(new Response(new Blob(['jpg-bytes']), { status: 200 }))
    const url = await fetchBlobUrl('/ui-runs/5/screens/step_0_passed.jpg')
    const [reqUrl, init] = fn.mock.calls[0] as [string, RequestInit]
    expect(reqUrl).toBe('/api/ui-runs/5/screens/step_0_passed.jpg')
    expect(headersOf(init).Authorization).toBe('Bearer jwt-abc')
    expect(url).toBe('blob:shot-1')
    expect(create).toHaveBeenCalledOnce()
  })

  it('downloadFile 带 Authorization 取流,下载名优先取响应头 filename*', async () => {
    setToken('jwt-abc')
    const { create, revoke } = stubObjectUrls()
    const clicked: { anchor?: HTMLAnchorElement } = {}
    vi.spyOn(HTMLElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.anchor = this
    })
    const fn = stubFetch(
      new Response(new Blob(['xmind-bytes']), {
        status: 200,
        headers: { 'Content-Disposition': "attachment; filename*=UTF-8''%E5%95%86%E5%9F%8E.xmind" },
      }),
    )
    await downloadFile('/projects/1/export/xmind', 'fallback.xmind')
    const [reqUrl, init] = fn.mock.calls[0] as [string, RequestInit]
    expect(reqUrl).toBe('/api/projects/1/export/xmind')
    expect(headersOf(init).Authorization).toBe('Bearer jwt-abc')
    expect(create).toHaveBeenCalledOnce()
    expect(clicked.anchor?.download).toBe('商城.xmind') // RFC 5987 解码,中文项目名不乱码
    await new Promise((r) => setTimeout(r, 0)) // revoke 在点击派发后的宏任务里
    expect(revoke).toHaveBeenCalledOnce()
  })

  it('withSseToken:有 token 追加 ?token=(已有 query 用 &),无 token 原样', () => {
    setToken('jwt abc/1')
    expect(withSseToken('/api/jobs/1/events')).toBe('/api/jobs/1/events?token=jwt%20abc%2F1')
    expect(withSseToken('/api/ui-runs/2/events?x=1')).toBe('/api/ui-runs/2/events?x=1&token=jwt%20abc%2F1')
    setToken(null)
    expect(withSseToken('/api/jobs/1/events')).toBe('/api/jobs/1/events')
  })
})

const BASE = '/api'
const TOKEN_KEY = 'tt_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(t: string | null): void {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

// Authorization 头;无 token 时不产生该键(fetch 原样匿名请求)
function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// 401 且不在登录页 → 清 token 踢回登录;登录页自身的 401(如口令错误)交由表单展示 detail,防循环跳转
function throwOn401(res: Response): void {
  if (res.status === 401 && location.hash !== '#/login') {
    setToken(null)
    location.hash = '#/login'
    throw new ApiError(401, '未登录或登录已过期')
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers, ...rest } = options
  const extra = authHeaders()
  // FormData 不设 Content-Type(浏览器自动补 multipart boundary);无 token 且无额外头时保持 undefined(既有 upload 语义)
  const finalHeaders =
    rest.body instanceof FormData
      ? extra.Authorization
        ? { ...headers, ...extra }
        : headers
      : { 'Content-Type': 'application/json', ...headers, ...extra }
  const res = await fetch(BASE + path, { ...rest, headers: finalHeaders })
  throwOn401(res)
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const data: unknown = await res.json()
      if (data && typeof data === 'object' && 'detail' in data) message = String((data as { detail: unknown }).detail)
    } catch {
      // 响应体不是 JSON,保留 HTTP 状态码文案
    }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// ── 直连资源鉴权:后端全端点 401 门禁后,浏览器原生 img/a/window.open 带不了 Authorization 头 ──

// 内联展示类资源(如执行截图):fetch → blob → objectURL,由调用方在组件卸载时 revoke
export async function fetchBlobUrl(path: string): Promise<string> {
  const res = await fetch(BASE + path, { headers: authHeaders() })
  throwOn401(res)
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`)
  return URL.createObjectURL(await res.blob())
}

// 下载类资源(Content-Disposition 附件端点):fetch → blob → <a download> 触发保存;
// 文件名优先取响应头 filename*(RFC 5987,后端导出用中文项目名),缺省用调用方给的 fallback
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(BASE + path, { headers: authHeaders() })
  throwOn401(res)
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`)
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const m = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = m ? decodeURIComponent(m[1]) : fallbackName
  a.click()
  setTimeout(() => URL.revokeObjectURL(url)) // 点击派发完成后回收
}

// SSE 专用:裸 EventSource 无法带自定义头,后端 SSE 端点退而认 query ?token=(app/auth.py get_current_user_sse)
export function withSseToken(url: string): string {
  const token = getToken()
  if (!token) return url
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: (path: string) => request<void>(path, { method: 'DELETE' }),
  upload: <T>(path: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<T>(path, { method: 'POST', body: fd })
  },
}

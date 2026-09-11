"""透传引擎(计划 15,ADR-0011):未命中请求原样转发上游真实服务。
语义钉子:上游返回的任何 HTTP 响应(含 4xx/5xx)都算透传成功原样带回;
仅传输层失败(连不上/DNS/读超时)才 ok=False 交由调用方回落兜底响应。"""
from dataclasses import dataclass, field

import httpx

CONNECT_TIMEOUT = 5.0   # 连不上真实依赖 5s 即判死,回兜底
READ_TIMEOUT = 30.0     # 真实接口慢但活着,等满 30s
# hop-by-hop 头(RFC 7230)不随转发;host/content-length 由 httpx 依上游地址与实际体重算
_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}


@dataclass
class ForwardOutcome:
    ok: bool
    status_code: int = 0
    headers: dict[str, str | list[str]] = field(default_factory=dict)
    content_type: str | None = None
    content: bytes = b""
    error: str | None = None


def build_upstream_headers(headers: dict[str, str], upstream_host: str) -> dict[str, str]:
    out = {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}
    out["host"] = upstream_host
    return out


def build_client_response_headers(headers: httpx.Headers) -> dict[str, str | list[str]]:
    # set-cookie 单独走 get_list 取原始多条(items() 会把重复头逗号合并,
    # 劈坏 Expires=Wed, 21 Oct ... 这类含逗号的 cookie 值),其余头仍单值 str。
    out: dict[str, str | list[str]] = {
        k: v for k, v in headers.items()
        if k.lower() not in _HOP_BY_HOP and k.lower() not in ("content-type", "set-cookie")}
    cookies = headers.get_list("set-cookie")
    if cookies:
        out["set-cookie"] = cookies
    return out


async def forward(client: httpx.AsyncClient, base_url: str, method: str, path: str,
                  query: str | None, headers: dict[str, str], body: bytes) -> ForwardOutcome:
    try:
        url = f"{base_url.rstrip('/')}{path}" + (f"?{query}" if query else "")
        up_url = httpx.URL(base_url)
        up_host = up_url.host
        if up_url.port:
            up_host = f"{up_host}:{up_url.port}"
        resp = await client.request(method, url,
                                    headers=build_upstream_headers(headers, up_host), content=body)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as e:  # 传输层/URL 构造失败;HTTP 响应本身不抛
        return ForwardOutcome(ok=False, error=type(e).__name__)
    return ForwardOutcome(ok=True, status_code=resp.status_code,
                          headers=build_client_response_headers(resp.headers),
                          content_type=resp.headers.get("content-type"), content=resp.content)

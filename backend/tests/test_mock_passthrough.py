"""透传引擎单测(httpx.MockTransport,零真实网络)。"""
import httpx
import pytest

from app.mock_service import passthrough


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_forward_ok_any_status_including_5xx():
    """上游任何 HTTP 响应(含 5xx)都算透传成功,原样带回状态码/头/体。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")
    out = await passthrough.forward(_client(handler), "http://up:1", "GET", "/x/1", "a=1",
                                    {"host": "mock:9001", "x-tag": "t"}, b"")
    assert out.ok and out.status_code == 503 and out.content == b"down"


@pytest.mark.asyncio
async def test_forward_transport_error_returns_not_ok():
    """仅传输层失败(连不上/超时)才 ok=False,error 记异常类名。"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    out = await passthrough.forward(_client(handler), "http://up:1", "POST", "/x", None,
                                    {}, b'{"a":1}')
    assert not out.ok and out.error == "ConnectError" and out.status_code == 0


@pytest.mark.asyncio
async def test_forward_builds_url_query_body_and_host():
    """URL=base+path(+?query);body 原样;Host 改上游、hop-by-hop 剥除。"""
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), host=request.headers["host"],
                    keep=request.headers.get("x-keep"), te=request.headers.get("transfer-encoding"))
        return httpx.Response(200)
    await passthrough.forward(_client(handler), "http://up:1/", "POST", "/a/1", "b=2&c=",
                              {"host": "mock:9001", "x-keep": "y", "transfer-encoding": "chunked"},
                              b'{"a":1}')
    assert seen["url"] == "http://up:1/a/1?b=2&c="
    assert seen["host"] == "up:1"
    assert seen["keep"] == "y" and seen["te"] is None


@pytest.mark.asyncio
async def test_forward_invalid_url_returns_not_ok():
    """非法上游 URL(如 http://up:port)不抛穿,ok=False 记 InvalidURL 交兜底。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)
    out = await passthrough.forward(_client(handler), "http://up:port", "GET", "/x", None, {}, b"")
    assert not out.ok and out.error == "InvalidURL" and out.status_code == 0


@pytest.mark.asyncio
async def test_forward_preserves_multiple_set_cookie():
    """上游多条 Set-Cookie 保序原样保留为 list,不被 items() 逗号合并劈坏。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=[
            ("set-cookie", "sid=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT"),
            ("set-cookie", "theme=dark"),
        ])
    out = await passthrough.forward(_client(handler), "http://up:1", "GET", "/x", None, {}, b"")
    assert out.headers["set-cookie"] == ["sid=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT", "theme=dark"]


def test_build_client_response_headers_strips_hop_by_hop():
    from httpx import Headers
    out = passthrough.build_client_response_headers(
        Headers({"content-type": "application/json", "connection": "close", "x-ok": "1"}))
    assert out == {"x-ok": "1"}

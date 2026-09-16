"""Jenkins REST 客户端:API token Basic 认证(API token 认证免 CSRF crumb),零插件依赖。

仅封装平台用到的端点;所有失败统一抛 JenkinsError(带响应码与响应体前 300 字)。
transport 参数供测试注入 httpx.MockTransport,生产恒为 None(真实连接)。
"""
import time

import httpx


class JenkinsError(Exception):
    pass


class JenkinsClient:
    def __init__(self, base_url: str, api_user: str, api_token: str,
                 timeout: float = 15.0, transport: httpx.BaseTransport | None = None):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base, auth=(api_user, api_token),
                                    timeout=timeout, transport=transport)

    def __enter__(self) -> "JenkinsClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _raise(self, action: str, r: httpx.Response) -> None:
        raise JenkinsError(f"{action}失败 HTTP {r.status_code}: {r.text[:300]}")

    def test_connection(self) -> dict:
        try:
            r = self._client.get("/api/json")
        except httpx.HTTPError as e:
            raise JenkinsError(f"Jenkins 不可达: {e}") from e
        if r.status_code != 200:
            self._raise("连接测试", r)
        return {"ok": True}

    def job_exists(self, name: str) -> bool:
        r = self._client.get(f"/job/{name}/api.json")
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
        self._raise("查询 job", r)

    def create_pipeline_job(self, name: str, config_xml: str) -> None:
        r = self._client.post("/createItem", params={"name": name},
                              content=config_xml.encode("utf-8"),
                              headers={"Content-Type": "text/xml; charset=utf-8"})
        if r.status_code not in (200, 201):
            self._raise(f"创建 job {name}", r)

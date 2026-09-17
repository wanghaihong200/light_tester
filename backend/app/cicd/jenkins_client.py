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

    def _get(self, url: str, **kwargs) -> httpx.Response:
        try:
            return self._client.get(url, **kwargs)
        except httpx.HTTPError as e:
            raise JenkinsError(f"Jenkins 不可达: {e}") from e

    def _post(self, url: str, **kwargs) -> httpx.Response:
        try:
            return self._client.post(url, **kwargs)
        except httpx.HTTPError as e:
            raise JenkinsError(f"Jenkins 不可达: {e}") from e

    def test_connection(self) -> dict:
        r = self._get("/api/json")
        if r.status_code != 200:
            self._raise("连接测试", r)
        return {"ok": True}

    def job_exists(self, name: str) -> bool:
        # Jenkins REST 只有 /api/json 形式;/api.json 后缀式不存在,GET 恒 404(会被误读成 job 不存在)
        r = self._get(f"/job/{name}/api/json")
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
        self._raise("查询 job", r)

    def create_pipeline_job(self, name: str, config_xml: str) -> None:
        r = self._post("/createItem", params={"name": name},
                       content=config_xml.encode("utf-8"),
                       headers={"Content-Type": "text/xml; charset=utf-8"})
        if r.status_code not in (200, 201):
            self._raise(f"创建 job {name}", r)

    def trigger_build(self, name: str, params: dict[str, str], queue_timeout: float = 60.0) -> tuple[int, str]:
        """触发参数化构建并轮询队列至拿到 build 号;超时抛 JenkinsError。"""
        r = self._post(f"/job/{name}/buildWithParameters", params=params)
        if r.status_code != 201:
            self._raise("触发构建", r)
        location = r.headers.get("Location", "")
        qid = location.rstrip("/").rsplit("/", 1)[-1] if location else ""
        if not qid:
            raise JenkinsError("触发成功但响应缺少队列地址")
        deadline = time.monotonic() + queue_timeout
        while time.monotonic() < deadline:
            q = self._get(f"/queue/item/{qid}/api/json")
            if q.status_code == 200:
                exe = (q.json() or {}).get("executable") or {}
                if exe.get("number"):
                    url = exe.get("url") or f"{self._base}/job/{name}/{exe['number']}/"
                    return int(exe["number"]), url
            elif q.status_code == 404:
                # 真实例调度完成后 queue item 即被清除:按 queueId 回退匹配 job 的 builds
                r = self._get(f"/job/{name}/api/json",
                              params={"tree": "builds[number,url,queueId]{0,10}"})
                if r.status_code == 200:
                    for b in r.json().get("builds") or []:
                        if b.get("queueId") == int(qid):
                            url = b.get("url") or f"{self._base}/job/{name}/{b['number']}/"
                            return int(b["number"]), url
            time.sleep(0.5)
        raise JenkinsError("排队超时:Jenkins 队列未在时限内调度该构建")

    def get_build(self, name: str, number: int) -> dict | None:
        r = self._get(f"/job/{name}/{number}/api/json",
                      params={"tree": "building,result,url"})
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            self._raise("查询构建", r)
        d = r.json()
        return {"building": bool(d.get("building")), "result": d.get("result"), "url": d.get("url")}

    def read_console_chunk(self, name: str, number: int, start: int) -> tuple[str, int]:
        """progressiveText 增量:X-Text-Size 是日志的绝对字节偏移,作为下次 start。"""
        r = self._get(f"/job/{name}/{number}/logText/progressiveText",
                      params={"start": str(start)})
        if r.status_code != 200:
            self._raise("读取日志", r)
        size = int(r.headers.get("X-Text-Size", str(start + len(r.content))))
        return r.text, size

    def stop_build(self, name: str, number: int) -> None:
        r = self._post(f"/job/{name}/{number}/stop")
        if r.status_code not in (200, 201, 302):
            self._raise("停止构建", r)

    def list_artifacts(self, name: str, number: int) -> list[str]:
        r = self._get(f"/job/{name}/{number}/api/json",
                      params={"tree": "artifacts[relativePath]"})
        if r.status_code == 404:
            raise JenkinsError("构建不存在,无法列产物")
        if r.status_code != 200:
            self._raise("列产物", r)
        return [a["relativePath"] for a in r.json().get("artifacts") or []]

    def get_artifact(self, name: str, number: int, path: str) -> bytes:
        r = self._get(f"/job/{name}/{number}/artifact/{path.lstrip('/')}")
        if r.status_code != 200:
            self._raise(f"拉取产物 {path}", r)
        return r.content

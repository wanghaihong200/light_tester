"""计划 16 Task 2/3:JenkinsClient 全方法——httpx.MockTransport 驱动的内存版 Jenkins,绝不连真实例。"""
import json

import httpx
import pytest

from app.cicd.jenkins_client import JenkinsClient, JenkinsError


class FakeJenkins:
    """内存版 Jenkins:按请求路径分发;builds/logs/artifacts 由用例按需播种。"""

    def __init__(self):
        self.jobs: set[str] = set()
        self.builds: dict[tuple[str, int], dict] = {}
        self.logs: dict[tuple[str, int], bytes] = {}
        self.artifacts: dict[tuple[str, int], dict[str, bytes]] = {}
        self.params_log: list[dict] = []
        self.stopped: list[tuple[str, int]] = []
        self._next_build = 1
        self._queue: dict[str, int] = {}

    def trigger(self, job: str) -> int:
        n = self._next_build
        self._next_build += 1
        self.builds[(job, n)] = {"building": True, "result": None,
                                 "url": f"http://jk/job/{job}/{n}/"}
        return n

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if path == "/api/json":
            return httpx.Response(200, json={})
        if path == "/createItem" and method == "POST":
            self.jobs.add(request.url.params["name"])
            return httpx.Response(200)
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "job":
            job = parts[1]
            if len(parts) == 3 and parts[2] == "api.json" and method == "GET":
                return httpx.Response(200 if job in self.jobs else 404, json={})
            if len(parts) == 3 and parts[2] == "buildWithParameters" and method == "POST":
                self.params_log.append(dict(request.url.params))
                n = self.trigger(job)
                qid = f"q{n}"
                self._queue[qid] = n
                return httpx.Response(201, headers={"Location": f"http://jk/queue/item/{qid}/"})
            if len(parts) >= 3 and parts[2].isdigit():
                n = int(parts[2])
                if method == "POST" and len(parts) == 4 and parts[3] == "stop":
                    self.stopped.append((job, n))
                    self.builds[(job, n)]["building"] = False
                    self.builds[(job, n)]["result"] = "ABORTED"
                    return httpx.Response(200)
                if method == "GET" and parts[-1] == "api.json":
                    b = self.builds.get((job, n))
                    if b is None:
                        return httpx.Response(404, json={})
                    body = dict(b)
                    if request.url.params.get("tree", "").startswith("artifacts"):
                        body["artifacts"] = [{"relativePath": p} for p in self.artifacts.get((job, n), {})]
                    return httpx.Response(200, json=body)
                if method == "GET" and parts[-1] == "progressiveText":
                    start = int(request.url.params.get("start", "0"))
                    data = self.logs.get((job, n), b"")
                    return httpx.Response(200, content=data[start:],
                                          headers={"X-Text-Size": str(len(data))})
                if method == "GET" and parts[3] == "artifact":
                    rel = "/".join(parts[4:])
                    blob = self.artifacts.get((job, n), {}).get(rel)
                    if blob is None:
                        return httpx.Response(404)
                    return httpx.Response(200, content=blob)
        if path.startswith("/queue/item/") and path.endswith("api.json"):
            qid = parts[2]
            n = self._queue.get(qid)
            if n is None:
                return httpx.Response(404, json={})
            job = next(j for (j, bn) in self.builds if bn == n)
            return httpx.Response(200, json={"executable": {"number": n, "url": f"http://jk/job/{job}/{n}/"}})
        return httpx.Response(404)

    def client(self) -> JenkinsClient:
        return JenkinsClient("http://jk", "admin", "tok", transport=httpx.MockTransport(self.handler))


def test_test_connection_ok_and_failure():
    fk = FakeJenkins()
    with fk.client() as c:
        assert c.test_connection() == {"ok": True}
    bad = JenkinsClient("http://never", "a", "t",
                        transport=httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("x"))))
    with pytest.raises(JenkinsError):
        bad.test_connection()


def test_job_exists_and_create():
    fk = FakeJenkins()
    with fk.client() as c:
        assert c.job_exists("light_tester_p1_ui") is False
        c.create_pipeline_job("light_tester_p1_ui", "<flow-definition/>")
        assert c.job_exists("light_tester_p1_ui") is True

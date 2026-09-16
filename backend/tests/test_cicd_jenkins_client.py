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
                                 "url": f"http://jk/job/{job}/{n}/", "queue_id": n}
        return n

    def drop_queue_item(self, qid: str) -> None:
        """测试控制:模拟真实例调度后 queue item 被清除。"""
        self._queue.pop(str(qid), None)

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
                if job not in self.jobs:
                    return httpx.Response(404, json={})
                builds = [{"number": n, "url": b["url"], "queueId": b.get("queue_id")}
                          for (j, n), b in sorted(self.builds.items()) if j == job]
                return httpx.Response(200, json={"builds": builds})
            if len(parts) == 3 and parts[2] == "buildWithParameters" and method == "POST":
                self.params_log.append(dict(request.url.params))
                n = self.trigger(job)
                qid = str(n)  # 真实例 queue id 为整数
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


def test_trigger_build_resolves_queue():
    fk = FakeJenkins()
    with fk.client() as c:
        fk.jobs.add("j1")
        n, url = c.trigger_build("j1", {"BRANCH": "master"})
        assert n == 1 and url.endswith("/job/j1/1/")
        assert fk.params_log == [{"BRANCH": "master"}]


def test_get_build_and_console_and_stop():
    fk = FakeJenkins()
    fk.jobs.add("j1")
    n = fk.trigger("j1")
    fk.logs[( "j1", n)] = b"line1\nline2\n"
    with fk.client() as c:
        b = c.get_build("j1", n)
        assert b == {"building": True, "result": None, "url": f"http://jk/job/j1/{n}/"}
        chunk, offset = c.read_console_chunk("j1", n, 0)
        assert chunk == "line1\nline2\n" and offset == 12
        chunk2, _ = c.read_console_chunk("j1", n, 6)
        assert chunk2 == "line2\n"
        c.stop_build("j1", n)
        assert fk.stopped == [("j1", n)]
        assert c.get_build("j1", n)["result"] == "ABORTED"


def test_get_build_missing_returns_none():
    fk = FakeJenkins()
    with fk.client() as c:
        assert c.get_build("j1", 99) is None


def test_artifacts_roundtrip():
    fk = FakeJenkins()
    fk.jobs.add("j1")
    n = fk.trigger("j1")
    fk.artifacts[("j1", n)] = {"ci-results/junit.xml": b"<testsuites/>"}
    with fk.client() as c:
        assert c.list_artifacts("j1", n) == ["ci-results/junit.xml"]
        assert c.get_artifact("j1", n, "ci-results/junit.xml") == b"<testsuites/>"
        with pytest.raises(JenkinsError):
            c.get_artifact("j1", n, "nope.xml")


def test_trigger_queue_timeout_raises():
    fk = FakeJenkins()
    fk.jobs.add("j1")

    class NoSchedule(FakeJenkins):
        def handler(self, request):
            if "/queue/item/" in request.url.path:
                return httpx.Response(200, json={})  # 永不给出 executable
            return super().handler(request)

    ns = NoSchedule()
    ns.jobs = fk.jobs
    with ns.client() as c:
        with pytest.raises(JenkinsError, match="排队超时"):
            c.trigger_build("j1", {}, queue_timeout=1.5)


def test_transport_error_wrapped_as_jenkins_error():
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with JenkinsClient("http://never", "a", "t",
                       transport=httpx.MockTransport(unreachable)) as c:
        with pytest.raises(JenkinsError, match="Jenkins 不可达"):
            c.get_build("j1", 1)


def test_trigger_build_queue_item_dropped_falls_back_by_queue_id():
    class DropAfterTrigger(FakeJenkins):
        def handler(self, request):
            if request.url.path.endswith("/buildWithParameters"):
                resp = super().handler(request)
                qid = resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
                self.drop_queue_item(qid)  # 模拟:调度后 queue item 被清除,下次轮询即 404
                return resp
            return super().handler(request)

    fk = DropAfterTrigger()
    fk.jobs.add("j1")
    with fk.client() as c:
        n, url = c.trigger_build("j1", {})
        assert n == 1 and url.endswith("/job/j1/1/")


def test_trigger_build_queue_item_dropped_without_match_times_out():
    class DropAndUnmatch(FakeJenkins):
        def handler(self, request):
            if request.url.path.endswith("/buildWithParameters"):
                resp = super().handler(request)
                qid = resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
                self.drop_queue_item(qid)
                for b in self.builds.values():  # build 在跑但 queueId 对不上
                    b.pop("queue_id", None)
                return resp
            return super().handler(request)

    fk = DropAndUnmatch()
    fk.jobs.add("j1")
    with fk.client() as c:
        with pytest.raises(JenkinsError, match="排队超时"):
            c.trigger_build("j1", {}, queue_timeout=1.5)

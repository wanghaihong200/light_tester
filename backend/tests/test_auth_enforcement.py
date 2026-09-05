"""Task 4:业务端点全量 401 鉴权 + SSE query token。
探针原则:每个 router 至少一个真实端点、无 token 必须 401(而非 200/404/405)。
注:brief 原稿 4 个探针路径在本后端不可用(/api/jobs、/api/ui-runs/{id}/steps 不存在;
/api/ui-auth-states、/api/projects/1/modules 对 GET 是 405),已替换为同 router 的等价真实端点,
详见 task-4-report。"""
UNPROTECTED = {"/api/health"}


def test_all_business_endpoints_require_auth(client):
    # 无 token 访问代表性端点(每个 router 至少一个)必须 401,而非 200/404
    probes = [
        ("/api/projects", "GET"),                   # projects
        ("/api/projects/1/tree", "GET"),            # modules
        ("/api/cases/1", "GET"),                    # cases
        ("/api/projects/1/documents", "GET"),       # documents
        ("/api/projects/1/jobs", "GET"),            # jobs(非 SSE)
        ("/api/projects/1/repo/files", "GET"),      # repo
        ("/api/projects/1/ui-scripts", "GET"),      # ui_scripts
        ("/api/ui-runs/1", "GET"),                  # ui_runs(非 SSE)
        ("/api/projects/1/ui-auth-states", "GET"),  # ui_auth_states
        ("/api/jobs/1/events", "GET"),              # jobs SSE(query 无 token 也 401)
        ("/api/ui-runs/1/events", "GET"),           # ui_runs SSE
        ("/api/ui-recordings/1/events", "GET"),     # ui_recordings SSE
    ]
    for path, method in probes:
        assert getattr(client, method.lower())(path).status_code == 401, path


def test_ui_recordings_non_sse_requires_auth(client):
    # ui_recordings 无 GET 业务端点,用创建会话的 POST 探针(无鉴权时本应 404 项目不存在)
    assert client.post("/api/projects/1/ui-recordings", json={}).status_code == 401


def test_health_and_login_open(client):
    assert client.get("/api/health").status_code == 200


def test_401_detail_is_uniform(client):
    # 加分项:未带 token 的 401 文案统一(Task 3 评审延后项)
    r = client.get("/api/projects")
    assert r.status_code == 401 and r.json()["detail"] == "未登录或登录已过期"


def test_sse_query_token_accepted(client, db_session, make_user):
    make_user(db_session, "sseuser")
    tok = client.post("/api/auth/login", json={"username": "sseuser", "password": "pw-sseuser"}).json()["token"]
    # 用一个必然 404(任务不存在)但通过鉴权的探测:404 而非 401 即证明 token 生效
    r = client.get(f"/api/jobs/999999/events?token={tok}")
    assert r.status_code in (404, 200), "SSE query token 必须通过鉴权层"

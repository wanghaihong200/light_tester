import pytest

from app.config import settings


@pytest.fixture()
def ah(client, db_session):
    """Task 6 存量用例补鉴权(保语义,补鉴权):bootstrap admin 登录头,admin 对所有项目直通。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def pid(client, ah):
    return client.post("/api/projects", json={"name": "P"}, headers=ah).json()["id"]


def test_upload_list_download_md(client, ah, pid):
    resp = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("login-req.md", "# 登录需求\n账号密码登录...".encode("utf-8"), "text/markdown")},
        headers=ah,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    docs = client.get(f"/api/projects/{pid}/documents", headers=ah).json()
    assert [d["filename"] for d in docs] == ["login-req.md"]

    dl = client.get(f"/api/documents/{doc_id}/download", headers=ah)
    assert dl.status_code == 200
    assert "登录需求" in dl.text


def test_reject_non_markdown(client, ah, pid):
    resp = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("spec.docx", b"binary", "application/octet-stream")},
        headers=ah,
    )
    assert resp.status_code == 400


def test_delete_document(client, ah, pid):
    doc_id = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("a.md", b"# a", "text/markdown")},
        headers=ah,
    ).json()["id"]

    # Count files before delete
    files_before = list((settings.uploads_dir / str(pid)).glob("*"))
    count_before = len(files_before)

    # Delete document
    assert client.delete(f"/api/documents/{doc_id}", headers=ah).status_code == 204

    # Verify DB record is gone (404 from DB check)
    assert client.get(f"/api/documents/{doc_id}/download", headers=ah).status_code == 404

    # Verify disk file is deleted (count should decrease by 1)
    files_after = list((settings.uploads_dir / str(pid)).glob("*"))
    assert len(files_after) == count_before - 1

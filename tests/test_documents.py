import pytest

from app.config import settings


@pytest.fixture()
def pid(client):
    return client.post("/api/projects", json={"name": "P"}).json()["id"]


def test_upload_list_download_md(client, pid):
    resp = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("login-req.md", "# 登录需求\n账号密码登录...".encode("utf-8"), "text/markdown")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    docs = client.get(f"/api/projects/{pid}/documents").json()
    assert [d["filename"] for d in docs] == ["login-req.md"]

    dl = client.get(f"/api/documents/{doc_id}/download")
    assert dl.status_code == 200
    assert "登录需求" in dl.text


def test_reject_non_markdown(client, pid):
    resp = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("spec.docx", b"binary", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_delete_document(client, pid):
    doc_id = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("a.md", b"# a", "text/markdown")},
    ).json()["id"]

    # Count files before delete
    files_before = list((settings.uploads_dir / str(pid)).glob("*"))
    count_before = len(files_before)

    # Delete document
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204

    # Verify DB record is gone (404 from DB check)
    assert client.get(f"/api/documents/{doc_id}/download").status_code == 404

    # Verify disk file is deleted (count should decrease by 1)
    files_after = list((settings.uploads_dir / str(pid)).glob("*"))
    assert len(files_after) == count_before - 1

# app/routers/ui_auth_states.py
"""登录态:采集会话复用 InteractiveSession(不注入工具条,不转发事件),
用户在弹出的浏览器里完成登录,save 时经 sess.call() 在会话线程内导出 storage_state。"""
import itertools
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Project, UiAuthState
from app.schemas import UiAuthStateOut
from app.ui_automation.session import INTERACTIVE_SLOT, InteractiveSession

router = APIRouter(prefix="/api", tags=["ui-auth-states"])

_collects: dict[int, InteractiveSession] = {}
_lock = threading.Lock()
_ids = itertools.count(1)


class CollectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/projects/{project_id}/ui-auth-states/collect", status_code=201)
def start_collect(project_id: int, payload: CollectCreate, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    if not INTERACTIVE_SLOT.acquire(blocking=False):
        raise HTTPException(409, "已有录制/登录态采集会话进行中")
    cid = next(_ids)
    # 占槽成功即拥有会话权,释放随 on_close(会话线程退出时触发),与 ui_recordings 同模式
    released = threading.Event()

    def on_close():
        if not released.is_set():
            released.set()
            with _lock:
                _collects.pop(cid, None)
            INTERACTIVE_SLOT.release()

    try:
        sess = InteractiveSession(cid, headless=False, start_url="about:blank",
                                  storage_state=None, on_raw=lambda e: None,
                                  on_frame=lambda b64: None, on_close=on_close,
                                  with_toolbar=False)
        sess._project_id = project_id  # save 时要用;挂在会话对象上与会话同生命周期
        sess._name = payload.name
        with _lock:
            _collects[cid] = sess
    except Exception:
        on_close()  # 就地释放,避免锁泄漏把后续所有会话卡死在 409
        raise
    return {"collect_id": cid}


@router.post("/ui-auth-collect/{cid}/save", response_model=UiAuthStateOut, status_code=201)
def save_collect(cid: int, db: Session = Depends(get_db)):
    sess = _collects.get(cid)
    if sess is None:
        raise HTTPException(404, "collect session not found")
    auth_dir = settings.ui_data_dir / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    # 文件名用 DB 自增 id 而非进程内计数:行与文件都跨重启持久,进程内计数重启后从 1 重来,
    # 会命中旧文件静默覆盖,删旧行时 unlink 还会连带删掉新行正用的文件。
    # 先 flush 拿 id 再导出(未提交),导出失败回滚即不留 storage_path 为空的孤儿行
    row = UiAuthState(project_id=sess._project_id, name=sess._name, storage_path="")
    db.add(row)
    db.flush()
    path = (auth_dir / f"{sess._project_id}_{row.id}.json").resolve()
    try:
        # 导出必须在会话线程内做(跨线程直调 context 会 greenlet 报错),经 call() 投递
        ctx = sess.browser_context()
        sess.call(lambda: ctx.storage_state(path=str(path)))
    except Exception as e:
        db.rollback()  # 显式回滚占位行
        sess.stop()  # 会话已坏:交给 on_close 释放槽位,调用方需重新采集
        raise HTTPException(409, f"采集会话已结束,无法导出登录态: {e}") from e
    row.storage_path = str(path)
    db.commit()
    db.refresh(row)
    sess.stop()  # 采集完成即关会话;槽位随 on_close 释放
    return row


@router.post("/ui-auth-collect/{cid}/cancel", status_code=204)
def cancel_collect(cid: int):
    sess = _collects.get(cid)
    if sess is None:
        raise HTTPException(404, "collect session not found")
    sess.stop()  # 丢弃不落库;槽位随 on_close 释放
    return Response(status_code=204)


@router.get("/projects/{project_id}/ui-auth-states", response_model=list[UiAuthStateOut])
def list_auth_states(project_id: int, db: Session = Depends(get_db)):
    return (db.query(UiAuthState)
            .filter(UiAuthState.project_id == project_id, UiAuthState.is_deleted.is_(False))
            .order_by(UiAuthState.id.desc()).all())


@router.delete("/ui-auth-states/{auth_id}", status_code=204)
def delete_auth_state(auth_id: int, db: Session = Depends(get_db)):
    row = db.get(UiAuthState, auth_id)
    if row is None or row.is_deleted:
        raise HTTPException(404, "auth state not found")
    row.is_deleted = True
    db.commit()
    from pathlib import Path
    Path(row.storage_path).unlink(missing_ok=True)  # 文件一并清;软删行保留审计痕迹
    return Response(status_code=204)

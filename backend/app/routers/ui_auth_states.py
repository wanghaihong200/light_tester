# app/routers/ui_auth_states.py
"""登录态:采集会话复用 InteractiveSession(不注入工具条,不转发事件),
用户在弹出的浏览器里完成登录,save 时经 sess.call() 在会话线程内导出 storage_state。"""
import itertools
import threading
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import get_current_user
from app.database import get_db
from app.models import Project, UiAuthState, User
from app.permissions import ensure_project_access
from app.schemas import UiAuthStateOut
from app.ui_automation.session import INTERACTIVE_SLOT, InteractiveSession

router = APIRouter(prefix="/api", tags=["ui-auth-states"], dependencies=[Depends(get_current_user)])


@dataclass
class CollectSession:
    """采集会话薄包装:项目/名字是采集业务的属性,不该挂到通用 InteractiveSession
    实例上(替代旧的 sess._project_id / sess._name 私有属性幽灵)。"""
    session: InteractiveSession
    project_id: int
    name: str


_collects: dict[int, CollectSession] = {}
_lock = threading.Lock()
_ids = itertools.count(1)


class CollectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/projects/{project_id}/ui-auth-states/collect", status_code=201)
def start_collect(project_id: int, payload: CollectCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    ensure_project_access(db, current, project_id, "editor")  # 开采集 = 写(先于占交互槽)
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
                                  with_toolbar=False, capture_frames=False)
        with _lock:
            _collects[cid] = CollectSession(sess, project_id, payload.name)
    except Exception:
        on_close()  # 就地释放,避免锁泄漏把后续所有会话卡死在 409
        raise
    return {"collect_id": cid}


def _take_owned(cid: int, db: Session, current: User, min_role: str) -> CollectSession:
    """会话级闸门 + 所有权移交:先窥视过闸(角色不足 → 403,会话原样保留,
    不能借 save/cancel 毁掉别人的采集会话),闸过才 pop(并发第二路 → 404)。"""
    with _lock:
        cs = _collects.get(cid)
        if cs is None:
            raise HTTPException(404, "collect session not found")
    ensure_project_access(db, current, cs.project_id, min_role)
    taken = _collects.pop(cid, None)
    if taken is None:  # 过闸窗口内被并发取走:与「不存在」同语义
        raise HTTPException(404, "collect session not found")
    return taken


@router.post("/ui-auth-collect/{cid}/save", response_model=UiAuthStateOut, status_code=201)
def save_collect(cid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # 所有权移交:开头取到手才允许导出,并发的第二次 save 到此即为 404,
    # 从根上排除两路 save 各落一行的可能;终态路径不回插
    cs = _take_owned(cid, db, current, "editor")  # save 落库 = 写
    sess = cs.session
    try:
        auth_dir = settings.ui_data_dir / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        # 文件名用 DB 自增 id 而非进程内计数:行与文件都跨重启持久,进程内计数重启后从 1 重来,
        # 会命中旧文件静默覆盖,删旧行时 unlink 还会连带删掉新行正用的文件。
        # 先 flush 拿 id 再导出(未提交),任何一步失败回滚即不留 storage_path 为空的孤儿行
        # save 是纯新建(所有权移交保证并发只落一行,无 upsert 更新路径):首次落库写 created_by
        row = UiAuthState(project_id=cs.project_id, name=cs.name, storage_path="", created_by=current.id)
        db.add(row)
        db.flush()
        path = (auth_dir / f"{cs.project_id}_{row.id}.json").resolve()
        try:
            # 导出必须在会话线程内做(跨线程直调 context 会 greenlet 报错),经 call() 投递
            ctx = sess.browser_context()
            sess.call(lambda: ctx.storage_state(path=str(path)))
        except RuntimeError as e:
            # 会话/浏览器已关,重试必然再败:停掉并清理,用户须重新采集
            db.rollback()  # 显式回滚占位行
            sess.stop()  # 交给 on_close 释放槽位
            raise HTTPException(409, f"采集会话已结束,无法导出登录态: {e}") from e
        row.storage_path = str(path)
        db.commit()
        db.refresh(row)
    except HTTPException:
        raise  # 409 已按口径处理完(回滚+停会话),原样透传
    except Exception as e:
        # mkdir/落库/导出写盘等失败,会话本身仍健康:回滚占位行后回插所有权,
        # 保留会话让用户重试 save(条目已被 pop,不回插的话重试只能 404、窗口还占着交互槽)
        db.rollback()
        with _lock:
            _collects[cid] = cs
        raise HTTPException(500, f"登录态保存失败,会话已保留可重试: {e}") from e
    sess.stop()  # 采集完成即关会话;槽位随 on_close 释放
    return row


@router.post("/ui-auth-collect/{cid}/cancel", status_code=204)
def cancel_collect(cid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    cs = _take_owned(cid, db, current, "editor")  # 同 save 的闸门+所有权移交:取消与保存互斥,先到先得
    cs.session.stop()  # 丢弃不落库;槽位随 on_close 释放
    return Response(status_code=204)


@router.get("/projects/{project_id}/ui-auth-states", response_model=list[UiAuthStateOut])
def list_auth_states(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    return (db.query(UiAuthState)
            .filter(UiAuthState.project_id == project_id, UiAuthState.is_deleted.is_(False))
            .order_by(UiAuthState.id.desc()).all())


@router.delete("/ui-auth-states/{auth_id}", status_code=204)
def delete_auth_state(auth_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = db.get(UiAuthState, auth_id)
    if row is None or row.is_deleted:
        raise HTTPException(404, "auth state not found")
    ensure_project_access(db, current, row.project_id, "editor")  # 删登录态(连带删文件)= 写
    row.is_deleted = True
    db.commit()
    from pathlib import Path
    Path(row.storage_path).unlink(missing_ok=True)  # 文件一并清;软删行保留审计痕迹
    return Response(status_code=204)

# app/routers/ui_recordings.py
"""录制会话 API:会话对象在内存,rid 用自增计数(不落库,停止才产草稿)。"""
import itertools
import json
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_sse
from app.database import get_db
from app.models import Project, UiAuthState, User
from app.ui_automation.recorder import INTERACTIVE_SLOT, RecordingSession, rec_bus

router = APIRouter(prefix="/api", tags=["ui-recordings"])

_sessions: dict[int, RecordingSession] = {}
_lock = threading.Lock()
_ids = itertools.count(1)


def _get_active(rid: int) -> RecordingSession:
    s = _sessions.get(rid)
    if s is None:
        raise HTTPException(404, "recording not found")
    return s


class RecordCreate(BaseModel):
    auth_state_id: int | None = None


class AssertInsert(BaseModel):
    target: dict
    assert_type: str = Field(pattern="^(assert_visible|assert_text|assert_exists)$")
    text: str | None = None
    mode: str | None = Field(default=None, pattern="^(equals|contains)$")


@router.post("/projects/{project_id}/ui-recordings", status_code=201)
def start_recording(project_id: int, payload: RecordCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    storage = None
    if payload.auth_state_id is not None:
        # 与 ui_runs 同源校验:存在、未软删、且属于本项目(防跨项目引用)
        auth = db.get(UiAuthState, payload.auth_state_id)
        if auth is None or auth.is_deleted or auth.project_id != project_id:
            raise HTTPException(400, "invalid auth_state_id")
        storage = str(auth.storage_path)
    if not INTERACTIVE_SLOT.acquire(blocking=False):
        raise HTTPException(409, "已有录制/登录态采集会话进行中")
    rid = next(_ids)
    # 占锁成功即拥有会话权,释放随 on_close 回调(会话线程退出时触发),消灭锁泄漏窗口
    released = threading.Event()

    def release():
        if not released.is_set():
            released.set()
            with _lock:
                _sessions.pop(rid, None)
            INTERACTIVE_SLOT.release()

    try:
        sess = RecordingSession(rid, storage_path=storage, on_close=release)
        with _lock:
            _sessions[rid] = sess
        sess.start()  # 构造即已启动;此处幂等,保留以显式表达「进入会话」
    except Exception:
        release()  # 就地释放,避免锁泄漏把后续所有录制卡死在 409
        raise
    return {"recording_id": rid}


@router.get("/ui-recordings/{rid}/events")
async def recording_events(rid: int, current: User = Depends(get_current_user_sse)):
    """SSE 实时流:断线重连先补发已有步骤,再持续推帧/步骤/断言候选,直到 stopped。"""
    _get_active(rid)
    queue = rec_bus.subscribe(rid)
    sess = _sessions.get(rid)
    if sess is None:  # 订阅间隙恰好结束:发终态前直接 404,避免流挂死
        rec_bus.unsubscribe(rid, queue)
        raise HTTPException(404, "recording not found")

    async def stream():
        try:
            for st in sess.steps():  # 断线重连补发已有步骤
                yield f"data: {json.dumps({'type': 'action', 'step': st}, ensure_ascii=False)}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "stopped":
                    return
        finally:
            rec_bus.unsubscribe(rid, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ui-recordings/{rid}/assert")
def insert_assert(rid: int, payload: AssertInsert, current: User = Depends(get_current_user)):
    """断言模式点击出的候选元素,由前端选定类型后回调插入,实时推流给录制面板。"""
    sess = _get_active(rid)
    sess.insert_assert(payload.target, payload.assert_type, payload.text, payload.mode)
    return {"steps": sess.steps()}


@router.post("/ui-recordings/{rid}/stop")
def stop_recording(rid: int, current: User = Depends(get_current_user)):
    """停止录制并返回草稿({meta,variables,steps});会话已结束则 404。"""
    sess = _get_active(rid)
    return sess.stop()


@router.post("/ui-recordings/{rid}/cancel", status_code=204)
def cancel_recording(rid: int, current: User = Depends(get_current_user)):
    sess = _get_active(rid)
    sess.stop()  # 草稿丢弃,仅停会话;槽位随 on_close 释放
    return Response(status_code=204)

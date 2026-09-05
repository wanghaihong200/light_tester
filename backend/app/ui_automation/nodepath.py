# app/ui_automation/nodepath.py
"""执行路径判定与端锁:含 AI 步或 target≠web 的脚本走 Node(Midscene),其余走原 Python 执行器。
端锁每端一把(同端同时至多一个 Node 会话,录制/执行共用),仅 Node 路径 acquire。"""
import threading

TARGETS = ("web", "android", "harmony")
TARGET_LOCKS: dict[str, threading.BoundedSemaphore] = {
    t: threading.BoundedSemaphore(1) for t in TARGETS
}


def driver_target(doc: dict) -> str:
    t = (doc.get("meta") or {}).get("target") if isinstance(doc.get("meta"), dict) else None
    return t if t in TARGETS else "web"


def needs_node(doc: dict) -> bool:
    if driver_target(doc) != "web":
        return True
    return any(isinstance(st, dict) and str(st.get("action", "")).startswith("ai_")
               for st in (doc.get("steps") or []))

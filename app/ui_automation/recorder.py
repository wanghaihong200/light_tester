# app/ui_automation/recorder.py
"""录制会话:原始事件流 → 增量映射 DSL 步骤 → SSE;停止时产出草稿。
rec_bus 与 jobs bus 同实现不同实例,避免 recording_id 与 run_id 冲突。"""
import asyncio
import itertools
import threading

from app.jobs.bus import JobEventBus
from app.ui_automation import events
from app.ui_automation.loopref import ui_loop
from app.ui_automation.session import INTERACTIVE_SLOT, InteractiveSession  # noqa: F401

rec_bus = JobEventBus()


def _sig(step: dict) -> dict:
    """步骤语义签名(不含 id):dedupe_and_map 每次全量重映射都会重新发号,
    同一位置的步骤 id 变化不算内容变化。"""
    return {k: v for k, v in step.items() if k != "id"}


class RecordingSession:
    def __init__(self, recording_id: int, *, headless: bool = False, start_url: str = "",
                 storage_state: str | None = None, storage_path: str | None = None,
                 on_close=lambda: None, on_event=lambda e: None, bus: JobEventBus = rec_bus):
        self.recording_id = recording_id
        self.on_event = on_event
        self._bus = bus
        self._close_cb = on_close
        self._headless = headless  # 交互会话默认有头;测试传 headless=True
        # 登录态文件路径:storage_path 为准(路由传入),storage_state 为等价别名
        self._storage_path = storage_path if storage_path is not None else storage_state
        self._raw: list[dict] = []
        self._main: list[dict] = []  # 主干:与全量重映射结果逐位对齐的最终步骤
        # 手工断言:(插入时主干长度 before_len, 步骤) —— stop/steps 按它穿插回原位
        self._asserts: list[tuple[int, dict]] = []
        self._ids = itertools.count(1)  # 断言步骤 id 会话内自增,稳定且不重复
        self._lock = threading.Lock()
        self._session: InteractiveSession | None = None
        self._started = False
        self._start_url = start_url
        self.start()  # 构造即开会话(简报测试直接构造后就用);start 由此幂等

    # ── 生命周期 ──
    def start(self) -> None:
        if self._started:
            return
        self._session = InteractiveSession(
            self.recording_id, headless=self._headless, start_url=self._start_url,
            storage_state=self._storage_path, on_raw=self._on_raw,
            on_frame=lambda b64: self._emit({"type": "frame", "data": b64}),
            on_close=self._on_close, with_toolbar=True)
        self._started = True  # 构造失败(浏览器起不来)时保持 False,调用方可重试

    def stop(self) -> dict:
        """停止会话并产出草稿。收尾做一次全量重映射(此后无新事件,末尾 flush 安全)。"""
        if self._session is not None:
            self._session.stop()
            self._session.join(timeout=10)
        with self._lock:
            self._sync_locked(events.dedupe_and_map(self._raw))
            steps = self._merged_locked()
        start_url = next((s["params"]["url"] for s in steps if s["action"] == "goto"),
                         self._start_url or "")
        return {"meta": {"start_url": start_url}, "variables": [], "steps": steps}

    def join(self, timeout: float | None = None) -> None:
        if self._session is not None:
            self._session.join(timeout)

    def current_page(self, timeout: float = 15.0):
        """首个页面(跨线程代理):外部用它驱动页面(测试程序化操作/登录态采集)。"""
        if self._session is None:
            raise RuntimeError("recording not started")
        return self._session.current_page(timeout)

    def steps(self) -> list[dict]:
        """当前步骤序列:主干 + 手工断言按 before_len 穿插(SSE 重连补发也用它)。"""
        with self._lock:
            return self._merged_locked()

    def insert_assert(self, target: dict, assert_type: str, text: str | None,
                      mode: str | None) -> dict:
        """断言模式点击后由前端选定类型回调插入,before_len 记录插入位置。"""
        step = {"id": f"st_assert_{next(self._ids)}", "action": assert_type,
                "locator": events.target_to_locator(target)}
        if assert_type == "assert_text":
            step["params"] = {"text": text or "", "mode": mode or "contains"}
        with self._lock:
            self._asserts.append((len(self._main), step))
        self._emit({"type": "action", "step": step, "summary": events.step_summary(step)})
        return step

    # ── 内部 ──
    def _on_close(self) -> None:
        # 先注销再广播 stopped:若先 publish 后 pop,晚于 publish 的订阅者在
        # 「publish 早于 subscribe 且 pop 晚于 get」窗口内会等不到终态,单连接挂死
        self._close_cb()
        self._emit({"type": "stopped"})

    def _emit(self, event: dict) -> None:
        """统一出口:回调外部 on_event + 投递 rec_bus(经主循环,与 runner._notify_bus 同构)。"""
        try:
            self.on_event(event)
        except Exception:
            pass  # 回调方异常不能打断录制线程
        loop = ui_loop()
        if loop is not None and not loop.is_closed():
            coro = self._bus.publish(self.recording_id, event)
            try:
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                fut.add_done_callback(lambda f: None if f.cancelled() else f.exception())
            except Exception:
                coro.close()  # 主循环不可调度(应用退出中):消费掉协程再丢事件

    def _on_raw(self, ev: dict) -> None:
        if ev["kind"] == "assert_click":
            self._emit({"type": "assert_candidate",
                        "summary": "请选择断言类型", "target": ev["target"]})
            return
        with self._lock:
            self._raw.append(ev)
            changed = self._sync_locked(events.dedupe_and_map(self._raw))
        for st in changed:  # 锁外通知,避免回调重入死锁
            self._emit({"type": "action", "step": st, "summary": events.step_summary(st)})

    def _sync_locked(self, mapped: list[dict]) -> list[dict]:
        """把全量重映射结果逐位对齐到主干,返回内容有变化的步骤(需对外通知)。
        映射流只有末尾待定稿的 fill 会被后续输入改写,前面位置恒定,逐位对齐因此成立;
        同一位置沿用旧 id,保证流式步骤 id 稳定。调用方须已持锁。"""
        changed: list[dict] = []
        for i, st in enumerate(mapped):
            final = events.finalize_steps([st])[0]
            if i < len(self._main):
                if _sig(final) != _sig(self._main[i]):
                    final["id"] = self._main[i]["id"]
                    self._main[i] = final
                    changed.append(final)
            else:
                self._main.append(final)
                changed.append(final)
        return changed

    def _merged_locked(self) -> list[dict]:
        """主干为主序,断言按各自 before_len 插回对应穿插位置(before_len 语义是
        「插在第 before_len 个主干步骤之前」,已插入的同位/前置断言各占一位)。调用方须已持锁。"""
        out = list(self._main)
        placed = 0
        for before_len, st in sorted(self._asserts, key=lambda t: t[0]):
            out.insert(min(before_len + placed, len(out)), st)
            placed += 1
        return out

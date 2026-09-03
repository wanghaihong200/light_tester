# app/ui_automation/session.py
"""有头交互会话基建:录制与登录态采集共用。
要点:context 级 add_init_script → 新开标签页自动带采集脚本(多标签页跟随);
binding 用 context.expose_binding → 所有 page 可调;会话线程持续推预览帧。

线程模型(sync API 的两条 greenlet 硬约束,均已实测验证,设计由此而来):
①派发 greenlet 绑定创建线程,外部线程直调 page 会抛 greenlet.error ——
  所以 current_page() 返回跨线程代理,方法调用经队列投递回会话线程执行;
②事件只在 sync 调用进行中派发,纯 time.sleep 期间一条都不会到 ——
  所以主循环用 page.wait_for_timeout() 做协议级等待,期间持续派发
  点击/输入/跳转事件,预览帧同样在会话线程内取(跨线程截图同罪①)。"""
import concurrent.futures
import queue
import threading
import time

from app.ui_automation.injected import COLLECT_JS, TOOLBAR_JS

INTERACTIVE_SLOT = threading.Lock()  # 全局同时 1 个交互会话(录制或登录态采集)
_FRAME_INTERVAL = 0.6  # 预览帧间隔秒
_PUMP_MS = 200  # 协议级等待时长:决定用户事件的派发延迟上限
_CALL_TIMEOUT = 30.0  # 外部投递调用的兜底超时,防会话已死时调用方永久挂起


class _ThreadProxy:
    """跨线程代理:属性/方法访问整体投递到会话线程执行并带回真实返回值,
    用法与原对象一致(page.fill(...) / page.keyboard.press(...) / page.url)。
    返回值若还是 playwright 包装对象(有 _impl_obj)则继续包一层代理,链式调用不破功。"""

    def __init__(self, call, target_fn):
        object.__setattr__(self, "_call", call)          # 投递器:fn() 在会话线程执行
        object.__setattr__(self, "_target_fn", target_fn)  # 会话线程内解析真实目标

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)  # 协议方法不做跨线程往返
        if not self._call(lambda: callable(getattr(self._target_fn(), name))):
            # 普通属性(page.url / page.keyboard):回传值,playwright 对象再包一层代理
            return _wrap(self._call(lambda: getattr(self._target_fn(), name)), self._call)

        def _access(*args, **kwargs):
            def job():
                return getattr(self._target_fn(), name)(*args, **kwargs)

            return _wrap(self._call(job), self._call)

        return _access


def _wrap(value, call):
    """playwright 包装对象 → 继续代理;普通值(字符串/数字/None 等)原样回传。"""
    if value is not None and hasattr(value, "_impl_obj"):
        return _ThreadProxy(call, lambda: value)
    return value


class InteractiveSession:
    def __init__(self, session_id: int, *, headless: bool, start_url: str,
                 storage_state: str | None, on_raw, on_frame, on_close,
                 with_toolbar: bool = True, capture_frames: bool = True):
        self.session_id = session_id
        self._context = None
        self._capture_frames = capture_frames  # 无预览面板的会话(登录态采集)不采帧
        self._cdp: dict = {}              # page → CDP 会话(预览帧直采,抖动修复)
        self._ready = threading.Event()   # 首个页面就绪(start_url 已加载)
        self._closed = threading.Event()  # 会话线程已退出
        self._stop = threading.Event()    # 请求停止(stop 后 ≤_PUMP_MS 内生效)
        self._calls: "queue.Queue" = queue.Queue()  # 外部线程 → 会话线程 的调用队列
        self._thread = threading.Thread(target=self._run, daemon=True, args=(
            headless, start_url, storage_state, on_raw, on_frame, on_close, with_toolbar))
        self._thread.start()

    # ── 供外部等待首个页面(录制面板要立刻显示画面) ──
    def current_page(self, timeout: float = 15.0) -> _ThreadProxy:
        if not self._ready.wait(timeout):
            if self._closed.is_set():
                raise RuntimeError("session closed before page ready")
            raise TimeoutError("page not ready")
        return _ThreadProxy(self.call, self._current_page_obj)

    def _current_page_obj(self):
        """会话线程内解析当前页:最近标签页(多标签页跟随,与 runner 一致)。"""
        return self._context.pages[-1] if (self._context and self._context.pages) else None

    def browser_context(self):
        """原始 context(登录态导出用);跨线程操作它请走 call(),勿直接调方法。"""
        return self._context

    def call(self, fn, timeout: float = _CALL_TIMEOUT):
        """把零参 fn 投递到会话线程执行并等待结果:跨线程驱动页面的唯一入口。"""
        if self._closed.is_set():
            raise RuntimeError("session closed")
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._calls.put((fn, fut))
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError as e:
            raise TimeoutError("session call timeout") from e

    def stop(self) -> None:
        # 只设标志位,由会话线程自己关浏览器(跨线程碰 playwright 对象会 greenlet error)
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    # ── 会话线程内部 ──
    def _frame_b64(self, page) -> str:
        """预览帧直发 CDP captureScreenshot(不带 captureBeyondViewport)。
        playwright 的 page.screenshot 对可滚动页面强制走 beyond-viewport 路径
        (captureBeyondViewport: !fitsViewport),有头窗口每次捕获都把渲染面临时
        扩到内容全高再复位 —— 用户看到 600ms 一次的持续抖动;
        CDP 纯读当前可见表面,零视觉扰动。只允许在会话线程调用。"""
        cdp = self._cdp.get(page)
        if cdp is None:
            cdp = page.context.new_cdp_session(page)
            self._cdp[page] = cdp
        try:
            return cdp.send("Page.captureScreenshot",
                            {"format": "jpeg", "quality": 55})["data"]
        except Exception:  # 页面已关闭/会话失效:弃缓存重建一次
            self._cdp.pop(page, None)
            cdp = page.context.new_cdp_session(page)
            self._cdp[page] = cdp
            return cdp.send("Page.captureScreenshot",
                            {"format": "jpeg", "quality": 55})["data"]

    def _drain_calls(self) -> None:
        """执行外部线程投递的调用(目标页在调用内部经 _current_page_obj 解析)。"""
        while True:
            try:
                fn, fut = self._calls.get_nowait()
            except queue.Empty:
                return
            try:
                fut.set_result(fn())
            except Exception as e:  # 调用本身的异常(定位超时等)原样送回调用方
                fut.set_exception(e)

    def _fail_pending_calls(self) -> None:
        """会话结束前把还没执行到的调用置错,避免调用方等到超时。"""
        while True:
            try:
                _, fut = self._calls.get_nowait()
            except queue.Empty:
                return
            if not fut.done():
                try:
                    fut.set_exception(RuntimeError("session closed"))
                except Exception:
                    pass

    def _run(self, headless, start_url, storage_state, on_raw, on_frame, on_close,
             with_toolbar):
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=headless)
                # storage_state 是 context 级参数(登录态),不是 launch 参数
                context = browser.new_context(
                    **({"storage_state": storage_state} if storage_state else {}))
                self._context = context
                context.add_init_script(COLLECT_JS)
                if with_toolbar:
                    context.add_init_script(TOOLBAR_JS)

                def report(source, ev):  # 页面 JS → Python(binding 回调)
                    ev = dict(ev)
                    ev["url"] = source["page"].url
                    on_raw(ev)

                context.expose_binding("__tcReport", report)

                def on_navigated(frame):
                    # 页面跳转由 Python 侧 framenavigated 合成为 goto(比 JS 可靠)
                    if frame is frame.page.main_frame and frame.url != "about:blank":
                        on_raw({"kind": "goto", "url": frame.url})

                def on_page(page):  # 新开标签页自动挂跳转监听
                    page.on("framenavigated", on_navigated)

                context.on("page", on_page)
                first = context.new_page()
                first.on("framenavigated", on_navigated)
                if start_url:
                    first.goto(start_url, wait_until="domcontentloaded")
                self._ready.set()

                next_frame = 0.0
                while not self._stop.is_set():
                    pages = context.pages
                    if not pages:
                        break  # 所有页面被用户直接关窗
                    self._drain_calls()
                    now = time.monotonic()
                    if now >= next_frame:
                        next_frame = now + _FRAME_INTERVAL
                        if self._capture_frames:
                            for dead in [p for p in self._cdp if p not in pages]:
                                self._cdp.pop(dead, None)  # 关掉的标签页弃缓存
                            try:  # 帧同样只能在会话线程取
                                on_frame(self._frame_b64(pages[-1]))
                            except Exception:
                                pass  # 导航中截图可能失败,跳过这一帧即可
                    try:
                        # 协议级等待:期间持续派发事件;纯 time.sleep 派发不了任何事件
                        pages[-1].wait_for_timeout(_PUMP_MS)
                    except Exception:
                        pass  # 页面恰好在等待中被关闭/跳转,下一轮循环自会感知
                browser.close()
        finally:
            self._fail_pending_calls()
            self._closed.set()
            on_close()

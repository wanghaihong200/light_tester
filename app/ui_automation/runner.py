# app/ui_automation/runner.py
"""执行器:DSL 步骤 → Playwright 调用。阻塞执行,配合后台线程使用。
设计要点:①全局 RUN_SLOT 并发=1;②每步「高亮→截图→执行」预览帧带元素高亮;
③context.pages[-1] 作为当前页实现多标签页跟随;④截图按步落盘供历史回看。
实现说明:Playwright 的 sync API 是 greenlet 绑定创建线程的,心跳帧线程跨线程
调 page.screenshot() 会报 greenlet error。因此这里用 async API 跑在执行线程
自己的事件循环上(asyncio.run),驱动调用与心跳帧同循环,预览帧才能不断供。"""
import asyncio
import base64
import contextlib
import threading
import time
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal
from app.models import UiRun
from app.ui_automation import dsl

RUN_SLOT = threading.Lock()
_FRAME_INTERVAL = 0.6  # 心跳帧间隔秒


def _notify_bus(run_id: int, event: dict) -> None:
    """线程内回调 → 主循环 bus 投递(无订阅者/无主循环时 no-op)。"""
    from app.jobs.bus import bus
    from app.ui_automation.loopref import ui_loop
    loop = ui_loop()
    if loop is not None:
        asyncio.run_coroutine_threadsafe(bus.publish(run_id, event), loop)


def _current_page(context, fallback):
    """多标签页跟随:总是取最近打开的标签页;context 尚无页面时回退到首屏。"""
    return context.pages[-1] if context.pages else fallback


def _single(page, c: dict):
    """单个定位候选 → Playwright 定位器(css 为默认策略)。"""
    s = c["strategy"]
    if s == "test_id": return page.get_by_test_id(c["value"])
    if s == "role": return page.get_by_role(c["role"], name=c.get("name"))
    if s == "placeholder": return page.get_by_placeholder(c["value"])
    if s == "label": return page.get_by_label(c["value"])
    if s == "text": return page.get_by_text(c["value"])
    return page.locator(c["value"])


async def _locate(page, loc: dict):
    """按 primary→fallbacks 顺序找第一个命中的定位器;全未命中返回 primary(让超时报错)。"""
    cands = dsl.raw_locator_candidates(loc)
    primary = _single(page, cands[0])
    for c in cands:
        loc_obj = _single(page, c)
        if await loc_obj.count() > 0:
            return loc_obj.first
    return primary.first


async def _highlight(page, loc: dict | None) -> None:
    """给目标元素加红框(预览高亮);失败静默(定位本就可能未命中)。"""
    if loc is None:
        return
    try:
        el = await _locate(page, loc)
        await el.evaluate(
            "el => { el.__tcOutline = el.style.outline; el.style.outline = '3px solid red'; }")
    except Exception:
        pass


async def _unhighlight(page, loc: dict | None) -> None:
    if loc is None:
        return
    try:
        el = await _locate(page, loc)
        await el.evaluate("el => { el.style.outline = el.__tcOutline || ''; }")
    except Exception:
        pass


async def _shot_b64(page) -> str:
    """截图直发 CDP captureScreenshot(不带 captureBeyondViewport)。
    playwright 截图对可滚动页强制走 beyond-viewport 路径,有头执行窗口每次
    捕获可见地膨胀-复位(抖动);CDP 纯读当前可见表面,零视觉扰动。"""
    cdp = await page.context.new_cdp_session(page)
    try:
        return (await cdp.send("Page.captureScreenshot",
                               {"format": "jpeg", "quality": 55}))["data"]
    finally:
        await cdp.detach()


async def _shot_bytes(page) -> bytes:
    return base64.b64decode(await _shot_b64(page))


async def _run_step(page, step: dict, variables: dict) -> tuple[str, str | None]:
    """执行单步。返回 ("passed"|"failed", 错误信息)。所有 Playwright 调用集中在此。"""
    a = step["action"]
    # 字符串参数统一过一遍变量渲染;非字符串原样保留
    p = {k: dsl.render_text(v, variables) if isinstance(v, str) else v
         for k, v in (step.get("params") or {}).items()}
    try:
        if a == "goto":
            await page.goto(p["url"], wait_until="domcontentloaded")
        elif a == "wait":
            # asyncio.sleep 而非 time.sleep:等待期间心跳帧照常推
            await asyncio.sleep(min(p["ms"], 30_000) / 1000)
        elif a == "set_var":
            variables[p["name"]] = p["value"]
        else:
            loc = step["locator"]
            el = await _locate(page, loc)
            if a == "click": await el.click()
            elif a == "fill": await el.fill(p["text"])
            elif a == "press": await el.press(p["key"])
            elif a == "select_option": await el.select_option(p["value"])
            elif a == "assert_visible":
                if not await el.is_visible(): return "failed", f"元素不可见: {loc}"
            elif a == "assert_exists":
                if await el.count() == 0: return "failed", f"元素不存在: {loc}"
            elif a == "assert_text":
                actual = await el.inner_text()
                want = p["text"]
                ok = (want == actual.strip()) if p.get("mode", "contains") == "equals" else (want in actual)
                if not ok:
                    return "failed", f"文本不匹配: 期望[{want}] 实际[{actual.strip()[:120]}]"
        return "passed", None
    except Exception as e:  # Playwright 超时/导航失败等都归为步骤失败
        return "failed", str(e).split("\n")[0][:300]


def _persist(run_id: int, *, status: str, results: list, total: int,
             passed: int, failed: int, error: str | None) -> None:
    """把一次 run 的结果落库(短会话,避免跨线程长持连接)。"""
    db = SessionLocal()
    try:
        r = db.get(UiRun, run_id)
        if r is None:
            return
        r.status, r.step_results = status, results
        r.steps_total, r.steps_passed, r.steps_failed = total, passed, failed
        r.started_at = r.started_at or datetime.now()
        if status in ("completed", "failed"):
            r.finished_at = datetime.now()
        r.error = error
        db.commit()
    finally:
        db.close()


def _persist_env_failure(run_id: int, error: str) -> None:
    """环境级错误兜底:只在 run 尚未终态时改写,避免覆盖已有步骤结果。"""
    db = SessionLocal()
    try:
        r = db.get(UiRun, run_id)
        if r is None or r.status in ("completed", "failed"):
            return
        r.status, r.error = "failed", error
        r.started_at = r.started_at or datetime.now()
        r.finished_at = datetime.now()
        db.commit()
    finally:
        db.close()


async def _frame_loop(context, page, results: list, notify) -> None:
    """心跳帧:跑动期间持续推当前页截图(含步骤执行中)。截图失败跳过该帧。"""
    while True:
        try:
            cur = _current_page(context, page)
            notify({"type": "frame", "data": await _shot_b64(cur), "step_index": len(results)})
        except Exception:
            pass  # 导航中截图可能失败,跳过这一帧即可
        await asyncio.sleep(_FRAME_INTERVAL)


async def _execute(run_id: int, script_doc: dict, *, mode: str, variables: dict,
                   auth_state_path: str | None, data_dir: Path, notify) -> None:
    from playwright.async_api import async_playwright

    steps = script_doc.get("steps") or []
    run_dir = Path(data_dir) / "runs" / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    passed = failed = 0
    t0 = time.monotonic()
    env_error: str | None = None

    def persist(status: str) -> None:
        _persist(run_id, status=status, results=results, total=len(steps),
                 passed=passed, failed=failed, error=env_error)

    try:
        persist("running")
        notify({"type": "step_start", "index": -1})  # 首帧占位:浏览器尚未就绪
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=mode == "headless")
            # storage_state 是 context 级参数(登录态),不是 launch 参数
            context = await browser.new_context(storage_state=auth_state_path)
            if context.pages:
                page = context.pages[0]
            else:
                page = await context.new_page()
            heartbeat = asyncio.create_task(_frame_loop(context, page, results, notify))
            try:
                for i, step in enumerate(steps):
                    notify({"type": "step_start", "index": i})
                    cur = _current_page(context, page)
                    await _highlight(cur, step.get("locator"))
                    notify({"type": "frame", "data": await _shot_b64(cur), "step_index": i})
                    st, err = await _run_step(cur, step, variables)
                    await _unhighlight(cur, step.get("locator"))
                    shot_name = f"step_{i}_{st}.jpg"
                    (run_dir / shot_name).write_bytes(await _shot_bytes(cur))
                    results.append({"index": i, "step_id": step["id"], "action": step["action"],
                                    "status": st, "error": err, "screenshot": shot_name,
                                    "elapsed_ms": int((time.monotonic() - t0) * 1000)})
                    if st == "passed":
                        passed += 1
                    else:
                        failed += 1
                        notify({"type": "step_end", "index": i, "status": st, "error": err,
                                "screenshot": shot_name})
                        persist("failed")  # fail-fast:断言失败即终止(重试策略二期)
                        notify({"type": "done", "status": "failed",
                                "summary": {"total": len(steps), "passed": passed, "failed": failed,
                                            "duration_ms": int((time.monotonic() - t0) * 1000)}})
                        return
                    notify({"type": "step_end", "index": i, "status": st, "error": None,
                            "screenshot": shot_name})
                persist("completed")
                notify({"type": "done", "status": "completed",
                        "summary": {"total": len(steps), "passed": passed, "failed": 0,
                                    "duration_ms": int((time.monotonic() - t0) * 1000)}})
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
                await browser.close()
    except Exception as e:  # 环境级错误(浏览器起不来等)
        env_error = str(e)[:500]
        persist("failed")
        notify({"type": "error", "message": env_error})


def execute_script(run_id: int, script_doc: dict, *, mode: str, variables: dict,
                   auth_state_path: str | None, data_dir: Path, notify) -> None:
    """阻塞跑完一个 run 并落库。调用方负责 RUN_SLOT 与线程。notify 在本线程被调用。"""
    try:
        asyncio.run(_execute(run_id, script_doc, mode=mode, variables=variables,
                             auth_state_path=auth_state_path,
                             data_dir=Path(data_dir), notify=notify))
    except Exception as e:  # _execute 兜底之外的异常(事件循环建不起来等)
        err = str(e)[:500]
        _persist_env_failure(run_id, err)
        notify({"type": "error", "message": err})

# app/ui_automation/loopref.py
"""主事件循环引用:runner 线程用它把事件投递回 asyncio 侧的 bus。"""
import asyncio

_loop: asyncio.AbstractEventLoop | None = None


def set_ui_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def ui_loop() -> asyncio.AbstractEventLoop | None:
    return _loop

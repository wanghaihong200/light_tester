import asyncio
import json

import pytest

from app.jobs.bus import JobEventBus


@pytest.mark.asyncio
async def test_bus_publish_reaches_subscriber_and_drops_when_empty():
    b = JobEventBus()
    q = b.subscribe(1)
    await b.publish(1, {"type": "delta", "text": "a"})
    await b.publish(1, {"type": "done", "staged_count": 3})
    assert q.get_nowait() == {"type": "delta", "text": "a"}
    assert q.get_nowait() == {"type": "done", "staged_count": 3}
    b.unsubscribe(1, q)
    await b.publish(1, {"type": "delta", "text": "dropped"})  # 无人订阅,不抛
    assert q.empty()


@pytest.mark.asyncio
async def test_bus_publish_sync_safe():
    b = JobEventBus()
    q = b.subscribe(2)
    b.publish_nowait(2, {"type": "status", "status": "running"})
    assert q.get_nowait()["status"] == "running"

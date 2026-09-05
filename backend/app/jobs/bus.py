"""进程内任务事件总线:SSE 端点订阅,管道发布。单进程 uvicorn 下安全。"""

import asyncio


class JobEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue]] = {}

    def subscribe(self, job_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: int, q: asyncio.Queue) -> None:
        queues = self._subscribers.get(job_id, [])
        if q in queues:
            queues.remove(q)
        if not queues:
            self._subscribers.pop(job_id, None)

    def publish_nowait(self, job_id: int, event: dict) -> None:
        for q in self._subscribers.get(job_id, []):
            q.put_nowait(event)

    async def publish(self, job_id: int, event: dict) -> None:
        self.publish_nowait(job_id, event)


bus = JobEventBus()

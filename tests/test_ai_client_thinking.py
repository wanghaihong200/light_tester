"""计划6:AI client 事件级流——thinking_delta/text_delta 分流,usage 保持,请求带 thinking 参数。"""
from types import SimpleNamespace as NS

import app.ai.client as client


def _fake_events(*pairs):
    """构造 content_block_delta 假事件:("thinking", s) → thinking_delta;("text", s) → text_delta。"""
    events = []
    for kind, s in pairs:
        if kind == "thinking":
            events.append(NS(type="content_block_delta", delta=NS(type="thinking_delta", thinking=s)))
        else:
            events.append(NS(type="content_block_delta", delta=NS(type="text_delta", text=s)))
    return events


class _FakeStream:
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _agen(self):
        for e in self._events:
            yield e

    def __aiter__(self):
        return self._agen()

    async def get_final_message(self):
        return NS(usage=NS(input_tokens=11, output_tokens=22))


async def test_case_stream_splits_thinking_and_text(monkeypatch):
    captured = {}

    def fake_stream_call(**params):
        captured.update(params)
        return _FakeStream(_fake_events(("thinking", "先分析需求…"), ("text", '{"feature_points":'), ("thinking", "再拆步骤…"), ("text", "[]}")))

    monkeypatch.setattr(client, "_stream_call", fake_stream_call)
    out = [item async for item in client.stream_case_generation("p", "m", "doc")]

    assert out == [
        ("thinking", "先分析需求…"),
        ("delta", '{"feature_points":'),
        ("thinking", "再拆步骤…"),
        ("delta", "[]}"),
        ("usage", (11, 22)),
    ]
    assert captured["thinking"] == {"type": "adaptive", "display": "summarized"}


async def test_api_stream_splits_thinking_and_text(monkeypatch):
    monkeypatch.setattr(client, "_stream_call", lambda **params: _FakeStream(_fake_events(("thinking", "设计测试类…"), ("text", '{"files": []}'))))
    out = [item async for item in client.stream_api_generation("p", "m", "doc", {})]
    assert out == [("thinking", "设计测试类…"), ("delta", '{"files": []}'), ("usage", (11, 22))]

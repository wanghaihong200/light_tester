"""测试 AI 客户端:成本估算、Schema 形状、流式生成元组协议。

全部测试以替身注入 _stream_call,零网络调用。
"""

from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.client import (
    CASE_JSON_SCHEMA,
    PRICING,
    _stream_call,
    estimate_cost,
    stream_case_generation,
)
from app.ai.prompts import CASE_SYSTEM_PROMPT
from app.config import settings


class FakeCtx:
    """模拟 AsyncAnthropic 流式上下文。"""

    def __init__(self, chunks: list[str], input_tokens: int, output_tokens: int):
        self.chunks = chunks
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.captured_kwargs: dict[str, Any] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def _text_stream(self):
        for chunk in self.chunks:
            yield chunk

    @property
    def text_stream(self):
        return self._text_stream()

    async def get_final_message(self):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="".join(self.chunks))],
            usage=SimpleNamespace(
                input_tokens=self.input_tokens, output_tokens=self.output_tokens
            ),
        )


def test_estimate_cost():
    """测试成本估算公式。"""
    assert estimate_cost("claude-opus-5", 1_000_000, 1_000_000) == pytest.approx(30.0)
    assert estimate_cost("claude-sonnet-5", 1_000_000, 1_000_000) == pytest.approx(18.0)
    assert estimate_cost("unknown-model", 1_000_000, 0) == pytest.approx(5.0)


def test_case_json_schema_shape():
    """测试 CASE_JSON_SCHEMA 形状约束。"""
    assert CASE_JSON_SCHEMA["type"] == "object"
    properties = CASE_JSON_SCHEMA["properties"]
    assert "feature_points" in properties
    fp = properties["feature_points"]["items"]
    assert "cases" in fp["properties"]
    cases_items = fp["properties"]["cases"]["items"]
    assert "priority" in cases_items["properties"]
    assert cases_items["properties"]["priority"]["enum"] == ["P0", "P1", "P2"]
    assert CASE_JSON_SCHEMA["additionalProperties"] is False


@pytest.mark.asyncio
async def test_stream_case_generation_yields_deltas_and_schema_passed():
    """测试流式生成输出元组协议(delta/usage)及参数透传。"""
    chunks = ['{"feature_points":', ' []}']
    fake_ctx = FakeCtx(chunks=chunks, input_tokens=100, output_tokens=50)
    captured_kwargs = {}

    def fake_stream_call(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_ctx

    # Monkeypatch _stream_call
    import app.ai.client as client_module

    original_stream_call = client_module._stream_call
    client_module._stream_call = fake_stream_call

    try:
        results = []
        async for item in stream_case_generation("商城", "登录模块", "# 需求"):
            results.append(item)

        assert results == [
            ("delta", '{"feature_points":'),
            ("delta", ' []}'),
            ("usage", (100, 50)),
        ]

        # 验证参数透传
        assert captured_kwargs["model"] == settings.ai_model
        assert captured_kwargs["system"] == CASE_SYSTEM_PROMPT
        assert captured_kwargs["output_config"] == {
            "format": {"type": "json_schema", "schema": CASE_JSON_SCHEMA}
        }
        assert captured_kwargs["max_tokens"] == 64000
    finally:
        client_module._stream_call = original_stream_call

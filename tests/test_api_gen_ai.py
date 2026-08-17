# tests/test_api_gen_ai.py
import pytest

from app.ai import client, prompts


class _FakeStream:
    def __init__(self, text: str, in_tok: int, out_tok: int):
        self._text = text
        self._in = in_tok
        self._out = out_tok

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def text_stream(self):
        class _It:
            def __init__(self, chunks):
                self._chunks = chunks

            def __aiter__(self):
                self._i = 0
                return self

            async def __anext__(self):
                if self._i >= len(self._chunks):
                    raise StopAsyncIteration
                c = self._chunks[self._i]
                self._i += 1
                return c

        return _It(self._text.splitlines(keepends=True))

    async def get_final_message(self):
        class _U:
            input_tokens = self._in
            output_tokens = self._out

        class _M:
            usage = _U()

        return _M()


def test_api_files_json_schema_shape():
    s = client.API_FILES_JSON_SCHEMA
    assert s["type"] == "object"
    assert s["properties"]["files"]["type"] == "array"
    item = s["properties"]["files"]["items"]
    assert "path" in item["properties"]
    assert "content" in item["properties"]


def test_build_api_gen_user_prompt_includes_summary_and_doc():
    p = prompts.build_api_gen_user_prompt("电商系统", "订单模块", "## 订单 API\nPOST /orders", {
        "group_id": "com.example",
        "artifact_id": "order-api",
        "has_rest_assured": True,
        "has_junit5": True,
        "test_packages": ["com.example.api"],
        "has_base_class": False,
    })
    assert "订单模块" in p
    assert "POST /orders" in p
    assert "com.example" in p


@pytest.mark.asyncio
async def test_stream_api_generation_yields_delta_and_usage(monkeypatch):
    fake = _FakeStream('{"files":[{"path":"src/test/java/T.java","content":"class T{}"}]}', 100, 200)
    monkeypatch.setattr(client, "_stream_call", lambda **kw: fake)
    out = []
    async for kind, value in client.stream_api_generation("p", "m", "doc", {"group_id": "g", "artifact_id": "a", "has_rest_assured": True, "has_junit5": True, "test_packages": [], "has_base_class": False}):
        out.append((kind, value))
    kinds = [k for k, _ in out]
    assert "delta" in kinds
    assert kinds[-1] == "usage"
    assert out[-1][1] == (100, 200)

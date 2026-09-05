"""生成引擎:选项构建守卫(纯构造,零子进程零网络)。"""

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import StreamEvent

from app.ai.engine import (
    API_FILES_JSON_SCHEMA,
    CASE_JSON_SCHEMA,
    DISALLOWED_TOOLS,
    build_generation_options,
)


def test_options_guardrails():
    opts = build_generation_options("functional-testing", "claude-opus-5", CASE_JSON_SCHEMA, api_key="k-1")
    # 禁落盘与禁外发(ADR-0005 守卫)
    assert "Write" in opts.disallowed_tools and "Edit" in opts.disallowed_tools
    assert "WebFetch" in opts.disallowed_tools and "WebSearch" in opts.disallowed_tools
    assert "NotebookEdit" in opts.disallowed_tools
    assert DISALLOWED_TOOLS == ["Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"]
    # 放行只读探索与受限命令
    assert opts.allowed_tools == ["Read", "Glob", "Grep", "Bash"]
    # 未预批工具一律拒绝,无交互挂起
    assert opts.permission_mode == "dontAsk"
    # 只发现仓库级平台技能(不加载用户全局技能)
    assert opts.setting_sources == ["project"]
    assert opts.skills == ["functional-testing"]
    assert opts.cwd is not None and opts.cwd.name == "backend"
    # 结构化输出契约随会话下发(SDK 终态校验)
    assert opts.output_format == {"type": "json_schema", "schema": CASE_JSON_SCHEMA}
    # 思考摘要可得(计划 6 语义延续)+ 流式增量
    assert opts.thinking == {"type": "adaptive", "display": "summarized"}
    assert opts.include_partial_messages is True
    # 熔断
    assert opts.max_turns == 40 and opts.max_budget_usd == 2.0
    # 密钥显式传子进程 env,不依赖 os.environ
    assert opts.env == {"ANTHROPIC_API_KEY": "k-1"}


def test_options_model_add_dirs_and_empty_key():
    opts = build_generation_options(
        "api-test-restassure", "claude-sonnet-5", API_FILES_JSON_SCHEMA,
        api_key="", add_dirs=["D:/repo/wc"],
    )
    assert opts.model == "claude-sonnet-5"
    assert opts.add_dirs == ["D:/repo/wc"]  # 统一转 str 传入
    assert opts.env == {}  # 空密钥不注入


def test_json_schemas_shape():
    assert CASE_JSON_SCHEMA["properties"]["feature_points"]["items"]["properties"]["cases"] is not None
    item = API_FILES_JSON_SCHEMA["properties"]["files"]["items"]
    assert "path" in item["properties"] and "content" in item["properties"]


def _stream_event(delta_type: str, payload: dict) -> StreamEvent:
    return StreamEvent(uuid="u1", session_id="s1", event={
        "type": "content_block_delta", "delta": {"type": delta_type, **payload}
    })


async def _collect(monkeypatch, messages):
    import app.ai.engine as eng

    async def fake_query(prompt, options):
        for m in messages:
            yield m

    monkeypatch.setattr(eng, "_run_query", fake_query)
    return [
        item
        async for item in eng.stream_skill_generation(
            "提示词", "functional-testing", eng.CASE_JSON_SCHEMA
        )
    ]


def _result(**kw):
    base = dict(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
        num_turns=1, session_id="s1",
        total_cost_usd=0.0, usage={"input_tokens": 0, "output_tokens": 0},
    )
    base.update(kw)
    return ResultMessage(**base)


async def test_stream_translates_sdk_messages(monkeypatch):
    result = _result(
        total_cost_usd=0.42,
        usage={"input_tokens": 100, "output_tokens": 50},
        structured_output={"feature_points": []},
    )
    out = await _collect(monkeypatch, [
        _stream_event("thinking_delta", {"thinking": "思考片段"}),
        _stream_event("text_delta", {"text": "叙述片段"}),
        AssistantMessage(
            content=[
                ToolUseBlock(id="t1", name="Read", input={"file_path": "SKILL.md"}),
                ToolUseBlock(id="t2", name="Bash", input={"command": "mvn -q test-compile"}),
                TextBlock(text="完整消息文本"),  # 已由 delta 覆盖,不重复产出
            ],
            model="claude-opus-5",
        ),
        result,
    ])
    assert out == [
        ("thinking", "思考片段"),
        ("delta", "叙述片段"),
        ("tool", "Read SKILL.md"),
        ("tool", "Bash mvn -q test-compile"),
        ("usage", (100, 50, 0.42)),
        ("result", {"feature_points": []}),
    ]


async def test_stream_error_result_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="error_max_turns"):
        await _collect(monkeypatch, [
            _result(subtype="error_max_turns", is_error=True, num_turns=40, errors=["Hit max turns"])
        ])


async def test_stream_success_without_structured_output(monkeypatch):
    """success 但无结构化产物 → 只产 usage,由管道走解析兜底。"""
    out = await _collect(monkeypatch, [
        _result(total_cost_usd=0.01, usage={"input_tokens": 10, "output_tokens": 5},
                structured_output=None)
    ])
    assert out == [("usage", (10, 5, 0.01))]


def test_summarize_tool_input_truncates():
    from app.ai.engine import _summarize_tool_input
    assert _summarize_tool_input("Read", {"file_path": "a" * 500}) == "Read " + "a" * 200
    assert _summarize_tool_input("Skill", {"skill": "functional-testing"}) == "Skill functional-testing"
    assert _summarize_tool_input("Glob", {"unknown": 1}) == "Glob"

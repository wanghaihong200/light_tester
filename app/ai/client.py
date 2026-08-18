"""AI 生成客户端:AsyncAnthropic 流式 + JSON Schema 结构化输出。

_stream_call 是模块级薄封装,便于测试替换(monkeypatch)而不触网。
"""

from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from app.ai.prompts import (
    API_GEN_SYSTEM_PROMPT,
    CASE_SYSTEM_PROMPT,
    build_api_gen_user_prompt,
    build_user_prompt,
)
from app.config import settings

_client = AsyncAnthropic()  # 从 env ANTHROPIC_API_KEY 解析

CASE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feature_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "功能点名称,简洁中文短语"},
                    "cases": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
                                "precondition": {"type": ["string", "null"]},
                                "remark": {"type": ["string", "null"]},
                                "steps": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "action": {"type": "string"},
                                            "expected": {"type": "string"},
                                        },
                                        "required": ["action", "expected"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["title", "priority", "steps"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "cases"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["feature_points"],
    "additionalProperties": False,
}

# USD / 每百万 token:(input, output);未列出的模型按 opus 价兜底
PRICING = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (3.0, 15.0)}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICING.get(model, (5.0, 25.0))
    return input_tokens / 1_000_000 * in_price + output_tokens / 1_000_000 * out_price


def _stream_call(**params: Any):
    return _client.messages.stream(**params)


async def stream_case_generation(
    project_name: str, module_name: str, doc_content: str
) -> AsyncIterator[tuple[str, Any]]:
    params = dict(
        model=settings.ai_model,
        max_tokens=64000,
        # opus-5 默认已在思考且按 output 计费;display=summarized 把已付费思考变为可读摘要(计划6)
        thinking={"type": "adaptive", "display": "summarized"},
        system=CASE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(project_name, module_name, doc_content)}],
        output_config={"format": {"type": "json_schema", "schema": CASE_JSON_SCHEMA}},
    )
    async with _stream_call(**params) as stream:
        async for event in stream:
            if event.type != "content_block_delta":
                continue
            if event.delta.type == "thinking_delta":
                yield ("thinking", event.delta.thinking)
            elif event.delta.type == "text_delta":
                yield ("delta", event.delta.text)
        final = await stream.get_final_message()
        yield ("usage", (final.usage.input_tokens, final.usage.output_tokens))


API_FILES_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "pattern": r"^src/test/(java|resources)/.+$"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["files"],
    "additionalProperties": False,
}


async def stream_api_generation(
    project_name: str, module_name: str, doc_content: str, project_summary: dict
) -> AsyncIterator[tuple[str, Any]]:
    params = dict(
        model=settings.ai_model,
        max_tokens=64000,
        thinking={"type": "adaptive", "display": "summarized"},
        system=API_GEN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_api_gen_user_prompt(project_name, module_name, doc_content, project_summary)}],
        output_config={"format": {"type": "json_schema", "schema": API_FILES_JSON_SCHEMA}},
    )
    async with _stream_call(**params) as stream:
        async for event in stream:
            if event.type != "content_block_delta":
                continue
            if event.delta.type == "thinking_delta":
                yield ("thinking", event.delta.thinking)
            elif event.delta.type == "text_delta":
                yield ("delta", event.delta.text)
        final = await stream.get_final_message()
        yield ("usage", (final.usage.input_tokens, final.usage.output_tokens))

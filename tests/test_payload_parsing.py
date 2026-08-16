"""解析健壮性:端点不强制结构化输出时的防御(markdown 围栏/顶层数组归一化)。

背景:GLM 中转等 Anthropic 兼容端点会静默丢弃 output_config,模型可能输出
带 ```json 围栏的自由 JSON 或顶层数组 —— 解析层负责归一化后再交 pydantic 校验。
"""

import pytest
from pydantic import ValidationError

from app.jobs.pipeline import _parse_staged_payload

VALID = '{"feature_points": [{"name": "登录", "cases": [{"title": "成功", "priority": "P0", "steps": [{"action": "输入", "expected": "成功"}]}]}]}'
ARRAY_FORM = '[{"name": "登录", "cases": [{"title": "成功", "priority": "P1", "steps": []}]}]'


def test_parse_plain_object():
    payload = _parse_staged_payload(VALID)
    assert payload.feature_points[0].name == "登录"


def test_parse_strips_code_fence_with_json_label():
    payload = _parse_staged_payload(f"```json\n{VALID}\n```")
    assert payload.feature_points[0].cases[0].priority == "P0"


def test_parse_strips_bare_code_fence():
    payload = _parse_staged_payload(f"```\n{VALID}\n```")
    assert payload.feature_points[0].name == "登录"


def test_parse_normalizes_top_level_array():
    """端点未强制 schema 时模型常见输出:feature_points 数组直接做根节点。"""
    payload = _parse_staged_payload(ARRAY_FORM)
    assert payload.feature_points[0].name == "登录"
    assert payload.feature_points[0].cases[0].steps == []


def test_parse_normalizes_fenced_array():
    payload = _parse_staged_payload(f"```json\n{ARRAY_FORM}\n```")
    assert payload.feature_points[0].cases[0].title == "成功"


def test_parse_rejects_garbage():
    with pytest.raises(ValidationError):
        _parse_staged_payload('{"totally": "wrong"}')
    with pytest.raises(Exception):
        _parse_staged_payload("not json at all")

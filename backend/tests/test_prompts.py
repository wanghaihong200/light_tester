# tests/test_prompts.py
"""补充提示词构建器:动态上下文 + 技能调度指令。"""
from app.ai.prompts import (
    SKILL_API_NAME,
    SKILL_CASE_NAME,
    build_api_gen_user_prompt,
    build_user_prompt,
)


def test_case_prompt_embeds_supplementary_and_skill():
    p = build_user_prompt("商城", "登录", "# 需求", "只测登录")
    assert "# 项目:商城" in p and "# 目标模块:登录" in p
    assert "# 需求文档" in p and "# 需求" in p
    assert "# 补充指令" in p and "只测登录" in p
    assert SKILL_CASE_NAME in p


def test_case_prompt_without_supplementary():
    p = build_user_prompt("商城", "登录", "# 需求")
    assert "# 补充指令" not in p
    assert "# 补充指令" not in build_user_prompt("商城", "登录", "# 需求", "   ")


def test_api_prompt_embeds_summary_supplementary_and_skill():
    p = build_api_gen_user_prompt("商城", "登录", "# API", {"group_id": "com.x"}, "优先 P0 接口")
    assert "com.x" in p and "# 补充指令" in p and "优先 P0 接口" in p
    assert SKILL_API_NAME in p

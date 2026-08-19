"""平台技能副本:安装位置与输出契约改写的守卫测试。

原件(C:\\Users\\王海虹\\.claude\\skills\\)不受影响——本测试只读仓库内副本。
"""
import pytest

from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[1] / ".claude" / "skills"


def _read(*parts: str) -> str:
    return SKILLS_ROOT.joinpath(*parts).read_text(encoding="utf-8")


@pytest.mark.skip_database
def test_skill_copies_installed():
    assert (SKILLS_ROOT / "functional-testing" / "SKILL.md").is_file()
    assert (SKILLS_ROOT / "api-test-restassure" / "SKILL.md").is_file()
    # 按需加载资源随副本安装(引擎按 SKILL.md 指令查阅)
    for skill in ("functional-testing", "api-test-restassure"):
        assert (SKILLS_ROOT / skill / "prompts").is_dir()
        assert (SKILLS_ROOT / skill / "references").is_dir()
        assert (SKILLS_ROOT / skill / "examples").is_dir()
        assert (SKILLS_ROOT / skill / "scripts").is_dir()


@pytest.mark.skip_database
def test_functional_copy_output_is_platform_json_contract():
    prompt = _read("functional-testing", "prompts", "functional-testing.md")
    assert '"feature_points"' in prompt
    assert "平台 JSON 契约" in prompt
    # 原「六节 Markdown 报告」输出节必须已被替换
    assert "### 1. 任务理解" not in prompt
    # 旧系统提示词方法论并入(优先级定义/去重)
    assert "P0=" in prompt and "去重" in prompt
    skill_md = _read("functional-testing", "SKILL.md")
    assert "默认 Markdown" not in skill_md


@pytest.mark.skip_database
def test_restassure_copy_output_is_platform_json_contract():
    prompt = _read("api-test-restassure", "prompts", "api-test-restassure.md")
    assert '"files"' in prompt
    assert "平台 JSON 契约" in prompt
    assert "### 1. 任务理解" not in prompt
    # 原「不要贴超长 Java 全文」必须反转(平台要完整文件)
    assert "不要贴超长" not in prompt
    assert "完整文件源码" in prompt
    skill_md = _read("api-test-restassure", "SKILL.md")
    assert "默认 Markdown" not in skill_md

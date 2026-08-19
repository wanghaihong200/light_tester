"""生成引擎:claude-agent-sdk 会话适配层。

以平台技能为方法论驱动一次生成会话;选项构建把守卫(禁落盘/禁外发)、
技能发现(仅项目级)与结构化输出契约固化在一处。
_run_query 是模块级薄封装,便于测试替换(monkeypatch)而不启动真子进程。
"""

from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions

from app.config import settings

# 引擎 cwd=后端仓库根:平台技能安装在 <backend>/.claude/skills/ 下,
# Read/Glob/Grep/Bash 的默认探索面即后端仓库;接口生成额外 add_dirs 挂 working copy
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# 守卫(ADR-0005):禁落盘(Write/Edit/NotebookEdit)、禁外发(WebFetch/WebSearch);
# 放行 Read/Glob/Grep/Bash;其余工具由 dontAsk 一律拒绝(无交互挂起)
DISALLOWED_TOOLS = ["Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"]
ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Bash"]

MAX_TURNS = 40
MAX_BUDGET_USD = 2.0

SKILL_CASE = "functional-testing"
SKILL_API = "api-test-restassure"

# 平台 JSON 契约(自 app/ai/client.py 迁移;Skill 副本的输出节与之一致)
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


def build_generation_options(
    skill_name: str,
    model: str,
    output_schema: dict[str, Any],
    api_key: str | None = None,
    add_dirs: list[str | Path] | None = None,
) -> ClaudeAgentOptions:
    key = api_key if api_key is not None else (settings.anthropic_api_key or "")
    env: dict[str, str] = {"ANTHROPIC_API_KEY": key} if key else {}
    return ClaudeAgentOptions(
        cwd=_BACKEND_ROOT,
        setting_sources=["project"],  # 只发现仓库级平台技能,不加载用户全局技能
        skills=[skill_name],
        allowed_tools=list(ALLOWED_TOOLS),
        disallowed_tools=list(DISALLOWED_TOOLS),
        permission_mode="dontAsk",
        model=model,
        thinking={"type": "adaptive", "display": "summarized"},
        include_partial_messages=True,
        output_format={"type": "json_schema", "schema": output_schema},
        max_turns=MAX_TURNS,
        max_budget_usd=MAX_BUDGET_USD,
        env=env,
        add_dirs=[str(p) for p in (add_dirs or [])],
    )

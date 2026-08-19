"""生成引擎:选项构建守卫(纯构造,零子进程零网络)。"""

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

"""AI 生成用户提示词构建:动态上下文 + 补充指令 + 技能调度指令(方法论事实源在平台技能副本)。"""

SKILL_CASE_NAME = "functional-testing"
SKILL_API_NAME = "api-test-restassure"


def build_user_prompt(project_name: str, module_name: str, doc_content: str, supplementary_prompt: str | None = None) -> str:
    parts = [
        f"# 项目:{project_name}\n# 目标模块:{module_name}\n",
        f"# 需求文档\n\n{doc_content}",
    ]
    if supplementary_prompt and supplementary_prompt.strip():
        parts.append(f"\n# 补充指令\n\n{supplementary_prompt.strip()}")
    parts.append(
        f"\n请调用 {SKILL_CASE_NAME} 技能,按技能内方法论为上述需求文档的目标模块设计功能测试用例;"
        "方法论与输出要求以技能内文件为准,产物按技能的平台 JSON 契约给出。"
    )
    return "\n".join(parts)


def build_api_gen_user_prompt(project_name: str, module_name: str, doc_content: str, project_summary: dict, supplementary_prompt: str | None = None) -> str:
    parts = [
        f"# 项目:{project_name}\n# 目标模块:{module_name}\n",
        f"""## 工程概要
- groupId: {project_summary.get('group_id') or '(未提供,用 com.example.api)'}
- artifactId: {project_summary.get('artifact_id') or '(未提供)'}
- 依赖已含:rest-assured={project_summary.get('has_rest_assured')}, junit5={project_summary.get('has_junit5')}, hamcrest={project_summary.get('has_hamcrest', False)}
- 已有测试包: {project_summary.get('test_packages') or '(无,新建)'}
- 已有 Base 类: {project_summary.get('has_base_class')}
- 自动化工程 working copy 已挂载为附加目录:可只读探索 pom.xml 与 src/test 结构

## API 文档
{doc_content}""",
    ]
    if supplementary_prompt and supplementary_prompt.strip():
        parts.append(f"\n# 补充指令\n\n{supplementary_prompt.strip()}")
    parts.append(
        f"\n请调用 {SKILL_API_NAME} 技能,按技能内方法论生成 REST Assured 测试类文件;"
        "产物按技能的平台 JSON 契约给出。"
    )
    return "\n".join(parts)

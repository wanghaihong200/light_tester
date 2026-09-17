"""计划 16 Task 4:job 命名/checkout URL 改写/config.xml 组装。"""
import defusedxml.minidom

from app.cicd.jenkins_job import PIPELINE_SCRIPT, build_job_config, job_name, rewrite_gitlab_url


def test_job_name():
    assert job_name(12, "ui") == "light_tester_p12_ui"
    assert job_name(3, "api") == "light_tester_p3_api"


def test_rewrite_gitlab_url():
    exp = "http://host.docker.internal:8090"
    assert rewrite_gitlab_url("http://localhost:8090/haihai/a.git", exp) == f"{exp}/haihai/a.git"
    assert rewrite_gitlab_url("http://127.0.0.1:8090/x/y.git", exp) == f"{exp}/x/y.git"
    # 非本机地址(公网/file)原样
    assert rewrite_gitlab_url("https://github.com/a/b.git", exp) == "https://github.com/a/b.git"
    assert rewrite_gitlab_url("file:///d:/x/origin.git", exp) == "file:///d:/x/origin.git"
    # 暴露地址未配(空/非法)时原样返回,不炸
    assert rewrite_gitlab_url("http://localhost:8090/a.git", "") == "http://localhost:8090/a.git"


def test_pipeline_script_has_both_agents_and_post():
    assert "mcr.microsoft.com/playwright/python" in PIPELINE_SCRIPT
    assert "maven:3.9-eclipse-temurin-8" in PIPELINE_SCRIPT
    assert "surefire-reports" in PIPELINE_SCRIPT and "ci-results" in PIPELINE_SCRIPT


def test_build_job_config_escapes_xml():
    xml = build_job_config('echo "<a & b>"')
    assert xml.startswith("<?xml")
    assert "&lt;a &amp; b&gt;" in xml  # script 已转义,config 仍是合法 XML
    assert 'class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition"' in xml


def test_build_job_config_is_parameterized():
    """真 Jenkins 陷阱:buildWithParameters 只认 config.xml properties 里的参数定义,
    脚本内 parameters {} 指令要等首次构建才回写 job 属性——REST 刚建的 job
    立即触发会 400 "not parameterized"(2026-09-17 冒烟缺陷)。"""
    doc = defusedxml.minidom.parseString(build_job_config("echo hi"))
    assert len(doc.getElementsByTagName("hudson.model.ParametersDefinitionProperty")) == 1
    params = doc.getElementsByTagName("hudson.model.StringParameterDefinition")
    names = [p.getElementsByTagName("name")[0].firstChild.data for p in params]
    assert names == ["REPO_URL", "BRANCH", "KIND", "SELECTION", "CREDENTIALS_ID"]
    defaults = {p.getElementsByTagName("name")[0].firstChild.data:
                (p.getElementsByTagName("defaultValue")[0].firstChild.data
                 if p.getElementsByTagName("defaultValue")[0].firstChild else "")
                for p in params}
    assert defaults["BRANCH"] == "master" and defaults["KIND"] == "ui"
    assert defaults["CREDENTIALS_ID"] == "gitlab-creds"
    assert defaults["REPO_URL"] == "" and defaults["SELECTION"] == ""


def test_pipeline_checkout_runs_on_builtin():
    """alpine/git 镜像 ENTRYPOINT=[git] 会吞 docker-workflow 的保活 cat(变成 git cat 秒退,
    docker top 报 container not running)——checkout 改在 built-in 节点跑(控制器自带 git)。
    2026-09-17 冒烟缺陷。"""
    assert "alpine/git" not in PIPELINE_SCRIPT
    assert "agent { label 'built-in' }" in PIPELINE_SCRIPT


def test_pipeline_agent_cache_volumes():
    """docker agent 容器每次构建环境全新:maven 空 ~/.m2 全量重下依赖、pip 重装 pytest——
    挂命名卷跨 build 复用缓存(2026-09-17 冒烟用户拍板)。"""
    assert "args '-v light-tester-m2:/root/.m2'" in PIPELINE_SCRIPT
    assert "args '-v light-tester-pip:/root/.cache/pip'" in PIPELINE_SCRIPT


def test_pipeline_script_has_no_parameters_directive():
    """参数定义单一来源=config.xml properties;脚本内 parameters {} 指令会造成双源漂移。"""
    assert "parameters {" not in PIPELINE_SCRIPT
    assert "params.KIND" in PIPELINE_SCRIPT  # 脚本仍消费参数,只是不再声明

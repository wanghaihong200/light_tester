"""计划 16 Task 4:job 命名/checkout URL 改写/config.xml 组装。"""
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

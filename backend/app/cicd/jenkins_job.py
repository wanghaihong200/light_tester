"""Jenkins job 侧产物:命名规则、checkout 地址改写、常量流水线脚本与 config.xml 组装。

pipeline 采用「常量脚本 + build 参数」:平台侧所有可变物(仓地址/分支/选择集合/凭据 ID)
都经 buildWithParameters 传入,job 模板本身零分支逻辑,平台升级不需要重写已存在的 job。
"""
from urllib.parse import urlparse, urlunparse
from xml.sax.saxutils import escape

JOB_PREFIX = "light_tester"

PIPELINE_SCRIPT = """pipeline {
  agent none
  options { timestamps() }
  parameters {
    string(name: 'REPO_URL', defaultValue: '', description: '自动化仓地址(Jenkins 容器视角)')
    string(name: 'BRANCH', defaultValue: 'master', description: '分支')
    string(name: 'KIND', defaultValue: 'ui', description: 'ui/api')
    string(name: 'SELECTION', defaultValue: '', description: 'ui=空格分隔 pytest 文件;api=逗号分隔 类#方法')
    string(name: 'CREDENTIALS_ID', defaultValue: 'gitlab-creds', description: 'GitLab 凭据 ID')
  }
  stages {
    stage('checkout') {
      agent { docker { image 'alpine/git:2.45.2' } }
      steps {
        checkout([$class: 'GitSCM',
          branches: [[name: "${params.BRANCH}"]],
          userRemoteConfigs: [[url: "${params.REPO_URL}", credentialsId: "${params.CREDENTIALS_ID}"]]])
      }
    }
    stage('run-ui') {
      when {
        beforeAgent true
        equals expected: 'ui', actual: params.KIND
      }
      agent { docker { image 'mcr.microsoft.com/playwright/python:v1.60.0-jammy' } }
      steps {
        sh 'python -m pip install -q pytest'
        sh 'python -m pytest ${SELECTION} --junitxml=ci-results/junit.xml -q'
      }
      post {
        always {
          junit allowEmptyResults: true, testResults: 'ci-results/*.xml'
          archiveArtifacts allowEmptyArchive: true, artifacts: 'ci-results/*.xml'
        }
      }
    }
    stage('run-api') {
      when {
        beforeAgent true
        equals expected: 'api', actual: params.KIND
      }
      agent { docker { image 'maven:3.9-eclipse-temurin-8' } }
      steps {
        sh 'mvn -B -q test -Dtest="${SELECTION}" -DfailIfNoTests=false'
      }
      post {
        always {
          junit allowEmptyResults: true, testResults: '**/surefire-reports/*.xml'
          archiveArtifacts allowEmptyArchive: true, artifacts: '**/surefire-reports/*.xml'
        }
      }
    }
  }
}
"""


def job_name(project_id: int, kind: str) -> str:
    return f"{JOB_PREFIX}_p{project_id}_{kind}"


def rewrite_gitlab_url(repo_url: str, exposed_base: str) -> str:
    """仓 remote 存的是宿主机视角地址(localhost:8090),Jenkins 容器内不可达;
    仅当 host 为本机回环时按「GitLab 对 Jenkins 暴露地址」改写 scheme+netloc,路径原样。"""
    src = urlparse(repo_url)
    if (src.hostname or "").lower() not in ("localhost", "127.0.0.1"):
        return repo_url
    exp = urlparse(exposed_base)
    if not exp.scheme or not exp.netloc:
        return repo_url
    return urlunparse((exp.scheme, exp.netloc, src.path, "", "", ""))


def build_job_config(pipeline_script: str) -> str:
    return (
        "<?xml version='1.1' encoding='UTF-8'?>\n"
        '<flow-definition plugin="workflow-job">\n'
        "  <description>created by light_tester (CI/CD module)</description>\n"
        "  <keepDependencies>false</keepDependencies>\n"
        '  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps">\n'
        f"    <script>{escape(pipeline_script)}</script>\n"
        "    <sandbox>true</sandbox>\n"
        "  </definition>\n"
        "  <triggers/>\n"
        "  <disabled>false</disabled>\n"
        "</flow-definition>"
    )

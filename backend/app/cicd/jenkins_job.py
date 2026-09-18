"""Jenkins job 侧产物:命名规则、checkout 地址改写、常量流水线脚本与 config.xml 组装。

pipeline 采用「常量脚本 + build 参数」:平台侧所有可变物(仓地址/分支/选择集合/凭据 ID)
都经 buildWithParameters 传入,job 模板本身零分支逻辑,平台升级不需要重写已存在的 job。
"""
from urllib.parse import urlparse, urlunparse
from xml.sax.saxutils import escape

JOB_PREFIX = "light_tester"

# 参数定义单一来源(config.xml properties):buildWithParameters 只认 job 属性,
# 脚本内 parameters {} 指令要等首次构建才回写,REST 刚建的 job 立即触发会 400。
JOB_PARAMETERS = [
    ("REPO_URL", "自动化仓地址(Jenkins 容器视角)", ""),
    ("BRANCH", "分支", "master"),
    ("KIND", "ui/api", "ui"),
    ("SELECTION", "ui=空格分隔 pytest nodeid(文件::函数);api=逗号分隔 类#方法", ""),
    ("CREDENTIALS_ID", "GitLab 凭据 ID", "gitlab-creds"),
]

PIPELINE_SCRIPT = """pipeline {
  agent none
  options { timestamps() }
  stages {
    stage('checkout') {
      // built-in 节点自带 git;勿用带 ENTRYPOINT 的 git 客户端镜像——会吞 docker agent 的保活 cat,容器秒退
      agent { label 'built-in' }
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
      agent {
        docker {
          image 'mcr.microsoft.com/playwright/python:v1.60.0-jammy'
          // LIGHT_HOST=宿主机地址:测试配置用 ${LIGHT_HOST:localhost} 占位,容器内可打宿主机服务
          args '-e LIGHT_HOST=host.docker.internal -v light-tester-pip:/root/.cache/pip'
        }
      }
      steps {
        // 镜像 v1.60.0-jammy 的 Python 环境为裸(仅浏览器二进制,2026-09-18 冒烟实测):
        // playwright 钉 1.60 与镜像浏览器(chromium-1223)配套,pytest-playwright <0.8 为框架约束;
        // 工程依赖仓自包含(vendor/*.whl)按需装,无 vendor 的导出物仓跳过不失败。
        sh 'python -m pip install -q "playwright==1.60.*" "pytest-playwright>=0.5,<0.8" pytest'
        sh '[ -d vendor ] && python -m pip install -q vendor/*.whl || echo "no vendor deps, skip"'
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
      agent {
        docker {
          image 'maven:3.9-eclipse-temurin-8'
          // LIGHT_HOST=宿主机地址:测试配置用 ${LIGHT_HOST:localhost} 占位,容器内可打宿主机服务
          args '-e LIGHT_HOST=host.docker.internal -v light-tester-m2:/root/.m2'
        }
      }
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


def _parameters_xml() -> str:
    defs = []
    for name, desc, default in JOB_PARAMETERS:
        defs.append(
            "            <hudson.model.StringParameterDefinition>\n"
            f"              <name>{escape(name)}</name>\n"
            f"              <description>{escape(desc)}</description>\n"
            f"              <defaultValue>{escape(default)}</defaultValue>\n"
            "              <trim>false</trim>\n"
            "            </hudson.model.StringParameterDefinition>"
        )
    return (
        "  <properties>\n"
        "    <hudson.model.ParametersDefinitionProperty>\n"
        "      <parameterDefinitions>\n"
        + "\n".join(defs) + "\n"
        "      </parameterDefinitions>\n"
        "    </hudson.model.ParametersDefinitionProperty>\n"
        "  </properties>\n"
    )


def build_job_config(pipeline_script: str) -> str:
    return (
        "<?xml version='1.1' encoding='UTF-8'?>\n"
        '<flow-definition plugin="workflow-job">\n'
        "  <description>created by light_tester (CI/CD module)</description>\n"
        "  <keepDependencies>false</keepDependencies>\n"
        + _parameters_xml()
        + '  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps">\n'
        f"    <script>{escape(pipeline_script)}</script>\n"
        "    <sandbox>true</sandbox>\n"
        "  </definition>\n"
        "  <triggers/>\n"
        "  <disabled>false</disabled>\n"
        "</flow-definition>"
    )

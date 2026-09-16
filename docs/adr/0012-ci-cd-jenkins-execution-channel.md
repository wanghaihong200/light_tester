# 0012 - CI/CD 执行通道:Jenkins + 双 Docker Agent + 纯轮询集成

日期:2026-09-15 · 状态:accepted

平台已有三条进程内执行通道(UiRun/AppRun/GenerationJob),但 UI 与接口自动化的"批量回归执行"缺位:
物料已随 ADR-0004/计划 11 推进外部 Git 仓(Playwright pytest / RestAssured),缺的是"勾选一批用例、
在独立环境跑、日志直播、出报告"的执行域。本 ADR 以六决策引入**持续集成执行通道**(grilling 会话
2026-09-15 定案,Q1-Q21 全记录在案):

1. **Jenkins 为执行引擎,常驻参数化 pipeline job(每 项目×kind 一个)**:平台经 REST 按需自动创建
   (首次执行时查建),内联平台生成的 Jenkinsfile;一次执行 = 触发一次 build,分支/选择集合/ci_run_id
   走 build 参数。拒"每 run 建/删 job"(REST 往返多、垃圾窗口)与"每计划一个 job"(job 数失控,且把
   计划与 Jenkins 载体焊死)。
2. **双 Docker Agent 拓扑,controller 只编排**:UI 阶段跑 `mcr.microsoft.com/playwright/python:v1.60`
   (自带 Python+浏览器,版本与平台 playwright==1.60 锁死);api 阶段跑 `maven:3.9-eclipse-temurin-8`
   (用户接口栈为 Java 8 + TestNG,与 controller 的 OpenJDK 17 隔离,规避老 TestNG/Spring Boot 2.2 的
   兼容雷)。拒"定制 Jenkins 镜像补工具链"(动用户自建的 cicd-jenkins 镜像,版本对齐靠手工)——
   前提是 controller 挂有 docker.sock(已具备)。
3. **纯出站轮询集成,拒入站 webhook**:后端运行期 ~2s 轮 Jenkins(build 状态 + `progressiveText`
   增量日志),日志经现有 SSE 总线中继前端直播、同步落盘供回放;后端重启按 mock supervisor 先例
   对账收口。轮询同时解决完成感知,平台不开任何入站免鉴权通道,Jenkins 零插件依赖。
4. **执行计划 = 单类型 + 分支前置 + 选择集合快照**:计划绑定仓分支(建/编先选分支、再勾用例),
   批量触发各计划用各自分支;触发时快照进执行记录,计划事后编辑不溯及历史。接口用例为注册表实体
   (扫到方法级,按 仓×分支×类×方法 定位,各分支独立合并与 stale 判定),仓是唯一事实源、平台只存
   引用。**新鲜度检测只提示不阻塞**:工作区 vs 远端对应分支(未提交+ahead),可按老代码继续;
   定时执行(未来)不检测。
5. **报告自研,JUnit XML 一统**:UI 侧 pytest 内置 `--junitxml`,api 侧 surefire 原生产出,平台单
   解析器入 `ci_runs` 表,报告页按平台 run 详情风格渲染(汇总卡/用例方法表/console 日志面板/
   Jenkins 外链)。拒 Allure(数据不落库、趋势无从谈起、多养一条工具链)。
6. **范围边界**:与平台内执行通道(UiRun/AppRun)并列互不隶属;APP/多端不入域;v1 仅人工触发;
   物料同步全人工(不自动导出/推送)。stale/缺失统一语义:勾选项执行时已不存在→警告列出、可继续、
   报告标注。

## Considered Options

- Jenkins 完成后回调平台 webhook——拒:平台要为 Jenkins 开免 JWT 入站通道(新攻击面+一次性 token
  管理),而日志流式本就只能靠拉(Jenkins 不推增量),回调省不掉轮询,反而多养一条通道。
- 定制 cicd-jenkins 镜像预装 Python+Playwright——拒:镜像约 +2GB 且版本对齐靠人;docker agent 用
  官方镜像 tag 锁版本,Jenkins 本体零改动。
- Allure 报告(Jenkins 插件 + 平台代理/iframe)——拒:漂亮但外置,数据不落库,与平台自研报告形态
  割裂;JUnit XML 让 UI/api 两域共用一个解析器。
- 计划可混选 UI+接口用例——拒:一执行=多 build,聚合状态(部分成功算什么)复杂度前置;单类型
  1 ci_run=1 build 最薄,将来要混在记录层加聚合即可。
- 注册表不带分支维度(全局单表)——拒:切分支重扫互相覆盖,stale 判定跨分支串味;分支是勾选用例的
  前置语境,注册表必须分支语境化。

## Consequences

- 部署前置(用户一次性手工操作):Jenkins 生成 API token → 平台 admin 配置页(URL+token+连通测试
  +「GitLab 对 Jenkins 暴露地址」,默认 `host.docker.internal:8090`,checkout 地址据此改写——仓 remote
  存的是宿主机视角 `localhost:8090`,Jenkins 容器内不可达);Jenkins 手动配 GitLab 凭据(固定 ID,
  如 `gitlab-creds`),平台只引用不保管 PAT;实施时验证 docker-workflow 插件在位(312 插件,大概率有)。
- Jenkins 侧出现平台创建的常驻实体(job 命名 `light_tester_p{project_id}_{kind}`),在 Jenkins UI 删掉
  会在下次触发时被平台按需重建;并发触发放行进 Jenkins 原生排队,平台如实显示「排队中」。
- console 日志落盘 `data/ci/runs/{run_id}/console.log`,磁盘占用随执行次数线性增长,v1 无清理策略。
- 执行分支=工作区分支:批量跨分支触发逐计划 checkout+检测(工作区最终停在最后一个计划的分支),
  与导出/推送共享同一工作区状态,不引入第二套代码视图。

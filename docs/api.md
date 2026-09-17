# API 参考

> 后端全部 HTTP 端点。基础地址 `http://127.0.0.1:8000`;前端经 vite proxy 以相对路径 `/api/...` 访问。
> 交互式文档(Swagger)在 http://127.0.0.1:8000/docs ——本页是带语境的导读,Swagger 是精确参数校验。
> 数据流与 SSE 协议的图示见 [architecture.md](architecture.md)。

## 总约定

- **鉴权(计划 9 起)**:除 `GET /api/health` 与 `POST /api/auth/login` 外,**所有端点都要登录**——带
  `Authorization: Bearer <jwt>`(HS256,`jwt_exp_days`=7 天;无 refresh、无服务端吊销)。
  未带/无效 → `401 {"detail":"未登录或登录已过期"}`;账号已禁用 → `403 {"detail":"账号已禁用"}`。
  五个 SSE 端点(jobs / ui_runs / ui_recordings / app_runs / ci_runs 的 events)额外支持 `?token=` query(裸 EventSource 带不了自定义头)。
- **项目级权限**:owner / editor / viewer 三角色,admin 全局直通(任何项目按 owner 处理)。
  无成员关系的项目对非 admin **一律 404(不可见,不泄露存在性)**;已可见但角色不足 → `403 {"detail":"无项目操作权限"}`。
  各域最低角色见下方「角色矩阵」。
- 出参模型定义在 `app/schemas.py`(鉴权相关在 `schemas_auth.py`),与前端 `src/types.ts` 一一对应;本页只列常用字段。
- 常见错误:404 资源不存在/项目不可见;400 参数/归属校验失败(如 `invalid document_id`、`job not completed`);
  409 项目重名/用户名重名/末位 owner。错误体为 `{"detail": "..."}`。
- 删除语义(2026-09-05 核对):**物理删为主**——项目/模块/功能点/用例/文档/暂存用例/成员的 DELETE
  均直接删行(带内容删项目会 FK 1451 500,见项目节与 DEFER #70);**软删**(`is_deleted=True`)仅两处——
  UI 脚本(执行历史外键不断链)与登录态(连带删存储文件)。多张表虽带 `is_deleted` 列,但删除端点未走软删。

## 健康检查

`GET /api/health` → `{"status":"ok"}`(免登录)

## 鉴权 `/api/auth`(auth.py)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 登录 `{username, password}` → `{token, user}`(`user`= id/username/display_name/is_admin/is_active);账号或口令错 401 `用户名或密码错误`(同一文案,不区分哪个错);已禁用 403 `账号已禁用` |
| GET | `/api/auth/me` | 当前登录用户(Bearer)→ 同 `user` 结构;401 未登录/过期,403 已禁用 |

token 即 JWT(`sub`=user_id,HS256,7 天)。首次启动自动创建 admin/admin123,见 README「快速开始」。

## 用户管理 `/api/users`(users.py,**仅 admin**,非 admin 一律 403 `需要管理员权限`;唯一例外:`GET /api/users/search` 登录即可)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/users` | 用户列表(按 id 排序) |
| GET | `/api/users/search?q=&limit=` | **用户搜索(任何登录用户,免 admin)**——选人场景(项目成员弹窗)数据源;`q` 未传/纯空白直接返回 `[]`;对 username / display_name 做 LIKE 包含匹配(按 username 排序);响应仅 `{id, username, display_name}`(不带 is_admin/is_active 等管理字段);`limit` 默认 20,收敛到 1..50(上限 50) |
| GET | `/api/users/{user_id}/projects` | 某用户的项目授权列表(**admin only**);用户不存在 404 `user not found`;返回 `[{project_id, project_name, role}]`(按项目名排序)——用户管理页「项目权限」授权弹窗数据源;只读视图,写(添加/改角色/移除)仍走项目成员接口(admin 直通) |
| POST | `/api/users` | 建号 `{username, display_name, password, is_admin?}`(201;密码最短 6,不足 422;重名 409 `用户名已存在`) |
| PUT | `/api/users/{id}` | 改资料/重置密码/禁用 `{display_name?, password?, is_active?}`(字段可选,给了才改);操作自己的账号仅当 payload 带 `is_active` 时 409 `不能操作自己的账号`(防自断禁用),改显示名/重置自己密码放行 |

## 角色矩阵(各域最低角色;admin 直通)

| 域 | 读 | 写 / 删 | 执行 / 推送 |
|---|---|---|---|
| 项目 | viewer(列表只回可见项目;xmind/Excel 导出同) | 改=editor;删=owner | — |
| 用例树(模块/功能点/用例/执行勾选) | viewer | editor | — |
| 文档库 | viewer | 上传/下载/删=editor | — |
| 生成任务 | **详情/事件流/暂存区=editor**(列表 viewer 可见自己可见项目) | 发起/转正/拒绝=editor | — |
| 自动化工程 repo | 文件树/读文件/变更/分支/仓配置列表=viewer | sync=editor;仓配置保存=editor | push=editor |
| UI 脚本 | viewer | 改/删=editor | 导出推 web 仓=editor |
| UI 执行 | 历史/详情/截图=viewer | 发起/强制结束=editor;**执行事件流=editor** | — |
| UI 录制 | **实时步骤流=editor** | 发起/断言/停止/取消=editor | — |
| 登录态 | 列表=viewer | 采集/save/cancel/删=editor | — |
| APP 脚本 | viewer | 改/删=editor;导入(设备拉取/上传)=editor | 导出推 app 仓=editor |
| APP 设备 | 清单/perf 项=登录即可(设备无项目归属) | — | — |
| APP 执行 | 历史/详情/对比/perf 曲线=viewer | 发起/强制结束=editor;**执行事件流=editor** | — |
| 接口Mock | 实例/规则/命中读=viewer | 建/改/删/启停/排序/清空=editor | 服务面(实例端口)无鉴权(探活/关停须实例令牌) |
| 性能测试 | 记录/曲线/对比/趋势=viewer;设备历史列表=登录即可(设备无项目归属) | 删/导入=editor | — |
| 持续集成 CI/CD | 计划/接口用例注册表/执行记录读=viewer | 计划增删改/扫描=editor | 触发/停止/重跑=editor;Jenkins 连接三端点=**仅 admin** |
| 项目成员 | viewer | 增/改角色/移除=owner(末位 owner 不可动) | — |
| 用户管理 | admin(**例外**:search 端点登录即可) | admin | — |

## 项目成员 `/api/projects/{id}/members`(members.py)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{id}/members` | 成员列表(viewer 可读,join 出 username/display_name) |
| POST | `/api/projects/{id}/members` | 添加 `{username, role: owner\|editor\|viewer}`(201;用户不存在 404;已是成员 409 `已是项目成员`) |
| PUT | `/api/projects/{id}/members/{user_id}` | 改角色 `{role}`;降级末位 owner 409 `项目至少需要一名 owner` |
| DELETE | `/api/projects/{id}/members/{user_id}` | 移除(204);末位 owner 同 409 |

创建项目自动成为该项目 owner;存量项目(计划 9 前已建)归 admin。

## 项目 `/api/projects`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects` | 列表 |
| POST | `/api/projects` | 创建 `{name, description?, git_repo_url?, git_token?}`(201) |
| GET/PUT | `/api/projects/{id}` | 详情 / 更新(配 git_repo_url + git_token 走这里) |
| DELETE | `/api/projects/{id}` | 删除(仅**无内容**项目可删;带内容会 FK 1451 500,级联清理未做,见 DEFER #70) |
| GET | `/api/projects/{id}/export/xmind` | 下载 .xmind(数据库 → 导图文件) |
| GET | `/api/projects/{id}/export/excel` | 下载 .xlsx(概览/功能点/用例 3 sheet) |

```bash
curl -X POST http://127.0.0.1:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"商城","git_repo_url":"http://localhost:8090/haihai/rest-assured-smoke.git","git_token":"glpat-xxx"}'
```

> **git_repo_url / git_token 的存储位置(计划 11 起)**:请求体仍收这两个字段,但**不再落 Project 旧列**——
> 写透 `automation_repos` 表 kind=api 行(旧列停写保留,兼容历史数据);详情出参 `git_repo_url` 也是从该行读出
> (未配置 → null,不回退旧列)。仓配置的读改还可走自动化工程页的 automation-repos 端点(见下节)。

## 用例树 `/api`(modules.py / cases.py)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{id}/tree` | **整棵用例树**(模块嵌套 + 各模块 feature_points + cases 摘要),导图数据源 |
| POST | `/api/projects/{id}/modules` | 建模块 `{name, parent_id?}`(parent_id 空=顶层) |
| PUT | `/api/modules/{id}` | 改名/移动 `{name?, parent_id?}`(环状嵌套被拒) |
| DELETE | `/api/modules/{id}` | 删模块 |
| POST | `/api/modules/{id}/feature-points` | 建功能点 `{name}` |
| PUT/DELETE | `/api/feature-points/{id}` | 改/删功能点 |
| POST | `/api/feature-points/{id}/cases` | 建用例(201) |
| GET/PUT | `/api/cases/{id}` | 用例详情(含步骤)/ 更新(steps 整体替换) |
| PATCH | `/api/cases/{id}/execution` | 勾选执行结果 `{"executed_pass": true\|null}` |
| DELETE | `/api/cases/{id}` | 删用例 |

用例创建体(步骤为有序"操作+预期"对):

```json
{
  "title": "正确账号密码登录成功",
  "priority": "P0",
  "precondition": "账号已注册",
  "remark": null,
  "steps": [{"action": "输入正确账号密码,点登录", "expected": "跳转首页,右上角显示用户名"}]
}
```

`priority` 枚举 `P0/P1/P2`(P0=必测,P1=应测,P2=有空再测)。

## 文档库 `/api`(documents.py,仅 .md)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{id}/documents` | 列表 |
| POST | `/api/projects/{id}/documents` | **multipart** 上传 `file`(201,落 `data/uploads/`) |
| GET | `/api/documents/{id}/download` | 下载原文 |
| DELETE | `/api/documents/{id}` | 删除 |

```bash
curl -X POST http://127.0.0.1:8000/api/projects/1/documents \
  -F "file=@需求文档.md;type=text/markdown"
```

## 生成任务 `/api`(jobs.py)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/jobs` | 发起生成(201,立即返回任务) |
| GET | `/api/projects/{id}/jobs` | 任务列表 |
| GET | `/api/jobs/{id}` | 任务详情(含 user_prompt/tool_trace/output_text/thinking_text) |
| GET | `/api/jobs/{id}/events` | **SSE 事件流**(见下) |
| GET | `/api/jobs/{id}/staging` | 暂存区分组视图 |
| POST | `/api/jobs/{id}/staging/accept` | 勾选转正 `{"ids":[...]}`(job 须 completed) |
| DELETE | `/api/staged/{id}` | 拒绝单条暂存用例 |

发起生成请求体:

```json
{
  "document_id": 3,
  "target_module_id": 5,
  "target_module_name": null,
  "job_type": "case_generation",
  "user_prompt": "只生成登录相关功能点,优先异常场景"
}
```

- `job_type`:`case_generation`(用例→暂存区)/ `api_generation`(脚本→写 working copy;项目须已配有效**接口自动化仓**,即 automation-repos 的 kind=api 行,URL 限 http(s))
- 模块三选一:`target_module_id`(下拉选中)/ `target_module_name`(手输名,项目下同名顶层模块复用、无则新建)/ 都空(不挂模块)
- `user_prompt`:可选补充指令(≤2000 字),随任务持久化,可在详情回看

**SSE 事件流** `GET /api/jobs/{id}/events`(`text/event-stream`,每行 `data: {...}\n\n`;SSE 带鉴权:
`Authorization: Bearer` 或 `?token=` query——裸 EventSource 带不了头,前端统一走 query):
连接即收 `status`;任务运行中依次收 `thinking_delta` / `delta` / `tool` / `stage` → 终态 `done` 或 `error` 后关流;
任务已是终态时直接收一条**全量 `snapshot`**(output_text/thinking_text/tool_trace/tokens/files_count/staged_count)后关流——这是"关页面后再开详情还能完整回放"的机制。事件载荷明细见 [architecture.md](architecture.md) 的「SSE 事件协议」一节。

## 自动化工程 `/api/projects/{id}/repo`(repo.py,多仓:一项目 × kind(api/web/app)各一仓)

计划 11 起仓配置按**分类**存储在 `automation_repos` 表(一项目×kind 各一仓,分开推送):
`api`=接口自动化(java)、`web`=Web 自动化(Playwright 导出)、`app`=APP 自动化(Appium 导出,计划 12 起启用)。
全部既有端点新增 `?kind=`(**默认 `api`**,老前端零影响);kind 非法 → 400 `未知仓分类: x(必须是 api/web/app)`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/repo/automation-repos` | 仓配置列表(viewer 可读)→ `[{id, kind, repo_url, repo_token, updated_at}]`;`repo_token` **明文返回**(配置页回显用,已接受决策) |
| PUT | `/repo/automation-repos/{kind}` | 保存/更新仓配置 `{repo_url, repo_token?}`(editor+;upsert——已有该 kind 行则更新;URL 仅允许 http(s)/file,否则 400 `repo_url 必须是 http(s) 或 file 且 host 非空`;`repo_token` 缺省/空串=**清除** token;成功返回 `{id, kind, repo_url, repo_token}`) |
| POST | `/repo/sync?kind=` | clone 或 pull working copy;`{"branch": "dev"}` 可选(指定则先切分支);未配置该 kind 仓 → 400 `项目未配置 {kind} 自动化仓,请先在自动化工程页配置` |
| GET | `/repo/files?kind=` | 文件树;未配置该 kind 仓 → `{"needs_config": true}`;已配置未同步过 → `{"needs_sync": true}` |
| GET | `/repo/file?path=src/test/java/...&kind=` | 读单文件 `{path, content, language}` |
| GET | `/repo/changes?kind=` | 工作区变更 `{files: [{path, status: added\|modified\|deleted, tracked}]}` |
| GET | `/repo/branches?kind=` | 远程分支列表 |
| POST | `/repo/push?kind=` | 勾选推送 `{files, branch, commit_message?}` |

> 未配置该 kind 仓时的语义:`files` 返回 `{"needs_config": true}`(前端据此弹配置表单),**其余端点(sync/file/changes/branches/push)一律 400** `项目未配置 {kind} 自动化仓,请先在自动化工程页配置`。

推送护栏:推前强制 `git pull --rebase`,冲突即 409 中止;只提交勾选的文件集合;AI 历史产物(artifacts 里出现过的路径)允许被再生成覆盖,用户手写的已跟踪文件拒覆盖。

```bash
curl -X PUT http://127.0.0.1:8000/api/projects/1/repo/automation-repos/web \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"http://localhost:8090/haihai/web-smoke.git","repo_token":"glpat-xxx"}'
```

```bash
curl -X POST http://127.0.0.1:8000/api/projects/1/repo/push?kind=web \
  -H "Content-Type: application/json" \
  -d '{"files":["test_login.py","RUN.md"],"branch":"main"}'
```

## Web UI 自动化 `/api`(ui_scripts.py / ui_recordings.py / ui_runs.py / ui_auth_states.py)

Playwright 驱动的 Web 自动化:录制浏览器操作成 JSON 步骤 DSL → 平台内可视编辑 → headless 执行边跑边预览(截图流 + 步骤事件流)。DSL 结构与两条 SSE 流的事件协议见 [architecture.md](architecture.md) 的「UI 自动化」一节。

**脚本 CRUD**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/ui-scripts` | 新建 `{name, description?, script}`(201);`script` 为 DSL 文档 |
| GET | `/api/projects/{id}/ui-scripts` | 列表(软删不显) |
| GET/PUT | `/api/ui-scripts/{id}` | 详情 / 更新 |
| DELETE | `/api/ui-scripts/{id}` | 软删(执行历史外键不断链) |

**导出 Playwright 推仓**(计划 11;`driver_target` 服务端由 `script.meta.target` 派生,非法/缺省兜底 web)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/ui-scripts/{id}/export` | 把脚本翻译成 pytest+Playwright 并推送**该项目的 web 仓**:`{branch, commit_message?}` → 200 `{ok, branch, commit_short, pushed_files, files}`(`files` 为仓内相对路径清单:主文件 `test_<slug>.py` + `RUN.md`;脚本带登录态时另推 `auth_states/<登录态名>.json`);权限同推送——viewer 403、非成员 404、目标非 web 400 `仅 driver_target=web 的脚本可导出 Playwright(当前 {target})` |

- **翻译语义**:`{{变量}}` → 主文件顶部 `VARIABLES` 字典(含默认值,仓内改值即改行为,未定义变量保留占位符);`run_sub` 内联展开——被引脚本渲染成 `_sub_<slug>` 私有函数、调用点原位替换,**一次推送全量**(主文件+全部子脚本);`assert_text` 映射为 `to_have_text`/`to_contain_text`
- **校验失败 → 400 `{"detail":{"errors":[...]}}` 错误清单**(中文逐条列具体步骤/原因,**不产生任何推送**):含 ai 系动作(`ai_tap` 等)的步骤、`run_sub` 引用缺失/已软删/循环引用、`meta.auth_state_id` 指向的登录态不存在或 storage_state 文件缺失、导出路径越界/写盘失败
- **推送语义**同 `/repo/push?kind=web`(推前先 `git pull --rebase`,冲突 409);`RUN.md` 为仓内运行说明——`pip install pytest pytest-playwright` 后 `pytest` 即可跑,不依赖平台;附带登录态时经 `browser_context_args` fixture 注入 `storage_state`,免录登录

```bash
curl -X POST http://127.0.0.1:8000/api/ui-scripts/12/export \
  -H "Content-Type: application/json" \
  -d '{"branch":"main","commit_message":"导出登录脚本"}'
```

**录制会话**(弹出有头浏览器,注入采集 JS + 断言工具条)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/ui-recordings` | 发起录制 `{auth_state_id?}`(201 → `{recording_id}`);带登录态可免录登录步骤 |
| GET | `/api/ui-recordings/{rid}/events` | **SSE**(`text/event-stream`,鉴权同 jobs 事件流,Bearer 或 `?token=`;闸 **editor**——viewer 打开录制预览页 403):`action` / `frame` / `assert_candidate` / `stopped`;断线重连先补发已有步骤再续流,`stopped` 后关流 |
| POST | `/api/ui-recordings/{rid}/assert` | 断言模式点选元素后由前端回调 `{target, assert_type: assert_visible\|assert_text\|assert_exists, text?, mode?: equals\|contains}` → `{steps}` |
| POST | `/api/ui-recordings/{rid}/stop` | 停止并返回草稿 `{meta, variables, steps}`(存为 ui-scripts 即脚本) |
| POST | `/api/ui-recordings/{rid}/cancel` | 丢弃草稿(204) |

**执行**(headless 回放,默认;`mode:"headed"` 可切)

> `assert_text` 比较语义(2026-09-04 起):双方先空白归一化(连续空白/换行/制表坍缩为单个空格并去首尾,对齐 Playwright `text=` 语义),再按 `mode` 判等(`equals`)或包含(`contains`,未知 mode 兜底)。注意:期望文本**内部**的空白属于内容——「AI测试」匹配不了「AI 测试」;失败报错带模式标记: `文本不匹配(equals): 期望[..] 实际[..]`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/ui-runs` | 执行 `{script_id, mode?, variables?, auth_state_id?}`(201);脚本非法 400,已有执行在跑 409 |
| GET | `/api/projects/{id}/ui-runs?script_id=` | 执行历史(近 100 条,可按脚本过滤) |
| GET | `/api/ui-runs/{rid}` | 详情(status / step_results / steps_total / steps_passed / steps_failed / error) |
| GET | `/api/ui-runs/{rid}/events` | **SSE**(鉴权同上,Bearer 或 `?token=`;闸 editor):`status` / `frame`(带 step_index,前端叠元素红框高亮)/ `step_start` / `step_end`(passed\|failed + 失败截图文件名)/ `done`(汇总)/ `error`(环境级失败);已终态连上即收 `status`+`snapshot` 后关流 |
| GET | `/api/ui-runs/{rid}/screens/{name}` | 步骤截图 jpg(文件名白名单校验,防路径穿越) |

**登录态**(storage_state 采集与复用,让脚本免录登录)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/ui-auth-states/collect` | 发起采集 `{name}`(201 → `{collect_id}`);弹出浏览器,用户登录被测站 |
| POST | `/api/ui-auth-collect/{cid}/save` | 导出 storage_state 落盘并登记(201)。会话已坏(浏览器被关等)→ 409 须重新采集;导出或落库(mkdir/写盘/commit)失败 → 500 且**会话保留**,可直接重试 save |
| POST | `/api/ui-auth-collect/{cid}/cancel` | 丢弃采集(204) |
| GET | `/api/projects/{id}/ui-auth-states` | 列表(storage_path 不外泄) |
| DELETE | `/api/ui-auth-states/{aid}` | 软删并删除登录态文件(204) |

并发约束(全局):执行槽 `RUN_SLOT` 为进程内信号量,并发数=`run_slot_count` env(**默认 5**),占满返回 409
`执行槽已满(上限 N)`;录制**或**登录态采集会话同时 1 个(`INTERACTIVE_SLOT`),占用同样 409。
`script_id` / `auth_state_id` 均校验存在、未软删、属本项目,否则 400。

## APP 自动化 `/api`(app_scripts.py / app_runs.py)

SoloPi 驱动的 APP 自动化:真机录制导出 SoloPi 原生用例 JSON → 平台导入/编辑(**JSON 原样存储,唯一事实源**)→ USB 真机执行(前置/后置检查点 + CPU/FPS/Memory 性能采集 + 启动耗时)→ 分发批量与对比矩阵 → 翻译导出 Appium·pytest 推 app 仓。**执行/检查点/编排语义**由 SoloPi Harness CLI 托管,平台不插步骤中间(ADR-0008);DSL 结构详见 [architecture.md](architecture.md)。

**环境前提**(缺任一,执行/设备/导入端点会 400 或返回空):

- **Harness CLI 安装**:`cd backend && source .venv/Scripts/activate && bash scripts/setup-solopi.sh`(幂等:克隆 `alipay/SoloPi` 的 **Harness 分支**到仓外同级 `../SoloPi` 并 `pip install -e solopi-harness-cli`;末尾自动跑 doctor)。
- 验证:`python -m solopi_harness.solopi_ai --pretty doctor` 退出码 0(不通过按输出接设备/装 App)。
- **真机**:仅 **USB** 连接的 Android 真机(`adb` 在 PATH;`adb devices` 须为 device 态);装 **SoloPi App v1.0.2** 并在其设置里开启**无障碍服务**;录制导出的用例 JSON 落在设备 `/sdcard/Android/data/com.alipay.hulu/files/harness-import/`。
- 导出的 Appium 产物独立运行(不依赖平台)需 Appium server(uiautomator2)+ `pip install pytest appium-python-client`,见仓内 `RUN.md`。

**脚本 CRUD**(用例体 = SoloPi 原生 JSON;`app_package` 服务端由 `case.targetAppPackage` 派生,`name` 缺省取 `case.caseName` 或「未命名用例」)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/app-scripts` | 新建 `{name?, description?, case, allow_high_risk?}`(201,editor+) |
| GET | `/api/projects/{id}/app-scripts` | 列表(软删不显,id 倒序) |
| GET/PUT | `/api/app-scripts/{id}` | 详情 / 更新 `{name?, description?, case?, allow_high_risk?}`(case 给了才整体替换并重算 app_package);**404=不存在或已软删(不泄漏存在性),403=成员但角色不足** |
| DELETE | `/api/app-scripts/{id}` | 软删(204;执行历史外键不断链) |

- **用例校验(400 `用例不合法: …`,创建/更新/导入/执行同闸)**:顶层必填 `caseName`/`targetAppPackage`;顶层禁止导入器管理字段(`id`/`gmtCreate`/`gmtModify`/`selected`/`caseFingerprint`/`storePath`);`operationLog.steps` 非空;每步 `operationMethod.actionEnum` 必填;`IF`/`WHILE`/`CONTINUE`/`BREAK` 是录制运行时内部动作,一律拒;`operationParam` 参数值必须全为字符串;`ASSERT` 需 `assertMode`+`assertInputContent`。编辑器不提供 IF/WHILE 编排。
- **高危门(400)**:用例含 `CLEAR_DATA`/`KILL_PROCESS`/`JUMP_TO_PAGE` 且请求未带 `allow_high_risk: true` → 400 `用例含高危动作(CLEAR_DATA,…),需勾选「允许高危动作」确认`(显式确认后放行,执行时向 CLI 传 `--confirm-high-risk`)。

**导入双通道**(均为 editor;两条路终点都是建 app-script)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{id}/app-scripts/device-cases?serial=&dir=` | 列出设备上录制导出的用例 JSON 文件名 `[{file_name}]`(只列不拉);`dir` 缺省 harness-import 目录;设备读取失败 400 |
| POST | `/api/projects/{id}/app-scripts/import-device` | **设备拉取导入** `{serial, file_name, name?, allow_high_risk?}`(201):adb pull 单文件到平台 `data/app/imports/` 再解析;文件名白名单防路径穿越,拉取失败/非合法 JSON 均 400 |
| POST | `/api/projects/{id}/app-scripts/import-upload` | **文件上传导入**:multipart `file` + 表单 `name?`/`allow_high_risk?`(201);超 1MB → 400 `用例文件超过 1MB 上限`;非合法 JSON → 400 |

**设备与性能项**(登录即可读,设备无项目归属)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/app-devices` | `adb devices` → `[{serial, state}]`;**非 device 态行保留**(unauthorized 等,前端据此提示);adb 读取失败 400 |
| GET | `/api/app-devices/{serial}/perf-items` | perf 可采集项动态发现(perf-list)→ `{items:[...]}`(键名随设备/插件不同,服务端对 items/metrics/keys 防御取值);CLI 失败 400 |

**执行**(单设备与分发批量同端点:每设备一行 AppRun,多设备共享 `batch_id` UUID;执行管线 = 前置检查点 → case_import → perf_start → 回放(阻塞至终态)→ perf_stop/analyze → 启动耗时 → 后置检查点 → 终态落库)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/app-runs` | 发起 `{script_id, device_serials(1..10), perf_items?, pre_checks?, post_checks?, startup_time?, allow_high_risk?}` → 201 `[AppRunOut]`(每设备一行);editor |
| GET | `/api/projects/{id}/app-runs?script_id=&batch_id=` | 执行历史(近 100 条,可按脚本/批次过滤) |
| GET | `/api/app-runs/{id}` | 详情(status/run_state/results/check_results/perf_summary/startup_summary/error/起止时间) |
| GET | `/api/app-runs/{id}/events` | **SSE**(鉴权同 jobs 事件流,Bearer 或 `?token=`;闸 **editor**——实时流=写会话语义):连上先 `status`;运行中收 `status` / 终态 `done`(带 status/state)或环境级 `error`(带 message)后关流;**已终态连上即收 `status`+`snapshot`(status/run_state/error)后关流**;步骤级实时流不承诺 |
| POST | `/api/app-runs/{id}/force-finish` | 强制结束执行中的 run → 状态置 `cancelled`(editor);**协作式**——执行线程在阶段边界检测标志后退出,终态防覆盖保证不被回写翻回;已终态 400 `该执行已结束,无需强制结束` |
| GET | `/api/projects/{id}/app-runs/comparison?batch_id=` | 分发批量对比矩阵:`{batch_id, script_id, script_name, runs:[AppRunOut]}`(按设备序;执行/检查点/性能/启动一并返回,前端拼表);空批次 404 `batch not found` |
| GET | `/api/app-runs/{id}/perf-series` | perf 曲线数据 `{series:[{item, columns, rows}]}`(`runs/{id}/perf/*.csv`,utf-8-sig→GBK 依次尝试解码) |

- **状态词汇**:`pending → running → passed/failed/cancelled`(终态三值;`run_state` 是 CLI 侧终态快照,平台状态可能与它不一致——**后置检查点不满足时端上 passed、平台置 failed**,两态并呈)。
- **create 占用语义(占用即拒绝,不排队)**:每设备一把 per-device 锁 + 全局执行槽各占 1 个(**all-or-nothing**:任一设备忙 → 回滚已获取的锁并 409 `设备 {serial} 忙,请稍后重试`,另一台未被占用可立即再发;槽满 → 409 `执行槽已满(上限 5)`,上限=`run_slot_count` env 默认 5,与 Web UI 执行共用)。
- **create 校验闸(顺序)**:script 必须属本项目且未软删(400 `invalid script_id`)→ 用例校验/高危门(同脚本节)→ 检查点校验(400 `pre_checks 不合法: …`/`post_checks 不合法: …`;两种定义:`{"type":"element_exists","text"?/"resource_id"?/"description"?}` 至少一条件多条件 AND,或 `{"type":"text_contains","value"}`)→ `device_serials` 去重保序,重复 400 `设备列表有重复`。

**导出 Appium·pytest 推 app 仓**(对齐 ui-scripts export 语义)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/app-scripts/{id}/export` | 翻译 SoloPi JSON 为 Appium·pytest 产物并推送**该项目的 app 仓**:`{branch, commit_message?}` → 200 `{ok, branch, commit_short, pushed_files, files}`(`files` 为仓内相对路径清单:主文件 `test_<id>_<拼音slug>.py` + `RUN.md`);权限:先可见性(非成员 404)再 editor(viewer 403) |

- **翻译范围(最小可用集)**:`CLICK`/`LONG_CLICK`/`INPUT`/`CLICK_AND_INPUT`/`SLEEP`/`ASSERT`(字符串三模式 assert_accurate→`==`、assert_contain→`in`、assert_regular→`re.search`)/`LET`(写变量);定位 resourceId→`AppiumBy.ID`(短名自动补包名前缀)、text/description→`UiSelector()`、xpath→`AppiumBy.XPATH`;`${var}` → 仓内 `PARAMS` 字典(未定义变量保留占位符)。
- **校验失败 → 400 `{"detail":{"errors":[...]}}` 错误清单,不产生任何推送**:用例含不翻译动作(如 `GESTURE`/`ASSERT_TOAST`)→ 逐步骤号列 `步骤N: 动作 X 平台不翻译(支持范围: CLICK/LONG_CLICK/INPUT/CLICK_AND_INPUT/SLEEP/ASSERT/LET)`。
- **推送语义**同 `/repo/push?kind=app`:未配 app 仓 400 `项目未配置 app 自动化仓,请先在自动化工程页配置`;产物先写 working copy 再 `push_files`(只 add 给定路径);推前先 sync(同步失败不阻断,push 内 rebase 兜底),rebase 冲突 409 `{"stage":"rebase","error":…}`;无变更 400 `{"stage":"nothing_to_commit","error":"没有变更可提交"}`。

```bash
curl -X POST http://127.0.0.1:8000/api/projects/1/app-runs \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"script_id":12,"device_serials":["emulator-5554"],"perf_items":["cpu","fps"],"startup_time":true}'
```

```bash
curl -X POST http://127.0.0.1:8000/api/app-scripts/12/export \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"branch":"main","commit_message":"导出登录脚本"}'
```

## 接口Mock `/api`(mock.py)+ Mock 服务面(`mock_service/`,实例独立端口)

每项目可建多个 **HTTP Mock 服务实例**(「接口Mock ▸ HTTP Mock」页),每实例 = 独立 Python 子进程(同 venv)监听独立端口,按规则返回 mock 响应,供被测系统直连(ADR-0009;规则组与透传见 ADR-0011)。规则按「method / path」实体化为**规则组**(组承载路由,组内规则=条件+响应);每个规则组可开**透传**(组即"被 mock 的原始接口"):组内规则全不中时请求转发该组上游真实服务。管理面走 8000 主端口(要登录);**服务面(实例端口)无登录鉴权**——mock 本就是给被测系统裸调的,仅探活/关停两个内部端点须带实例令牌。

- **状态机**:`stopped / starting / running / error`(`desired` 存期望态);启动=起子进程后 5s 内探活,超时置 `error`+`error_message`;平台每 10s 巡检探活、重启后对账重启 `running` 实例;孤儿子进程双保险自退(父进程死亡监测 + 令牌关停兜底)。
- **端口**:创建时 `port` 不填则在 `mock_port_range`(env,默认 `9001-9499`)内自动分配;手填则保存前做库内查重 + 试绑预检(冲突 400 `端口 x 已被实例占用`/`端口 x 被外部进程占用`);running/starting 锁端口不可改(409);**软删实例的端口行仍预留**,不回收复用。
- **热更新**:子进程**每请求实时读库**——规则/默认响应的增删改、启停、排序保存即生效,无需重启实例。
- **匹配**:两级遍历取**第一条命中**——先按**组间序**遍历规则组,再按**组内序**遍历组内规则;组=HTTP 方法精确 + 路径精确或 `{var}` 模板段(同实例内唯一,重路 400),规则=条件行(query/header/body 按 JSONPath,等于|正则)+响应;组或规则停用即跳过(组停用整组跳过);全不中:路由命中的组若开了透传→原样转发**该组**上游(见「透传」),否则回实例默认响应(`default_status`/`default_body`);请求不匹配任何组路由→直接实例兜底。存量迁移保序:组序=旧全局扁平序的最小 `sort_order`,迁移前后行为等价——前提:同路由变体在旧全局序中连续、各组模板不重叠同一路径(现网存量已核实;ADR-0011)。
- **透传(ADR-0011;2026-09-13 验收调整由实例级移至组级)**:组级 `passthrough_enabled` + `upstream_base_url`(须以 `http://`/`https://` 开头;开透传必须填地址,400 校验建/改同源;PATCH 省略字段=沿用现值、显式 null 地址=未提供)。组内规则全不中时请求原样转发:请求剥 hop-by-hop 头、host/content-length 重算;**上游任何 HTTP 响应(含 4xx/5xx)照透**——真实依赖的 5xx 是被测系统要演练的现场;仅传输层失败(连接 5s/读 30s 超时、DNS、非法 URL)回落默认响应,命中记 `error=forward-failed`。转发客户端 `trust_env=False` 直连(不吃系统代理,防代理把上游不可达转成 502 响应骗过兜底判定)。响应侧 content-encoding 剔除(httpx 已透明解压)、set-cookie 多值保真;关开关即回纯 mock 语义。
- **响应**:状态码(100-599)/响应头/响应体;`enable_template` 开 Jinja2 模板(可引用路径变量/query/header/请求体 JSON);`delay_ms` 延迟;模拟超时(挂住不回,等客户端超时自断,命中记 `error=timeout-simulated`);实例级 CORS(`OPTIONS` 预检直接 204,不耗规则不记命中)。
- **命中记录**:每个业务请求落一条(方法/路径/请求头体/响应状态/**实收响应体 response_body**/耗时/**outcome 三态**:`matched` 命中|`fallback` 兜底|`forwarded` 透传),**每实例滚动保留 1000 条,请求/响应体截断 64KB**。
- **权限**:实例/规则组/规则/命中读=viewer,写(建/改/删/启停/排序/清空)=editor;非项目成员一律 404(不泄漏存在性)。

**实例**(editor 写 / viewer 读)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/mock-instances` | 建实例 `{name, description?, port?, cors_enabled?, default_status?, default_body?}`(201;`port` 空则范围内自动分配;名称空白 400;端口冲突 400) |
| GET | `/api/projects/{id}/mock-instances` | 实例列表(id 倒序,软删不显) |
| GET | `/api/mock-instances/{instance_id}` | 详情(`desired`/`status`/`error_message`/`port` 等;实例令牌不出网——仅平台内部用于探活/关停) |
| PUT | `/api/mock-instances/{instance_id}` | 更新 `{name?, description?, port?, cors_enabled?, default_status?, default_body?}`(字段给了才改;运行中改端口 409 `实例运行中不能修改端口,请先停止`) |
| DELETE | `/api/mock-instances/{instance_id}` | 删除(204,软删;running/starting 时 409 `先停止实例再删除`) |
| POST | `/api/mock-instances/{instance_id}/start` | 启动实例(起子进程探活;失败/超时置 `error`,响应仍 200 带 `status=error`) |
| POST | `/api/mock-instances/{instance_id}/stop` | 停止实例(令牌关停子进程) |

**规则组**(editor 写 / viewer 读;组承载 method+path,同实例内唯一;`method` 入参小写自动大写化落库)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/mock-instances/{instance_id}/rule-groups` | 建组 `{method, path_template, description?, enabled?, passthrough_enabled?, upstream_base_url?}`(201,排到组间序末位;方法不支持/路径模板不合法/同实例重路 400;透传校验:开透传必须填上游地址、地址须 http(s):// 开头 400) |
| GET | `/api/mock-instances/{instance_id}/rule-groups` | 组列表(组间序升序=匹配序;每行内嵌 `rules` 按组内序) |
| PUT | `/api/mock-rule-groups/{group_id}` | 更新(字段给了才改;method/path_template 不接受 null 与空串 400,给了才整体查重;`description` 显式 null=清空;透传两字段省略=沿用现值、显式 null 地址=未提供,校验同建组) |
| DELETE | `/api/mock-rule-groups/{group_id}` | 删除(204,软删;**组亡规则亡**——组下规则连软删,历史命中 rule_id 仍可追溯) |
| PUT | `/api/mock-instances/{instance_id}/rule-groups/reorder` | 调组间序 `{group_ids}`(**全量新序**——须恰为实例下全部未删组 id,缺/多/重复/跨实例 400) |
| PUT | `/api/mock-rule-groups/{group_id}/rules/reorder` | 调组内序 `{rule_ids}`(全量新序——须恰为该组下全部未删规则 id,缺/多/重复 400) |

**规则**(editor 写 / viewer 读;规则挂组只存条件+响应,method/path 由组承载)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/mock-instances/{instance_id}/rules` | 建规则 `{group_id, conditions?, enabled?, response_status?, response_headers?, response_body?, enable_template?, delay_ms?, timeout_enabled?, timeout_seconds?}`(201,排到**组内**末位;组不存在/已删 404,组不属于该实例 400) |
| GET | `/api/mock-instances/{instance_id}/rules` | 规则列表(平铺序=组间序→组内序) |
| PUT | `/api/mock-rules/{rule_id}` | 更新(字段给了才改;`group_id` 不应用——规则改挂组暂不支持,挪组=删了重建) |
| DELETE | `/api/mock-rules/{rule_id}` | 删除(204,软删;历史命中的 rule_id 仍可追溯) |

**命中记录**(读=viewer;清空=editor)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/mock-instances/{instance_id}/hits?filter=&group_id=&limit=` | 命中列表(id 倒序;`filter`= `all\|matched\|unmatched\|forwarded` 默认 all,非法 400——unmatched=兜底、forwarded=透传;`group_id`=按组预过滤:命中行按 rule_id 归组(含已删规则),未命中行按「method 相同+路径能被组模板匹配」归因,跨实例组 400;`limit` 默认 200、上限 1000) |
| GET | `/api/mock-hits/{hit_id}` | 命中详情(请求头/体、命中的规则与响应、delay/耗时/error、`outcome` 与实收 `response_body`) |
| DELETE | `/api/mock-instances/{instance_id}/hits` | 清空该实例全部命中(204;硬删,命中表唯一删除入口) |

**服务面**(子进程在实例端口上,`http://127.0.0.1:{port}`,**无登录鉴权**)

| 方法 | 路径 | 说明 |
|---|---|---|
| ANY | `/{任意路径}` | mock 匹配主入口(GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS 全收;每请求实时读库匹配+记命中;实例被删后 404) |
| GET | `/__mock_health__?token={实例令牌}` | 探活(令牌错/缺 403)——平台启动探活、10s 巡检、重启对账都用它 |
| POST | `/__mock_shutdown__?token={实例令牌}` | 关停子进程(令牌错/缺 403)——平台 stop 与孤儿清理用 |

```bash
# 建实例(管理面,要登录)
curl -X POST http://127.0.0.1:8000/api/projects/1/mock-instances \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"name":"订单mock"}'

# 被测系统直连服务面(无鉴权;假设分配到 9001)
curl http://127.0.0.1:9001/api/orders/1001
```

## 性能测试 `/api`(perf.py,计划 14 / ADR-0010)

APP 自动化采集的性能数据(CPU/FPS/Memory 等)统一收敛为**性能记录**(`perf_records` 表)——**展示视图层**:平台不做采集,只把已有数据汇聚成列表/曲线/对比/趋势四类视图(ADR-0010)。两类来源:`source=run` **引用行**(执行终态自动登记,数据仍读执行目录,**不复制**)与 `source=import` **副本**(设备端历史 preview 落盘 `data/app/perf_records/{id}/`)。数据事实源是文件系统 CSV;曲线解析复用 APP 执行域的 perf_csv(utf-8-sig→GBK 依次尝试)。

- **run 引用行**:执行终态 `passed/failed` 且执行目录有有效 perf CSV(≥2 行数据)时幂等登记一行(名=`{脚本名}@{设备}`,快照 script_id/script_name/device_serial/perf_items/perf_summary/起止时间);`cancelled` 或无有效数据不登记。**删除 run 引用行只删记录行,不动执行目录**(执行历史里的 perf 曲线不受影响);import 删除则连落盘目录一起删。
- **数据完整性诚实标记**:import 走 SoloPi 历史接口 preview(硬边界:单文件 64KB/单次合计 512KB),超界 `filesTruncated=True` → 记录 `data_complete=false`(前端打「数据不完整」徽标);run 来源恒 `true`。
- **防重复导入**:`UniqueConstraint(source, source_ref)`,import 的 `source_ref`=设备端历史 id;run 的 `source_ref` 为 NULL(以 app_run_id 幂等)。
- **权限**:记录读/series/对比/趋势=viewer,删/导入=editor;设备历史列表**登录即可**(对齐 `/app-devices` 系既有口径,设备无项目归属)。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{id}/perf-records?source=&script_id=&device_serial=` | 记录列表(viewer;id 倒序,近 100 条;可按来源/脚本/设备过滤) |
| GET | `/api/perf-records/{record_id}` | 记录详情(PerfRecordOut:id/source/source_ref/name/app_run_id/script 快照/device_serial/perf_items/data_complete/perf_summary/起止时间) |
| DELETE | `/api/perf-records/{record_id}` | 删除(200 `{ok:true}`;editor;import 连落盘目录 / run 只删引用行,语义见上) |
| GET | `/api/perf-records/{record_id}/series` | 单记录曲线 `{record, series:[{item, columns, rows}]}`;run 来源读执行目录 `runs/{app_run_id}/perf`,import 读自己落盘目录 |
| POST | `/api/projects/{id}/perf-records/compare` | 跨记录对比(viewer)`{record_ids}`:2~10 条(越界 400)→ `{records, series}`(series 以记录 id 字符串为键);含非本项目/已删记录 404 |
| GET | `/api/projects/{id}/perf-trend?script_id=&device_serial=` | **趋势(仅 run 来源)**:按 `script_id+device_serial` 分组的时间序列 `{groups:[{script_id, script_name, device_serial, points:[{record_id, finished_at, series:{index:{mean,p90}}}]}]}`,按 finished_at 升序;**数据取 perf_summary 统计值,不碰 CSV**;import 记录与无脚本/无终态时间的记录不进趋势(共识既定) |
| GET | `/api/app-devices/{serial}/perf-history?limit=` | 设备端 SoloPi 性能历史列表(**登录即可**;`limit` 默认 50,收敛 1..500)→ `{items:[{id, start_time, end_time, file_count, size_bytes, metrics, imported_record_id}]}`;**已导入条目回填 `imported_record_id`**(前端防重复导入);CLI 失败 400 |
| POST | `/api/projects/{id}/perf-records/import` | 设备历史导入(editor)`{serial, history_id, name?}` → 201 PerfRecordOut:CLI 详情 → preview 逐文件落盘 → perf-analyze 统计;重复导入 409 `该设备历史已导入(perf 记录 #N)`;CLI 失败 400;preview 为空 400 `历史详情未含可落盘的 CSV 内容(preview 为空)` 且回滚刚建的行(不留空壳);统计失败不 500(perf_summary 记 error) |

```bash
curl -X POST http://127.0.0.1:8000/api/projects/1/perf-records/import \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"serial":"emulator-5554","history_id":"1718000000000","name":"冷启动基线"}'
```

## 持续集成(CI/CD)`/api`(cicd.py,计划 16 / ADR-0012)

第四条执行域(与生成任务/UI 执行/APP 执行并列互不隶属,ADR-0012 决策 6):把「勾选一批用例 → 独立环境跑 → 日志直播 → 出报告」落在 **Jenkins** 上——每 项目×kind 一个**常驻参数化 pipeline job**(job 名 `light_tester_p{id}_{kind}`,首次触发时 REST 自动查建,内联平台生成 Jenkinsfile,双 docker agent:UI=`playwright/python:v1.60` / api=`maven:3.9-eclipse-temurin-8`),一次执行 = 触发一次 build。平台**纯出站轮询**集成(~2s 拉 build 状态+`progressiveText` 增量日志,不开任何入站通道),日志经 SSE 总线中继直播并落盘回放,后端重启按 mock supervisor 先例对账收口。报告自研:UI 侧 pytest `--junitxml`、api 侧 surefire 原生 XML,平台单解析器入 `ci_runs`。

- **三实体**:执行计划(单类型 `kind=ui|api` + 分支前置 + 选择集合)、接口用例注册表(仓×分支×类×方法,TestNG 主,仓是唯一事实源、平台只存引用)、执行记录(**触发时快照 selection 进 run**,计划事后编辑不溯及历史)。
- **状态机**:`queued / running / success / failure / aborted / error`(`aborted`=停止;`error`=环境级失败,如排队 60s 未解析、Jenkins 不可达)。
- **新鲜度门(只提示不阻塞,ADR-0012 决策 4)**:触发先 `sync_repo`(切计划分支 + reset --hard)再比对工作区 vs 远端——reset 后 ahead 恒 0,**dirty 信号实际来自未推送产物(untracked)**。检测 stale 且未确认 → **整单 409**,前端弹确认,勾后按**远端现状(老代码)**执行;定时执行(未来)语义已钉=直接跑远端现状、不检测。
- **409 stale 响应结构**(dict detail,前端据此渲染确认弹窗):

```json
{"detail": {"message": "仓里有新代码未同步到远端,是否仍按远端现状(老代码)执行?",
            "freshness": {"on_branch": true, "dirty_files": 1, "ahead": 0, "stale": true}}}
```

- **快照缺失标注**:触发时对勾选项逐一核对仓内物料,已不存在的标 `skipped:true` + `skip_reason`(`stale`=注册表已无此方法 / `file_missing`=ui 脚本导出文件不在工作区)——警告列出、可继续、报告页标注「未执行」。
- **SSE 事件流** `GET /api/ci-runs/{run_id}/events`(鉴权同 jobs 事件流,Bearer 或 `?token=`):连上先 `status`(当前状态);活跃 run 持续转发轮询增量(`log` 文本块 / `status`→running),收到 `done`(带终态 status)或 `error` 后断流;**已终态连上即收 `status`+`snapshot`(status/total/passed/failed/skipped/results/error)后关流**。console 全量日志不走 SSE,经 `GET /api/ci-runs/{run_id}/console` 拉取。
- **权限**:计划/注册表/执行记录读=viewer;扫描、计划增删改、触发/停止/重跑=editor;Jenkins 连接三端点=**仅 admin**(403 `仅管理员可配置 Jenkins 连接`)。

**执行计划**(editor 写 / viewer 读;选择集合 ui 项=`{script_id, name}`(落库补 `file=test_{slug}.py`)/ api 项=`{class_name, method}`(落库补 `ref={class}#{method}`))

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{id}/ci-plans` | 计划列表(id 倒序,软删不显) |
| POST | `/api/projects/{id}/ci-plans` | 建计划 `{name(1-200), description?, kind(ui\|api), branch(1-200), selection[]}`(201;空 selection 可建,触发时 400 `空计划不可触发`;ui 项需 int script_id+非空 name / api 项需非空 class_name+method,400) |
| PUT | `/api/ci-plans/{plan_id}` | 更新(字段给了才改;selection 给了按计划 kind 整体重校验+补全) |
| DELETE | `/api/ci-plans/{plan_id}` | 删除(204,**软删**;历史 run 保留快照不受影响) |

**接口用例注册表**(editor 扫描 / viewer 读)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/interface-cases/scan` | 扫描同步 `{branch}`:sync_repo → 扫工作区(方法级正则解析)→ 注册表同步(扫到置 `active` 刷 framework/file_path/last_commit,未扫到置 `stale`)→ `{total, active, stale, added}`;项目 404 / 未配 api 仓 400 / 分支同步失败 400 |
| GET | `/api/projects/{id}/interface-cases?branch=` | 用例列表(class_name,method 升序,上限 2000;`{id, branch, class_name, method, status[active\|stale], framework, file_path}`) |

**执行**(preflight/触发/停止/重跑=editor;记录读=viewer)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/ci-runs/preflight` | 触发前预检 `{plan_ids}`(≥1)→ 逐计划 `{plan_id, name, kind, branch, freshness, valid, missing, error}`(valid/missing=快照可执行/缺失数;同步失败等记入该行 `error`,不中断其余计划);计划不存在/跨项目 400 |
| POST | `/api/projects/{id}/ci-runs` | 批量触发 `{plan_ids, confirm_stale?}` → `{runs:[CiRunOut], failures:[{plan_id, error}]}`;**stale 且未确认整单 409**(结构见上,已触发 run 不在响应,重 GET 可见);单计划失败(Jenkins 未配/物料全缺等)进 `failures` 行,唯 409 原样上抛;Jenkins 调用失败 502 |
| GET | `/api/projects/{id}/ci-runs` | 执行记录列表(id 倒序,近 100 条) |
| GET | `/api/ci-runs/{run_id}` | 执行详情(CiRunOut:id/project_id/plan_id/plan_name/kind/branch/selection 快照/status/jenkins_job/build_number/jenkins_url/total/passed/failed/skipped/results(逐用例含 skip_reason)/console_bytes/freshness/error/started_at/finished_at/created_at/created_by) |
| GET | `/api/ci-runs/{run_id}/events` | **SSE 直播**(事件类型与断流语义见上) |
| GET | `/api/ci-runs/{run_id}/console` | **全量 console 日志**(text/plain,无截断;排队中/尚无日志返回空串;权限同执行详情) |
| POST | `/api/ci-runs/{run_id}/stop` | 停止:Jenkins 侧 abort build(已落 build_number 时)+ 平台置 `aborted` 广播 done;非 queued/running 400 `该执行已结束,无需停止`;未配连接 400;Jenkins 停止失败 502 |
| POST | `/api/ci-runs/{run_id}/rerun` | 重跑(201,新 CiRun):按原计划再触发,**confirm_stale=True(不过新鲜度门)**;原计划已删 400 `原计划已删除,无法重跑` |

**Jenkins 连接**(全局单例,**仅 admin**;「用户管理」页 Jenkins 连接卡)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/jenkins/connection` | 读连接 `{configured, base_url, api_user, api_token, gitlab_exposed_base, credential_id}`(未配置时 `configured=false` 带默认值;token 明文回显,单机 MVP 口径同 git_token) |
| PUT | `/api/jenkins/connection` | 保存 `{base_url(须 http/s://), api_user, api_token, gitlab_exposed_base?(默认 http://host.docker.internal:8090), credential_id?(默认 gitlab-creds)}`(base_url 尾 `/` 归一;首存落 id=1 单例行) |
| POST | `/api/jenkins/connection/test` | 连通测试(未配置 400 `尚未配置 Jenkins 连接`;失败 400;成功 `{ok:true}`) |

```bash
# 触发(stale 时先收 409,确认后带 confirm_stale 重发)
curl -X POST http://127.0.0.1:8000/api/projects/1/ci-runs \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"plan_ids":[3]}'

curl -X POST http://127.0.0.1:8000/api/projects/1/ci-runs \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"plan_ids":[3],"confirm_stale":true}'
```

## 排障(接口视角)

| 现象 | 说明 |
|---|---|
| 全端点 401 `未登录或登录已过期` | 未带/无效 token:先 `POST /api/auth/login` 拿 token,再带 `Authorization: Bearer <token>`(SSE 可 `?token=`) |
| 明明存在的项目 404 | 当前用户不是该项目成员(不可见语义,不泄露存在性);找 admin 或该项目 owner 把自己加进成员 |
| 403 `无项目操作权限` | 角色不足(典型:viewer 发起执行/生成/推送、打开录制预览);找 owner 提角色 |
| admin 禁用自己被拒 | 自操作守卫:`PUT /api/users/{自己的id}` 带 `is_active` 即 409(改名/自改密放行;见用户管理节与 DEFER #71) |
| 任务创建成功但一直 pending | `.env` 无 `ANTHROPIC_API_KEY`,worker 未启动(设计行为) |
| api_generation 创建返回 400 | 项目未配置**有效的 http(s)** 接口自动化仓(kind=api 行;在自动化工程页配置) |
| accept 返回 400 `job not completed` | 只能转正已完成任务的暂存用例 |
| SSE 收不到事件 | 只能同时订阅未终态任务;终态任务连上即收 snapshot 后关流,属设计 |
| push 409 | 远程有新提交且 rebase 冲突,先在 GitLab 侧处理后再推 |
| app run 409 `设备 x 忙` | 同设备已有执行未结束(per-device 锁,占用即拒绝不排队);等终态或 force-finish 后再发 |
| `GET /api/app-devices` 看不到设备 / state 非 device | adb 未接好或未授权 USB 调试,重新插拔授权;APP 自动化仅支持 USB 真机,`adb` 须在 PATH |
| app run force-finish 后设备上回放还在跑 | force-finish 是协作式收口:当前阻塞中的 CLI 回放要等自然结束才真正停,平台侧状态已置 cancelled 且终态防覆盖不翻回 |
| app 导出 400 errors | 用例含平台不翻译的动作(GESTURE/ASSERT_TOAST 等),按错误清单的步骤号改用例或拆步;有错不推送 |

---
*最后更新:2026-09-16;对应代码基线:计划 16 CI/CD 模块(ADR-0012:Jenkins 常驻参数化 job×项目×kind + 双 docker agent + 纯出站轮询 + JUnit XML 自研报告,执行计划/接口用例注册表/执行记录/Jenkins 连接四组端点);参数级精确校验以 /docs(Swagger)为准*

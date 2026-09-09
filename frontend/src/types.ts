// 与后端 pydantic 契约一一对应(backend/app/schemas.py、routers/modules.py get_tree)
export type Priority = 'P0' | 'P1' | 'P2'

export interface Project {
  id: number
  name: string
  description: string | null
  git_repo_url: string | null
  created_at: string
}

// 树接口的节点形状(GET /api/projects/{id}/tree 返回 ModuleNode[])
export interface CaseSummary {
  id: number
  title: string
  priority: Priority
  executed_pass: boolean | null
}
export interface FeaturePointNode {
  id: number
  name: string
  cases: CaseSummary[]
}
export interface ModuleNode {
  id: number
  name: string
  children: ModuleNode[]
  feature_points: FeaturePointNode[]
}

// 用例详情(GET /api/cases/{id},含步骤)
export interface Step {
  id: number
  step_no: number
  action: string
  expected: string
}
export interface CaseDetail {
  id: number
  feature_point_id: number
  title: string
  priority: Priority
  precondition: string | null
  remark: string | null
  executed_pass: boolean | null
  steps: Step[]
}

export interface DocumentItem {
  id: number
  filename: string
  uploaded_at: string
}

export interface CaseUpsert {
  title: string
  priority: Priority
  precondition?: string | null
  remark?: string | null
  steps: { action: string; expected: string }[]
}

// 任务与暂存区相关类型
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface GenerationJob {
  id: number
  project_id: number
  document_id: number
  target_module_id: number
  job_type: string
  status: JobStatus
  model: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  error: string | null
  created_at: string
  document_name: string | null
  output_text: string | null
  thinking_text: string | null
  user_prompt: string | null
  tool_trace: string | null
  started_at: string | null
  finished_at: string | null
}

export interface StagedCaseItem {
  id: number
  job_id: number
  feature_point_name: string
  title: string
  priority: Priority
  precondition: string | null
  remark: string | null
  steps: { action: string; expected: string }[]
  created_at: string
}

export interface StagingGroup {
  feature_point_name: string
  cases: StagedCaseItem[]
}

export interface StagingResponse {
  job_id: number
  groups: StagingGroup[]
}

export type SSEEvent =
  | { type: 'status'; status: JobStatus }
  | { type: 'delta'; text: string }
  | { type: 'thinking_delta'; text: string }
  | { type: 'tool'; text: string }
  | { type: 'stage'; stage: 'compiling' | 'fixing'; round?: number }
  | { type: 'done'; staged_count?: number; files_count?: number }
  | { type: 'snapshot'; status: JobStatus; error: string | null; output_text: string | null;
      thinking_text: string | null; tool_trace: string | null;
      input_tokens: number; output_tokens: number; files_count: number; staged_count: number }
  | { type: 'error'; message: string }

export interface FileNode {
  name: string
  path: string
  is_dir: boolean
  children?: FileNode[] | null
}
export interface ChangeFile {
  path: string
  status: 'added' | 'modified' | 'deleted'
  tracked: boolean
}
export interface SyncResult {
  cloned: boolean
  updated: boolean
  failed: boolean
  branch: string
  commit_short: string
  error?: string | null
}
export interface PushResult {
  ok: boolean
  branch: string
  commit_short: string
  pushed_files: string[]
}

// ── UI 自动化 ──────────────────────────────
export interface UiLocator {
  strategy: 'test_id' | 'role' | 'placeholder' | 'label' | 'text' | 'css'
  role?: string
  name?: string
  value?: string
  fallbacks?: UiLocator[]
}
export interface UiStep {
  id: string
  action: string
  locator?: UiLocator
  params?: Record<string, unknown>
}
export interface UiVariable { name: string; default?: string; desc?: string }
export interface UiScriptDoc {
  version: number
  meta: {
    start_url: string
    auth_state_id?: number // 录制时用的登录态,执行默认带上
    target?: 'web' | 'android' | 'harmony' // 脚本目标端;缺省视为 web(version 1 兼容)
    launch_target?: string // 启动目标:Android 包名/鸿蒙 bundleName(web 无此字段)
  }
  variables: UiVariable[]
  steps: UiStep[]
}
export interface UiScript {
  id: number; project_id: number; name: string
  description: string | null; script: UiScriptDoc
  created_at: string; updated_at: string
}
export interface UiStepResult {
  index: number; step_id: string; action: string
  status: 'passed' | 'failed'; error: string | null
  screenshot: string | null; elapsed_ms: number
}
export interface UiRun {
  id: number; project_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  script_id: number; script_name: string; mode: string
  variables: Record<string, string>
  step_results: UiStepResult[]
  steps_total: number; steps_passed: number; steps_failed: number
  error: string | null; started_at: string | null; finished_at: string | null
  driver_target: string // 执行端:web/android/harmony(老记录由后端按 mode 派生为 web)
  ai_usage: Record<string, unknown> | null // AI 消耗统计(仅 AI 步骤运行时有值)
}
export interface UiAuthState {
  id: number; project_id: number; name: string; created_at: string
  kind: 'web_storage' | 'android_snapshot' // 登录态种类:Web 存储快照 / Android 应用快照
  app_package: string | null // Android 快照的应用包名(web 登录态为 null)
}

// ===== APP自动化(计划 12:SoloPi 原生 JSON 唯一事实源,独立域) =====
export interface AppCaseStep {
  operationNode: Record<string, unknown> | null
  operationMethod: {
    actionEnum: string
    operationParam: Record<string, string>
    encrypt: boolean
    safeEncrypt: boolean
  }
  operationIndex: number
  operationId: string
  stepId: string
}

export interface AppCaseJson {
  caseName: string
  caseDesc?: string
  targetAppPackage: string
  targetAppLabel?: string
  recordMode?: string
  advanceSettings?: string
  priority?: number
  operationLog: { steps: AppCaseStep[] }
  [key: string]: unknown // 原生 JSON 的未知顶层字段原样保留
}

export interface CheckDef {
  type: 'element_exists' | 'text_contains'
  text?: string
  resource_id?: string
  description?: string
  value?: string
}

export interface CheckResult {
  type: string
  passed: boolean
  detail: string
}

export interface AppScript {
  id: number
  project_id: number
  name: string
  description: string | null
  case_json: AppCaseJson
  app_package: string
  created_at: string
  updated_at: string
}

export type AppRunStatus = 'pending' | 'running' | 'passed' | 'failed' | 'cancelled'

export interface AppRun {
  id: number
  project_id: number
  status: AppRunStatus
  script_id: number
  script_name: string
  device_serial: string
  batch_id: string | null
  variables: Record<string, string>
  pre_checks: CheckDef[]
  post_checks: CheckDef[]
  perf_items: string[]
  run_state: string | null
  results: unknown[] | null
  check_results: { pre: CheckResult[] | null; post: CheckResult[] | null } | null
  perf_summary: Record<string, unknown> | null
  startup_summary: Record<string, unknown> | null
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export interface DeviceInfo {
  serial: string
  state: string
}

export interface AppPerfSeries {
  item: string
  columns: string[]
  rows: string[][]
}

// ── 接口Mock(计划13)──
export type MockConditionScope = 'query' | 'header' | 'body'
export type MockMatchMode = 'eq' | 'regex'
export type MockInstanceStatus = 'stopped' | 'starting' | 'running' | 'error'
export interface MockCondition { scope: MockConditionScope; key: string; match: MockMatchMode; value: string }
export interface MockInstance {
  id: number; project_id: number; name: string; description: string | null; port: number
  cors_enabled: boolean; default_status: number; default_body: string | null
  desired: 'running' | 'stopped'; status: MockInstanceStatus; error_message: string | null
  created_at: string; updated_at: string
}
export interface MockRule {
  id: number; instance_id: number; method: string; path_template: string; conditions: MockCondition[]
  enabled: boolean; response_status: number; response_headers: Record<string, string>
  response_body: string | null; enable_template: boolean; delay_ms: number
  timeout_enabled: boolean; timeout_seconds: number; sort_order: number; updated_at: string
}
export interface MockRuleBody {
  method: string; path_template: string; conditions: MockCondition[]; enabled: boolean
  response_status: number; response_headers: Record<string, string>
  response_body: string | null; enable_template: boolean; delay_ms: number
  timeout_enabled: boolean; timeout_seconds: number
}
export interface MockHit {
  id: number; instance_id: number; rule_id: number | null; method: string; path: string
  query: string | null; matched: boolean; response_status: number | null
  delay_ms: number; elapsed_ms: number; error: string | null; created_at: string
}
export interface MockHitDetail extends MockHit { request_headers: Record<string, string> | null; request_body: string | null }

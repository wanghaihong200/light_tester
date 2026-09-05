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
  meta: { start_url: string; auth_state_id?: number } // auth_state_id:录制时用的登录态,执行默认带上
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
}
export interface UiAuthState { id: number; project_id: number; name: string; created_at: string }

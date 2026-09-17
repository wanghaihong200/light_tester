// frontend/src/api/cicd.ts
import { http } from './client'

export type PlanKind = 'ui' | 'api'

// 计划选择集合项(存储形态);ui.file / api.ref 由后端富化,前端提交时可不带
export interface PlanSelectionUi { script_id: number; name: string; file?: string }
export interface PlanSelectionApi { ref?: string; class_name: string; method: string }
export type PlanSelectionItem = PlanSelectionUi | PlanSelectionApi

export interface ExecutionPlan {
  id: number
  project_id: number
  name: string
  description: string | null
  kind: PlanKind
  branch: string
  selection: PlanSelectionItem[]
  updated_at: string
}

export interface InterfaceCase {
  id: number
  branch: string
  class_name: string
  method: string
  status: 'active' | 'stale'
  framework: string
  file_path: string | null
}

// 新鲜度检测结果(与后端 freshness.check_freshness 同构)
export interface Freshness {
  on_branch: boolean
  dirty_files: number
  ahead: number
  stale: boolean
}

export interface CiCaseRow { class_name: string; name: string; status: string; time_s: number; message: string | null }

export interface CiRun {
  id: number
  project_id: number
  plan_id: number
  plan_name: string
  kind: PlanKind
  branch: string
  selection: (PlanSelectionItem & { skipped?: boolean; skip_reason?: string })[]
  status: 'queued' | 'running' | 'success' | 'failure' | 'aborted' | 'error'
  jenkins_job: string
  build_number: number | null
  jenkins_url: string | null
  total: number
  passed: number
  failed: number
  skipped: number
  results: CiCaseRow[] | null
  console_bytes: number
  error: string | null
  freshness: Freshness | null
  created_at: string
  finished_at: string | null
}

export interface PreflightItem {
  plan_id: number
  name: string
  kind: PlanKind
  branch: string
  freshness: Freshness | null
  valid: number
  missing: number
  error: string | null
}

export interface PlanPayload {
  name: string
  description?: string | null
  kind: PlanKind
  branch: string
  selection: PlanSelectionItem[]
}

export const listPlans = (projectId: number) =>
  http.get<ExecutionPlan[]>(`/projects/${projectId}/ci-plans`)
export const createPlan = (projectId: number, body: PlanPayload) =>
  http.post<ExecutionPlan>(`/projects/${projectId}/ci-plans`, body)
export const updatePlan = (id: number, body: Partial<PlanPayload>) =>
  http.put<ExecutionPlan>(`/ci-plans/${id}`, body)
export const deletePlan = (id: number) => http.del(`/ci-plans/${id}`)

export const scanInterfaceCases = (projectId: number, branch: string) =>
  http.post<{ total: number; active: number; stale: number; added: number }>(
    `/projects/${projectId}/interface-cases/scan`, { branch })
export const listInterfaceCases = (projectId: number, branch: string) =>
  http.get<InterfaceCase[]>(`/projects/${projectId}/interface-cases?branch=${encodeURIComponent(branch)}`)

export const preflight = (projectId: number, planIds: number[]) =>
  http.post<PreflightItem[]>(`/projects/${projectId}/ci-runs/preflight`, { plan_ids: planIds })
export const triggerRuns = (projectId: number, planIds: number[], confirmStale: boolean) =>
  http.post<{ runs: CiRun[]; failures: { plan_id: number; error: string }[] }>(
    `/projects/${projectId}/ci-runs`, { plan_ids: planIds, confirm_stale: confirmStale })

export const listCiRuns = (projectId: number) =>
  http.get<CiRun[]>(`/projects/${projectId}/ci-runs`)
export const getCiRun = (id: number) => http.get<CiRun>(`/ci-runs/${id}`)
export const stopCiRun = (id: number) => http.post<CiRun>(`/ci-runs/${id}/stop`)
export const rerunCiRun = (id: number) => http.post<CiRun>(`/ci-runs/${id}/rerun`)
// 配合 client.withSseToken 使用(裸 EventSource 带不了 Authorization,后端认 ?token=)
export const ciRunEventsUrl = (id: number) => `/api/ci-runs/${id}/events`

export interface JenkinsCfg {
  base_url: string
  api_user: string
  api_token: string
  gitlab_exposed_base: string
  credential_id: string
}
export const getJenkinsConnection = () =>
  http.get<JenkinsCfg & { configured: boolean }>('/jenkins/connection')
export const putJenkinsConnection = (body: JenkinsCfg) =>
  http.put<JenkinsCfg & { configured: boolean }>('/jenkins/connection', body)
export const testJenkinsConnection = () =>
  http.post<{ ok: boolean }>('/jenkins/connection/test')

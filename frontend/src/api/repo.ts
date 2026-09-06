import { http } from './client'
import type { ChangeFile, FileNode, PushResult, SyncResult } from '../types'

// 仓分类:一个项目可有 api/web/app 三个自动化仓,后端以 ?kind= 区分。
// 缺省 'api',既有调用方不传即维持原行为(plan11 起 web 仓供脚本导出使用)
export type RepoKind = 'api' | 'web' | 'app'

// kind 一律走 query 传给后端;已有查询串的端点(path 带 ?)用 & 续接
const kinded = (path: string, kind: RepoKind) => `${path}${path.includes('?') ? '&' : '?'}kind=${kind}`

export const syncRepo = (projectId: number, branch?: string, kind: RepoKind = 'api') =>
  http.post<SyncResult>(kinded(`/projects/${projectId}/repo/sync`, kind), branch ? { branch } : undefined)
export const listFiles = (projectId: number, kind: RepoKind = 'api') =>
  http.get<FileNode | { needs_sync: true } | { needs_config: true }>(kinded(`/projects/${projectId}/repo/files`, kind))
export const readFile = (projectId: number, path: string, kind: RepoKind = 'api') =>
  http.get<{ path: string; content: string; language: string }>(kinded(`/projects/${projectId}/repo/file?path=${encodeURIComponent(path)}`, kind))
export const listChanges = (projectId: number, kind: RepoKind = 'api') =>
  http.get<{ files: ChangeFile[] }>(kinded(`/projects/${projectId}/repo/changes`, kind))
export const listBranches = (projectId: number, kind: RepoKind = 'api') =>
  http.get<{ branches: string[] }>(kinded(`/projects/${projectId}/repo/branches`, kind))
// kind 追加在尾部可选参:保持 (projectId, files, branch, commit_message) 既有位置不变
export const pushFiles = (
  projectId: number, files: string[], branch: string, commit_message?: string, kind: RepoKind = 'api',
) =>
  http.post<PushResult>(kinded(`/projects/${projectId}/repo/push`, kind), { files, branch, commit_message })

// ── plan11 Task 8:多仓配置(GET viewer 可读 / PUT editor 权限,路由挂在 /api/projects/{id}/repo 下) ──
export interface AutomationRepoRow {
  id: number
  kind: RepoKind
  repo_url: string
  // 后端明文返回;前端不回显到输入框,留空提交即清除
  repo_token: string | null
  updated_at?: string
}

export const listAutomationRepos = (projectId: number) =>
  http.get<AutomationRepoRow[]>(`/projects/${projectId}/repo/automation-repos`)

export const putAutomationRepo = (projectId: number, kind: RepoKind, body: { repo_url: string; repo_token?: string | null }) =>
  http.put<{ id: number; kind: RepoKind; repo_url: string; repo_token: string | null }>(
    `/projects/${projectId}/repo/automation-repos/${kind}`, body,
  )

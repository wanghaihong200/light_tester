import { http } from './client'
import type { ChangeFile, FileNode, PushResult, SyncResult } from '../types'

export const syncRepo = (projectId: number, branch?: string) =>
  http.post<SyncResult>(`/projects/${projectId}/repo/sync`, branch ? { branch } : undefined)
export const listFiles = (projectId: number) => http.get<FileNode | { needs_sync: true }>(`/projects/${projectId}/repo/files`)
export const readFile = (projectId: number, path: string) =>
  http.get<{ path: string; content: string; language: string }>(`/projects/${projectId}/repo/file?path=${encodeURIComponent(path)}`)
export const listChanges = (projectId: number) => http.get<{ files: ChangeFile[] }>(`/projects/${projectId}/repo/changes`)
export const listBranches = (projectId: number) => http.get<{ branches: string[] }>(`/projects/${projectId}/repo/branches`)
export const pushFiles = (projectId: number, files: string[], branch: string, commit_message?: string) =>
  http.post<PushResult>(`/projects/${projectId}/repo/push`, { files, branch, commit_message })

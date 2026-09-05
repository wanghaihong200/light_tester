import type { Project } from '../types'
import { http } from './client'

export function listProjects() {
  return http.get<Project[]>('/projects')
}
export function createProject(p: { name: string; description?: string | null; git_repo_url?: string | null; git_token?: string | null }) {
  return http.post<Project>('/projects', p)
}
export function updateProject(id: number, p: Partial<{ name: string; description: string | null; git_repo_url: string | null; git_token: string | null }>) {
  return http.put<Project>(`/projects/${id}`, p)
}
export function deleteProject(id: number) {
  return http.del(`/projects/${id}`)
}

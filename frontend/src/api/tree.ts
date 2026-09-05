import type { ModuleNode } from '../types'
import { http } from './client'

export function fetchTree(projectId: number) {
  return http.get<ModuleNode[]>(`/projects/${projectId}/tree`)
}
export function createModule(projectId: number, p: { name: string; parentId?: number | null }) {
  return http.post<{ id: number; name: string; parent_id: number | null }>(`/projects/${projectId}/modules`, {
    name: p.name,
    parent_id: p.parentId ?? null,
  })
}
export function updateModule(id: number, p: { name?: string; parentId?: number | null }) {
  return http.put<{ id: number; name: string; parent_id: number | null }>(`/modules/${id}`, {
    ...(p.name !== undefined ? { name: p.name } : {}),
    ...(p.parentId !== undefined ? { parent_id: p.parentId } : {}),
  })
}
export function deleteModule(id: number) {
  return http.del(`/modules/${id}`)
}
export function createFeaturePoint(moduleId: number, name: string) {
  return http.post<{ id: number; name: string; module_id: number }>(`/modules/${moduleId}/feature-points`, { name })
}
export function updateFeaturePoint(id: number, name: string) {
  return http.put<{ id: number; name: string; module_id: number }>(`/feature-points/${id}`, { name })
}
export function deleteFeaturePoint(id: number) {
  return http.del(`/feature-points/${id}`)
}

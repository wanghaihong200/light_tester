import type { DocumentItem } from '../types'
import { http } from './client'

export function listDocuments(projectId: number) {
  return http.get<DocumentItem[]>(`/projects/${projectId}/documents`)
}
export function uploadDocument(projectId: number, file: File) {
  return http.upload<DocumentItem>(`/projects/${projectId}/documents`, file)
}
export function deleteDocument(id: number) {
  return http.del(`/documents/${id}`)
}

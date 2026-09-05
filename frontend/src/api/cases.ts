import type { CaseDetail, CaseUpsert } from '../types'
import { http } from './client'

export function getCase(id: number) {
  return http.get<CaseDetail>(`/cases/${id}`)
}
export function createCase(fpId: number, body: CaseUpsert) {
  return http.post<CaseDetail>(`/feature-points/${fpId}/cases`, body)
}
export function updateCase(id: number, body: CaseUpsert) {
  return http.put<CaseDetail>(`/cases/${id}`, body)
}
export function patchExecution(id: number, executedPass: boolean | null) {
  return http.patch<CaseDetail>(`/cases/${id}/execution`, { executed_pass: executedPass })
}
export function deleteCase(id: number) {
  return http.del(`/cases/${id}`)
}

// 接口Mock(计划13):HTTP Mock 服务实例/规则/命中
import { http } from './client'
import type { MockHit, MockHitDetail, MockInstance, MockRule, MockRuleBody } from '../types'

export type MockInstanceBody = {
  name: string; description?: string | null; port?: number | null
  cors_enabled?: boolean; default_status?: number; default_body?: string | null
}

export const listMockInstances = (projectId: number) =>
  http.get<MockInstance[]>(`/projects/${projectId}/mock-instances`)
export const createMockInstance = (projectId: number, body: MockInstanceBody) =>
  http.post<MockInstance>(`/projects/${projectId}/mock-instances`, body)
export const updateMockInstance = (id: number, body: Partial<MockInstanceBody>) =>
  http.put<MockInstance>(`/mock-instances/${id}`, body)
export const deleteMockInstance = (id: number) => http.del(`/mock-instances/${id}`)
export const startMockInstance = (id: number) => http.post<MockInstance>(`/mock-instances/${id}/start`)
export const stopMockInstance = (id: number) => http.post<MockInstance>(`/mock-instances/${id}/stop`)

export const listMockRules = (instanceId: number) =>
  http.get<MockRule[]>(`/mock-instances/${instanceId}/rules`)
export const createMockRule = (instanceId: number, body: MockRuleBody) =>
  http.post<MockRule>(`/mock-instances/${instanceId}/rules`, body)
export const updateMockRule = (id: number, body: Partial<MockRuleBody>) =>
  http.put<MockRule>(`/mock-rules/${id}`, body)
export const deleteMockRule = (id: number) => http.del(`/mock-rules/${id}`)
// 后端 reorder 返回重排后的完整规则列表(T10 前端直接回贴,免二次拉取)
export const reorderMockRules = (instanceId: number, ruleIds: number[]) =>
  http.put<MockRule[]>(`/mock-instances/${instanceId}/rules/reorder`, { rule_ids: ruleIds })

export type MockHitsFilter = 'all' | 'matched' | 'unmatched'
export const listMockHits = (instanceId: number, filter: MockHitsFilter = 'all', limit = 200) =>
  http.get<MockHit[]>(`/mock-instances/${instanceId}/hits?filter=${filter}&limit=${limit}`)
export const getMockHit = (id: number) => http.get<MockHitDetail>(`/mock-hits/${id}`)
export const clearMockHits = (instanceId: number) => http.del(`/mock-instances/${instanceId}/hits`)

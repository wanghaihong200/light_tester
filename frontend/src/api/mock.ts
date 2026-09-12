// 接口Mock(计划13):HTTP Mock 服务实例/规则组/规则/命中;计划15:规则组+透传+命中 outcome
import { http } from './client'
import type {
  MockHit, MockHitDetail, MockInstance, MockRule, MockRuleBody, MockRuleGroup, MockRuleGroupBody,
} from '../types'

export type MockInstanceBody = {
  name: string; description?: string | null; port?: number | null
  cors_enabled?: boolean; default_status?: number; default_body?: string | null
  passthrough_enabled?: boolean; upstream_base_url?: string | null
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
// 实例单查(计划15 T10 详情页头部要实例名+port 拼 base_url;后端 mock.py GET /mock-instances/{id} 已有)
export const getMockInstance = (id: number) => http.get<MockInstance>(`/mock-instances/${id}`)

// ── 规则组(计划15):规则挂到组下,组按 method+path_template 匹配 ──
export const listMockRuleGroups = (instanceId: number) =>
  http.get<MockRuleGroup[]>(`/mock-instances/${instanceId}/rule-groups`)
export const createMockRuleGroup = (instanceId: number, body: MockRuleGroupBody) =>
  http.post<MockRuleGroup>(`/mock-instances/${instanceId}/rule-groups`, body)
export const updateMockRuleGroup = (id: number, body: Partial<MockRuleGroupBody> & { enabled?: boolean }) =>
  http.put<MockRuleGroup>(`/mock-rule-groups/${id}`, body)
export const deleteMockRuleGroup = (id: number) => http.del(`/mock-rule-groups/${id}`)
export const reorderMockGroups = (instanceId: number, groupIds: number[]) =>
  http.put<MockRuleGroup[]>(`/mock-instances/${instanceId}/rule-groups/reorder`, { group_ids: groupIds })
export const reorderMockGroupRules = (groupId: number, ruleIds: number[]) =>
  http.put<MockRule[]>(`/mock-rule-groups/${groupId}/rules/reorder`, { rule_ids: ruleIds })

export const listMockRules = (instanceId: number) =>
  http.get<MockRule[]>(`/mock-instances/${instanceId}/rules`)
export const createMockRule = (instanceId: number, body: MockRuleBody) =>
  http.post<MockRule>(`/mock-instances/${instanceId}/rules`, body)
export const updateMockRule = (id: number, body: Partial<MockRuleBody>) =>
  http.put<MockRule>(`/mock-rules/${id}`, body)
export const deleteMockRule = (id: number) => http.del(`/mock-rules/${id}`)

export type MockHitsFilter = 'all' | 'matched' | 'unmatched' | 'forwarded'
export const listMockHits = (instanceId: number, filter: MockHitsFilter = 'all', limit = 200, groupId?: number) =>
  http.get<MockHit[]>(`/mock-instances/${instanceId}/hits?filter=${filter}&limit=${limit}` +
    (groupId != null ? `&group_id=${groupId}` : ''))
export const getMockHit = (id: number) => http.get<MockHitDetail>(`/mock-hits/${id}`)
export const clearMockHits = (instanceId: number) => http.del(`/mock-instances/${instanceId}/hits`)

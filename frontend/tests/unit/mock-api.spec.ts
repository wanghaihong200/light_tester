import { describe, expect, it, vi } from 'vitest'

// vi.mock 工厂被提升到文件顶,httpMock 须随 hoisted 提升才能在工厂内引用(同 app-script-editor.spec 风格)
const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }))
vi.mock('../../src/api/client', () => ({ http: httpMock }))

import {
  clearMockHits, createMockInstance, createMockRule, createMockRuleGroup, deleteMockRuleGroup,
  getMockHit, listMockHits, listMockInstances, listMockRuleGroups, listMockRules,
  reorderMockGroupRules, reorderMockGroups, startMockInstance, stopMockInstance, updateMockRuleGroup,
} from '../../src/api/mock'

describe('mock api 路径与载荷', () => {
  it('实例端点', () => {
    listMockInstances(7)
    expect(httpMock.get).toHaveBeenCalledWith('/projects/7/mock-instances')
    createMockInstance(7, { name: 'svc' })
    expect(httpMock.post).toHaveBeenCalledWith('/projects/7/mock-instances', { name: 'svc' })
    startMockInstance(3)
    expect(httpMock.post).toHaveBeenCalledWith('/mock-instances/3/start')
    stopMockInstance(3)
    expect(httpMock.post).toHaveBeenCalledWith('/mock-instances/3/stop')
  })
  it('规则组端点(计划15)', () => {
    listMockRuleGroups(3)
    expect(httpMock.get).toHaveBeenCalledWith('/mock-instances/3/rule-groups')
    createMockRuleGroup(3, { method: 'GET', path_template: '/a' })
    expect(httpMock.post).toHaveBeenCalledWith('/mock-instances/3/rule-groups', { method: 'GET', path_template: '/a' })
    updateMockRuleGroup(5, { enabled: false })
    expect(httpMock.put).toHaveBeenCalledWith('/mock-rule-groups/5', { enabled: false })
    deleteMockRuleGroup(5)
    expect(httpMock.del).toHaveBeenCalledWith('/mock-rule-groups/5')
    reorderMockGroups(3, [2, 1])
    expect(httpMock.put).toHaveBeenCalledWith('/mock-instances/3/rule-groups/reorder', { group_ids: [2, 1] })
    reorderMockGroupRules(5, [9, 8])
    expect(httpMock.put).toHaveBeenCalledWith('/mock-rule-groups/5/rules/reorder', { rule_ids: [9, 8] })
  })
  it('规则与命中端点', () => {
    listMockRules(3)
    expect(httpMock.get).toHaveBeenCalledWith('/mock-instances/3/rules')
    createMockRule(3, {} as never)
    expect(httpMock.post).toHaveBeenCalledWith('/mock-instances/3/rules', {})
    listMockHits(3, 'unmatched', 50)
    expect(httpMock.get).toHaveBeenCalledWith('/mock-instances/3/hits?filter=unmatched&limit=50')
    listMockHits(3, 'forwarded', 200, 7)
    expect(httpMock.get).toHaveBeenCalledWith('/mock-instances/3/hits?filter=forwarded&limit=200&group_id=7')
    getMockHit(9)
    expect(httpMock.get).toHaveBeenCalledWith('/mock-hits/9')
    clearMockHits(3)
    expect(httpMock.del).toHaveBeenCalledWith('/mock-instances/3/hits')
  })
})

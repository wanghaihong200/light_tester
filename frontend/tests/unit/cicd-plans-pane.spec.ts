import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listPlans: vi.fn(), deletePlan: vi.fn() }))
vi.mock('../../src/api/cicd', () => api)
vi.mock('../../src/api/repo', () => ({ listBranches: vi.fn(async () => ({ branches: ['master'] })) }))
vi.mock('../../src/api/uiAutomation', () => ({ listUiScripts: vi.fn(async () => []) }))
vi.mock('../../src/components/cicd/PlanDialog.vue', () => ({ default: { template: '<div class="plan-dialog-stub"/>' } }))
vi.mock('../../src/components/cicd/TriggerDialog.vue', () => ({ default: { template: '<div class="trigger-dialog-stub"/>' } }))

import PlansPane from '../../src/components/cicd/PlansPane.vue'

const PLAN = {
  id: 1, project_id: 3, name: '接口回归', description: null, kind: 'api' as const,
  branch: 'master', selection: [{ class_name: 'com.x.A', method: 'm1' }], updated_at: '2026-09-16T10:00:00',
}

describe('PlansPane', () => {
  it('加载并渲染计划列表', async () => {
    api.listPlans.mockResolvedValue([PLAN])
    const w = mount(PlansPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(api.listPlans).toHaveBeenCalledWith(3)
    expect(w.text()).toContain('接口回归')
    expect(w.text()).toContain('master')
  })

  it('选中行后可打开触发对话框', async () => {
    api.listPlans.mockResolvedValue([PLAN])
    const w = mount(PlansPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    await w.find('.el-table__body .el-checkbox').trigger('click')
    await flushPromises()
    await w.find('.trigger-btn').trigger('click')
    expect(w.find('.trigger-dialog-stub').exists()).toBe(true)
  })
})

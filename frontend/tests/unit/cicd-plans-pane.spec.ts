import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listPlans: vi.fn(), deletePlan: vi.fn() }))
const repoApi = vi.hoisted(() => ({
  listBranches: vi.fn(async () => ({ branches: ['master'] })),
  listAutomationRepos: vi.fn(async () => []),
}))
vi.mock('../../src/api/cicd', () => api)
// 展开真实模块:repoDisplayName(纯函数)走实现,仅网络调用 mock
vi.mock('../../src/api/repo', async (importOriginal) => ({ ...(await importOriginal()), ...repoApi }))
vi.mock('../../src/api/uiAutomation', () => ({ listUiScripts: vi.fn(async () => []) }))
vi.mock('../../src/components/cicd/PlanDialog.vue', () => ({ default: { template: '<div class="plan-dialog-stub"/>' } }))
vi.mock('../../src/components/cicd/TriggerDialog.vue', () => ({ default: { template: '<div class="trigger-dialog-stub"/>' } }))

import PlansPane from '../../src/components/cicd/PlansPane.vue'

const PLAN = {
  id: 1, project_id: 3, name: '接口回归', description: null, kind: 'api' as const,
  branch: 'master', selection: [{ class_name: 'com.x.A', method: 'm1' }], updated_at: '2026-09-16T10:00:00',
}
const PLAN_UI = {
  id: 2, project_id: 3, name: 'UI 冒烟', description: null, kind: 'ui' as const,
  branch: 'dev', selection: [{ script_id: 7, name: '登录', file: 'test_7_login.py' }], updated_at: '2026-09-17T10:00:00',
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

  it('自动化工程列按计划类型映射仓显示名;未配置显示 —', async () => {
    repoApi.listAutomationRepos.mockResolvedValue([
      { id: 1, kind: 'api', repo_url: 'http://localhost:8090/haihai/light_api_autotest_demo', repo_token: null },
      { id: 2, kind: 'web', repo_url: 'http://localhost:8090/haihai/light_web_ui_autotest_demo.git', repo_token: null },
    ])
    api.listPlans.mockResolvedValue([PLAN, PLAN_UI])
    const w = mount(PlansPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('light_api_autotest_demo') // api 计划 → api 仓
    expect(w.text()).toContain('light_web_ui_autotest_demo') // ui 计划 → web 仓(.git 已剥)
    expect(repoApi.listAutomationRepos).toHaveBeenCalledWith(3)
  })

  it('仓未配置时自动化工程列显示 —', async () => {
    repoApi.listAutomationRepos.mockResolvedValue([])
    api.listPlans.mockResolvedValue([PLAN])
    const w = mount(PlansPane, { props: { projectId: 3 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.get('.el-table__body').text()).toContain('—')
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

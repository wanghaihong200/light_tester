// frontend/tests/unit/cicd-plan-dialog.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import type { InterfaceCase } from '../../src/api/cicd'

const api = vi.hoisted(() => ({
  createPlan: vi.fn(),
  updatePlan: vi.fn(),
  listInterfaceCases: vi.fn(),
  scanInterfaceCases: vi.fn(),
  listUiCases: vi.fn(),
  scanUiCases: vi.fn(),
}))
const repoApi = vi.hoisted(() => ({ listBranches: vi.fn(), listAutomationRepos: vi.fn() }))
vi.mock('../../src/api/cicd', () => api)
// 展开真实模块:repoDisplayName(纯函数)走实现,仅网络调用 mock
vi.mock('../../src/api/repo', async (importOriginal) => ({ ...(await importOriginal()), ...repoApi }))

import PlanDialog from '../../src/components/cicd/PlanDialog.vue'

const mountDialog = (props: Record<string, unknown> = {}) =>
  mount(PlanDialog, { props: { projectId: 3, plan: null, modelValue: true, ...props },
                      global: { plugins: [ElementPlus] }, attachTo: document.body })

describe('PlanDialog', () => {
  const REPOS = [
    { id: 1, kind: 'api', repo_url: 'http://localhost:8090/haihai/light_api_autotest_demo', repo_token: null },
    { id: 2, kind: 'web', repo_url: 'http://localhost:8090/haihai/light_web_ui_autotest_demo', repo_token: null },
  ]

  const UI_CASES: InterfaceCase[] = [
    { id: 1, branch: 'master', class_name: 'tests/test_smoke.py', method: 'test_login', status: 'active',
      framework: 'pytest', file_path: 'tests/test_smoke.py', case_type: 'web',
      title: '登录态直达', markers: ['account:standard'] },
    { id: 2, branch: 'master', class_name: 'tests/test_smoke.py', method: 'test_gone', status: 'stale',
      framework: 'pytest', file_path: 'tests/test_smoke.py', case_type: 'web', title: null, markers: [] },
  ]

  it('ui 模式选分支后拉注册表;扫描按钮刷新;标题/标记/状态列可见', async () => {
    repoApi.listAutomationRepos.mockResolvedValue(REPOS)
    repoApi.listBranches.mockResolvedValue({ branches: ['master'] })
    api.listUiCases.mockResolvedValue(UI_CASES)
    api.scanUiCases.mockResolvedValue({ total: 2, added: 1, stale: 1, active: 1 })
    const w = mountDialog() // 默认 kind='ui'
    await flushPromises()
    ;(w.vm as unknown as { form: { branch: string } }).form.branch = 'master'
    await flushPromises()
    expect(api.listUiCases).toHaveBeenCalledWith(3, 'master')
    expect(w.text()).toContain('登录态直达')
    expect(w.text()).toContain('account:standard')
    expect(w.text()).toContain('stale')
    // 扫描按钮(两分支同款):ui 分支也能扫
    const btn = w.findAll('button').find((b) => b.text().includes('扫描 master'))
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    await flushPromises()
    expect(api.scanUiCases).toHaveBeenCalledWith(3, 'master')
    expect(api.listUiCases).toHaveBeenCalledTimes(2)
  })

  it('ui 模式保存 payload 为 {file_path, function}', async () => {
    repoApi.listAutomationRepos.mockResolvedValue(REPOS)
    repoApi.listBranches.mockResolvedValue({ branches: ['master'] })
    api.listUiCases.mockResolvedValue(UI_CASES)
    api.createPlan.mockResolvedValue({})
    const w = mountDialog()
    await flushPromises()
    ;(w.vm as unknown as { form: { branch: string } }).form.branch = 'master'
    await flushPromises()
    const vm = w.vm as unknown as { form: { name: string }; uiSel: InterfaceCase[]; save: () => Promise<void> }
    vm.form.name = 'ui计划'
    // 编程式勾选 active 行(uiSel 经 defineExpose 暴露;save 内校验仅查名称非空与 selection 非空,可直通)
    vm.uiSel = [UI_CASES[0]]
    await vm.save()
    await flushPromises()
    expect(api.createPlan).toHaveBeenCalledWith(3, expect.objectContaining({
      kind: 'ui',
      selection: [{ file_path: 'tests/test_smoke.py', function: 'test_login' }],
    }))
  })

  it('ui 分支注册表为空时展示扫描空态指引', async () => {
    repoApi.listAutomationRepos.mockResolvedValue(REPOS)
    repoApi.listBranches.mockResolvedValue({ branches: ['master'] })
    api.listUiCases.mockResolvedValue([])
    const w = mountDialog()
    await flushPromises()
    ;(w.vm as unknown as { form: { branch: string } }).form.branch = 'master'
    await flushPromises()
    expect(w.text()).toContain('尚未扫描到用例')
  })

  it('项目未配置此类型仓时给出提示,分支下拉禁用', async () => {
    repoApi.listAutomationRepos.mockResolvedValue([])
    repoApi.listBranches.mockClear() // 调用计数跨用例共享,先清零再断言
    const w = mountDialog()
    await flushPromises()
    expect(w.text()).toContain('该项目未配置此类型自动化仓')
    expect((w.vm as unknown as { repoUrl: string }).repoUrl).toBe('')
    expect(repoApi.listBranches).not.toHaveBeenCalled()
  })

  it('api 模式需扫描;扫描后列出 active 方法,保存 payload 形态正确', async () => {
    repoApi.listAutomationRepos.mockResolvedValue(REPOS)
    repoApi.listBranches.mockResolvedValue({ branches: ['master'] })
    api.listInterfaceCases.mockResolvedValue([
      { id: 1, branch: 'master', class_name: 'com.x.AuthApiTest', method: 'loginOk', status: 'active', framework: 'testng', file_path: null },
      { id: 2, branch: 'master', class_name: 'com.x.AuthApiTest', method: 'loginBad', status: 'stale', framework: 'testng', file_path: null },
    ])
    api.createPlan.mockResolvedValue({})
    api.scanInterfaceCases.mockResolvedValue({ total: 2, added: 1, stale: 1, active: 1 }) // doScan 读取统计字段
    const w = mountDialog()
    ;(w.vm as unknown as { form: { kind: string; branch: string } }).form.kind = 'api'
    ;(w.vm as unknown as { form: { branch: string } }).form.branch = 'master'
    await flushPromises()
    await w.find('.scan-btn').trigger('click')
    await flushPromises()
    expect(api.scanInterfaceCases).toHaveBeenCalledWith(3, 'master')
    expect(w.text()).toContain('com.x.AuthApiTest')
    expect(w.text()).toContain('stale') // stale 标注可见
    // 勾选第一行(active)并保存
    ;(w.vm as unknown as { toggleCase: (row: unknown, on: boolean) => void })
      .toggleCase({ class_name: 'com.x.AuthApiTest', method: 'loginOk' }, true)
    ;(w.vm as unknown as { form: { name: string } }).form.name = '接口冒烟回归' // save 校验名称非空
    ;(w.vm as unknown as { save: () => Promise<void> }).save()
    await flushPromises()
    expect(api.createPlan).toHaveBeenCalledWith(3, expect.objectContaining({
      kind: 'api', branch: 'master',
      selection: [{ class_name: 'com.x.AuthApiTest', method: 'loginOk' }],
    }))
  })
})

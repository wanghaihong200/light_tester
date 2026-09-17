// frontend/tests/unit/cicd-plan-dialog.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createPlan: vi.fn(),
  updatePlan: vi.fn(),
  listInterfaceCases: vi.fn(),
  scanInterfaceCases: vi.fn(),
  listUiScriptMaterials: vi.fn(),
}))
const repoApi = vi.hoisted(() => ({ listBranches: vi.fn(), listAutomationRepos: vi.fn() }))
const uiApi = vi.hoisted(() => ({ listUiScripts: vi.fn() }))
vi.mock('../../src/api/cicd', () => api)
// 展开真实模块:repoDisplayName(纯函数)走实现,仅网络调用 mock
vi.mock('../../src/api/repo', async (importOriginal) => ({ ...(await importOriginal()), ...repoApi }))
vi.mock('../../src/api/uiAutomation', () => uiApi)

import PlanDialog from '../../src/components/cicd/PlanDialog.vue'

const mountDialog = (props: Record<string, unknown> = {}) =>
  mount(PlanDialog, { props: { projectId: 3, plan: null, modelValue: true, ...props },
                      global: { plugins: [ElementPlus] }, attachTo: document.body })

describe('PlanDialog', () => {
  const REPOS = [
    { id: 1, kind: 'api', repo_url: 'http://localhost:8090/haihai/light_api_autotest_demo', repo_token: null },
    { id: 2, kind: 'web', repo_url: 'http://localhost:8090/haihai/light_web_ui_autotest_demo', repo_token: null },
  ]

  it('未选分支时用例区禁用;ui 模式选分支后按分支物料过滤脚本', async () => {
    repoApi.listAutomationRepos.mockResolvedValue(REPOS)
    repoApi.listBranches.mockResolvedValue({ branches: ['master', 'release'] })
    uiApi.listUiScripts.mockResolvedValue([
      { id: 7, name: '登录流程', driver_target: 'web' },
      { id: 8, name: '下单流程', driver_target: 'web' },
    ])
    api.listUiScriptMaterials.mockResolvedValue([
      { script_id: 7, name: '登录流程', file: 'test_7_login.py', exists: true },
      { script_id: 8, name: '下单流程', file: 'test_8_order.py', exists: false },
    ])
    const w = mountDialog()
    await flushPromises()
    expect((w.find('.cases-area').element as HTMLDivElement).classList.contains('is-disabled')).toBe(true)
    // 唯一 web 仓自动选中(显示名 = repo_url 末段)
    expect(w.text()).toContain('light_web_ui_autotest_demo')
    // 选分支(el-select 渲染在下拉 teleport;直接设值触发 watch)
    ;(w.vm as unknown as { form: { branch: string } }).form.branch = 'master'
    await flushPromises()
    expect(uiApi.listUiScripts).toHaveBeenCalledWith(3)
    expect(api.listUiScriptMaterials).toHaveBeenCalledWith(3, 'master')
    expect(w.text()).toContain('登录流程') // 已导出 → 可见可勾
    expect(w.text()).not.toContain('下单流程') // 未导出 → 分支即事实源,不显示
  })

  it('分支上无任何已导出脚本时展示空态指引', async () => {
    repoApi.listAutomationRepos.mockResolvedValue(REPOS)
    repoApi.listBranches.mockResolvedValue({ branches: ['master'] })
    uiApi.listUiScripts.mockResolvedValue([{ id: 7, name: '登录流程', driver_target: 'web' }])
    api.listUiScriptMaterials.mockResolvedValue([])
    const w = mountDialog()
    await flushPromises()
    ;(w.vm as unknown as { form: { branch: string } }).form.branch = 'master'
    await flushPromises()
    expect(w.text()).toContain('该分支暂无已导出脚本')
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

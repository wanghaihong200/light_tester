// frontend/tests/unit/cicd-plan-dialog.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createPlan: vi.fn(),
  updatePlan: vi.fn(),
  listInterfaceCases: vi.fn(),
  scanInterfaceCases: vi.fn(),
}))
const repoApi = vi.hoisted(() => ({ listBranches: vi.fn() }))
const uiApi = vi.hoisted(() => ({ listUiScripts: vi.fn() }))
vi.mock('../../src/api/cicd', () => api)
vi.mock('../../src/api/repo', () => repoApi)
vi.mock('../../src/api/uiAutomation', () => uiApi)

import PlanDialog from '../../src/components/cicd/PlanDialog.vue'

const mountDialog = (props: Record<string, unknown> = {}) =>
  mount(PlanDialog, { props: { projectId: 3, plan: null, modelValue: true, ...props },
                      global: { plugins: [ElementPlus] }, attachTo: document.body })

describe('PlanDialog', () => {
  it('未选分支时用例区禁用;ui 模式选分支后列出 Web 脚本', async () => {
    repoApi.listBranches.mockResolvedValue({ branches: ['master', 'release'] })
    uiApi.listUiScripts.mockResolvedValue([
      { id: 7, name: '登录流程', driver_target: 'web' },
      { id: 8, name: '下单流程', driver_target: 'web' },
    ])
    const w = mountDialog()
    await flushPromises()
    expect((w.find('.cases-area').element as HTMLDivElement).classList.contains('is-disabled')).toBe(true)
    // 选分支(el-select 渲染在下拉 teleport;直接设值触发 watch)
    ;(w.vm as unknown as { form: { branch: string } }).form.branch = 'master'
    await flushPromises()
    expect(uiApi.listUiScripts).toHaveBeenCalledWith(3)
    expect(w.text()).toContain('登录流程')
  })

  it('api 模式需扫描;扫描后列出 active 方法,保存 payload 形态正确', async () => {
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

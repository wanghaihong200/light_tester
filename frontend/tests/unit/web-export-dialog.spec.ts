import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'

// mock 出口对齐真实 API 模块的具名导出;rejection 形状对齐 client.ts 的错误封装:
// request() 对非 2xx 抛 ApiError(status, message)(message = String(detail)),不携带原始 body。
const mocks = vi.hoisted(() => ({
  exportUiScript: vi.fn(),
  listBranches: vi.fn(),
}))
vi.mock('../../src/api/uiAutomation', () => ({ exportUiScript: mocks.exportUiScript }))
vi.mock('../../src/api/repo', () => ({ listBranches: mocks.listBranches }))

import ExportDialog from '../../src/components/webauto/ExportDialog.vue'

function mountDlg(visible = true) {
  return mount(ExportDialog, {
    props: { scriptId: 42, projectId: 1, scriptName: '下单流程', visible },
    global: {
      plugins: [ElementPlus],
      stubs: {
        // el-dialog 默认 teleport 到 body 且懒渲染;拍平成内联插槽才能对 w.text() 断言错误清单
        'el-dialog': { template: '<div><slot /><slot name="footer" /></div>', props: ['modelValue'] },
      },
    },
  })
}

describe('ExportDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('打开时以 kind=web 拉分支列表并预填首个分支与默认 commit 说明', async () => {
    mocks.listBranches.mockResolvedValue({ branches: ['main', 'dev'] })
    const w = mountDlg()
    await flushPromises()
    expect(mocks.listBranches).toHaveBeenCalledWith(1, 'web')
    expect((w.vm as unknown as { branch: string }).branch).toBe('main')
    expect((w.vm as unknown as { commitMessage: string }).commitMessage).toBe('Web自动化导出 下单流程')
  })

  it('确认后调用导出 API(kind=web 仓分支),成功 emit exported 并关框', async () => {
    mocks.listBranches.mockResolvedValue({ branches: ['main'] })
    mocks.exportUiScript.mockResolvedValue({ ok: true, branch: 'main', commit_short: 'ab12cd3', pushed_files: [], files: ['test_x.py'] })
    const w = mountDlg()
    await flushPromises()
    ;(w.vm as unknown as { commitMessage: string }).commitMessage = '导出'
    await (w.vm as unknown as { onConfirm: () => Promise<void> }).onConfirm()
    await flushPromises()
    expect(mocks.exportUiScript).toHaveBeenCalledWith(42, { branch: 'main', commit_message: '导出' })
    expect(w.emitted('exported')).toEqual([['ab12cd3']])
    expect(w.emitted('update:visible')).toContainEqual([false])
  })

  it('400 透传错误文本渲染为错误清单且不 emit(真实 ApiError 形状)', async () => {
    mocks.listBranches.mockResolvedValue({ branches: ['main'] })
    mocks.exportUiScript.mockRejectedValue(new ApiError(400, '步骤1: ai_tap 无法导出'))
    const w = mountDlg()
    await flushPromises()
    await (w.vm as unknown as { onConfirm: () => Promise<void> }).onConfirm()
    await flushPromises()
    expect(w.text()).toContain('ai_tap')
    expect(w.emitted('exported')).toBeFalsy()
    // 弹窗保持打开,用户可改参数重试
    expect(w.emitted('update:visible')).toBeFalsy()
  })

  it('400 detail={errors:[…]}(导出校验失败)逐行渲染错误清单且不 emit', async () => {
    mocks.listBranches.mockResolvedValue({ branches: ['main'] })
    mocks.exportUiScript.mockRejectedValue({
      status: 400,
      data: { detail: { errors: ['步骤1: ai_tap 无法导出', '步骤3: set_var 不支持'] } },
    })
    const w = mountDlg()
    await flushPromises()
    await (w.vm as unknown as { onConfirm: () => Promise<void> }).onConfirm()
    await flushPromises()
    expect(w.text()).toContain('ai_tap')
    expect(w.text()).toContain('set_var 不支持')
    expect(w.emitted('exported')).toBeFalsy()
  })
})

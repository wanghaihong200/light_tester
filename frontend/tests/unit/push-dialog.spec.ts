import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import PushDialog from '../../src/components/PushDialog.vue'

vi.mock('../../src/api/repo', () => ({
  listBranches: vi.fn().mockResolvedValue({ branches: ['dev', 'main'] }),
  pushFiles: vi.fn().mockResolvedValue({ ok: true, branch: 'dev', commit_short: 'abc1234', pushed_files: ['T.java'] }),
}))

describe('PushDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('打开时拉分支并默认勾选非删除文件', async () => {
    const changes = [
      { path: 'A.java', status: 'added', tracked: false },
      { path: 'B.java', status: 'deleted', tracked: true },
    ] as any
    const w = mount(PushDialog, {
      props: { visible: true, projectId: 1, changes },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect((w.vm as any).branches).toEqual(['dev', 'main'])
    // 默认勾选非删除文件 A.java,排除 B.java
    expect((w.vm as any).selected).toEqual(['A.java'])
  })

  it('canPush 在有选中且有分支时为真', async () => {
    const w = mount(PushDialog, {
      props: { visible: false, projectId: 1, changes: [] },
      global: { plugins: [ElementPlus] },
    })
    // 空选中 + 默认 dev 分支 → canPush 假
    expect((w.vm as any).canPush).toBeFalsy()
  })

  it('点击推送调用 pushFiles 并 emit pushed', async () => {
    const { pushFiles } = await import('../../src/api/repo')
    const changes = [{ path: 'T.java', status: 'added', tracked: false }] as any
    const w = mount(PushDialog, {
      props: { visible: true, projectId: 2, changes },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    // 默认选中 T.java + 分支 dev → canPush 真(canPush 是 selected.length>0 && branch.trim(),JS && 返回 branch 字符串)
    expect((w.vm as any).canPush).toBeTruthy()
    // 触发推送
    await (w.vm as any).onPush()
    await flushPromises()
    expect(pushFiles).toHaveBeenCalledWith(2, ['T.java'], 'dev', expect.any(String))
    expect(w.emitted('pushed')).toBeTruthy()
  })
})

import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import PushDialog from '../../src/components/PushDialog.vue'

vi.mock('../../src/api/repo', () => ({
  listBranches: vi.fn().mockResolvedValue({ branches: ['dev', 'main'] }),
  pushFiles: vi.fn().mockResolvedValue({ ok: true, branch: 'dev', commit_short: 'abc1234', pushed_files: ['T.java'] }),
}))

describe('PushDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

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

  it('点击推送调用 pushFiles 并 emit pushed(缺省 kind=api)', async () => {
    const { pushFiles } = await import('../../src/api/repo')
    const changes = [{ path: 'T.java', status: 'added', tracked: false }] as any
    const w = mount(PushDialog, {
      props: { visible: true, projectId: 2, changes },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    // 默认选中 T.java + 分支 dev → canPush 真(JS && 返回 branch 字符串)
    expect((w.vm as any).canPush).toBeTruthy()
    await (w.vm as any).onPush()
    await flushPromises()
    expect(pushFiles).toHaveBeenCalledWith(2, ['T.java'], 'dev', expect.any(String), 'api')
    expect(w.emitted('pushed')).toBeTruthy()
  })

  // ── plan12 补遗:kind 透传 + 文案分支 + 成功写新记忆 key ──

  it('kind=app 时 listBranches/pushFiles 透传 app,默认文案为中性措辞,成功写新记忆 key', async () => {
    const { listBranches, pushFiles } = await import('../../src/api/repo')
    const changes = [{ path: 'T.java', status: 'added', tracked: false }] as any
    const w = mount(PushDialog, {
      props: { visible: true, projectId: 2, changes, kind: 'app' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect((w.vm as any).commitMessage).toContain('自动化测试推送')
    expect((w.vm as any).commitMessage).not.toContain('接口')
    await (w.vm as any).onPush()
    await flushPromises()
    expect(listBranches).toHaveBeenCalledWith(2, 'app')
    expect(pushFiles).toHaveBeenCalledWith(2, ['T.java'], 'dev', expect.any(String), 'app')
    expect(localStorage.getItem('push_branch_2_app')).toBe('dev')
    expect(localStorage.getItem('push_branch_2')).toBeNull() // 旧 key 只读迁移:成功推送也不回写
  })

  it('分支记忆按 kind 隔离;api 回退读旧 key;kind 变化时重读', async () => {
    localStorage.setItem('push_branch_3_web', 'web-branch')
    localStorage.setItem('push_branch_3', 'old-api-branch')

    const w = mount(PushDialog, {
      props: { visible: false, projectId: 3, changes: [], kind: 'web' },
      global: { plugins: [ElementPlus] },
    })
    expect((w.vm as any).branch).toBe('web-branch')

    // 切到 api:新 key 无记录 → 回退读旧 key(只读迁移)
    await w.setProps({ kind: 'api' })
    expect((w.vm as any).branch).toBe('old-api-branch')

    // 切到 app:无任何记忆 → 默认 dev
    await w.setProps({ kind: 'app' })
    expect((w.vm as any).branch).toBe('dev')
  })

  it('kind 变化时默认文案重算(复现真实挂载路径:api 起步再切 web)', async () => {
    const w = mount(PushDialog, {
      props: { visible: false, projectId: 4, changes: [], kind: 'api' },
      global: { plugins: [ElementPlus] },
    })
    expect((w.vm as any).commitMessage).toContain('AI 生成接口测试')
    await w.setProps({ kind: 'web' })
    expect((w.vm as any).commitMessage).toContain('自动化测试推送')
    expect((w.vm as any).commitMessage).not.toContain('接口')
  })
})

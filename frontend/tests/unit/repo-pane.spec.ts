import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('monaco-editor', () => ({
  editor: {
    create: vi.fn(() => ({ setValue: vi.fn(), getModel: () => ({ setValue: vi.fn() }), dispose: vi.fn() })),
    setModelLanguage: vi.fn(),
  },
}))

const repoApi = vi.hoisted(() => ({
  syncRepo: vi.fn(),
  listFiles: vi.fn().mockResolvedValue({ needs_sync: true }),
  readFile: vi.fn(),
  listChanges: vi.fn().mockResolvedValue({ files: [] }),
  listBranches: vi.fn(),
  pushFiles: vi.fn(),
}))
vi.mock('../../src/api/repo', () => repoApi)

import RepoPane from '../../src/components/RepoPane.vue'

describe('RepoPane', () => {
  beforeEach(() => vi.clearAllMocks())

  it('无 git_repo_url 时显示提示', () => {
    const w = mount(RepoPane, {
      props: { projectId: 1, project: { id: 1, name: 'p', git_repo_url: null } as any },
      global: { plugins: [ElementPlus] },
    })
    expect(w.text()).toContain('请先在项目列表编辑')
  })

  it('needs_sync 时显示同步占位', async () => {
    const w = mount(RepoPane, {
      props: { projectId: 1, project: { id: 1, name: 'p', git_repo_url: 'https://x' } as any },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(w.text()).toContain('同步工程')
    expect(w.text()).toContain('点击「同步工程」拉取仓库')
  })

  // 树(根 path='.' 对齐真实后端 rel.as_posix()):根匹配一切变更→红 / pom.xml 干净绿 / src 含变更红 / NewTest.java 精确匹配红
  const TREE: any = {
    name: 'demo-repo', path: '.', is_dir: true,
    children: [
      { name: 'pom.xml', path: 'pom.xml', is_dir: false, children: null },
      { name: 'src', path: 'src', is_dir: true, children: [
        { name: 'NewTest.java', path: 'src/NewTest.java', is_dir: false, children: null },
      ] },
    ],
  }

  it('树节点按变更状态着色,全部展开/收起切换子节点', async () => {
    repoApi.listFiles.mockResolvedValue(TREE)
    repoApi.listChanges.mockResolvedValue({
      files: [{ path: 'src/NewTest.java', status: 'added', tracked: false }],
    })
    repoApi.listBranches.mockResolvedValue({ branches: ['main', 'dev'] })

    const w = mount(RepoPane, {
      props: { projectId: 1, project: { id: 1, name: 'p', git_repo_url: 'https://x' } as any },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    // 默认收起:仅根节点可见,且根因空 path 前缀匹配恒红(仓库级汇总)
    expect(w.findAll('.node-changed, .node-clean').length).toBe(1)

    // 全部展开 → 4 个节点渲染,变更红/干净绿
    const btns = w.findAll('button')
    await btns.find(b => b.text().includes('全部展开'))!.trigger('click')
    await flushPromises()

    expect(w.findAll('.node-changed').map(n => n.text())).toEqual(['demo-repo', 'src', 'NewTest.java'])
    expect(w.findAll('.node-clean').map(n => n.text())).toEqual(['pom.xml'])

    // 全部收起 → 可见节点回到仅根(el-tree 子节点渲染过只隐藏不卸载,故按可见性断言)
    await w.findAll('button').find(b => b.text().includes('全部收起'))!.trigger('click')
    await flushPromises()
    expect(w.findAll('.node-changed, .node-clean').filter(n => n.isVisible()).length).toBe(1)
  })

  it('分支下拉 change 触发带 branch 参数的同步', async () => {
    repoApi.syncRepo.mockResolvedValue({ cloned: false, updated: true, failed: false, branch: 'dev', commit_short: 'abc1234' })
    repoApi.listBranches.mockResolvedValue({ branches: ['main', 'dev'] })

    const w = mount(RepoPane, {
      props: { projectId: 1, project: { id: 1, name: 'p', git_repo_url: 'https://x' } as any },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    const sel = w.findComponent({ name: 'ElSelect' })
    await sel.vm.$emit('change', 'dev')
    await flushPromises()

    expect(repoApi.syncRepo).toHaveBeenCalledWith(1, 'dev')
    // sync 成功后回填当前分支信息
    expect(w.text()).toContain('dev@abc1234')
  })
})

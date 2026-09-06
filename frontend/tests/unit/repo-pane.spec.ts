import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('monaco-editor', () => ({
  editor: {
    create: vi.fn(() => ({ setValue: vi.fn(), getModel: () => ({ setValue: vi.fn() }), dispose: vi.fn() })),
    setModelLanguage: vi.fn(),
  },
}))

// mock 出口覆盖组件会用到的 api/repo 全部具名导出(listAutomationRepos/putAutomationRepo 为 plan11 Task 8 新增)
const repoApi = vi.hoisted(() => ({
  syncRepo: vi.fn(),
  listFiles: vi.fn().mockResolvedValue({ needs_sync: true }),
  readFile: vi.fn(),
  listChanges: vi.fn().mockResolvedValue({ files: [] }),
  listBranches: vi.fn(),
  pushFiles: vi.fn(),
  listAutomationRepos: vi.fn().mockResolvedValue([]),
  putAutomationRepo: vi.fn(),
}))
vi.mock('../../src/api/repo', () => repoApi)

import RepoPane from '../../src/components/RepoPane.vue'

const mountPane = (projectId = 1) =>
  mount(RepoPane, {
    props: { projectId, project: { id: projectId, name: 'p', git_repo_url: 'https://x' } as any },
    global: { plugins: [ElementPlus] },
  })

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

    // plan11 起 syncRepo 携带 kind(缺省 api 分类的仓)
    expect(repoApi.syncRepo).toHaveBeenCalledWith(1, 'dev', 'api')
    // sync 成功后回填当前分支信息
    expect(w.text()).toContain('dev@abc1234')
  })

  // ── plan11 Task 8:接口/Web 双仓切换 + 仓配置表单 ──

  it('加载时拉仓配置并以 kind=api 拉文件树,APP 工程项禁用提示计划 12', async () => {
    repoApi.listAutomationRepos.mockResolvedValue([
      { id: 1, kind: 'api', repo_url: 'https://g/api.git', repo_token: 't' },
      { id: 2, kind: 'web', repo_url: 'https://g/web.git', repo_token: null },
    ])
    repoApi.listFiles.mockResolvedValue({ name: 'api', path: '', is_dir: true, children: [] })

    const w = mountPane()
    await flushPromises()

    expect(repoApi.listAutomationRepos).toHaveBeenCalledWith(1)
    expect(repoApi.listFiles).toHaveBeenCalledWith(1, 'api')
    // kind 切换器:接口/Web 可选,APP 禁用并提示计划 12 提供
    expect(w.text()).toContain('接口工程')
    expect(w.text()).toContain('Web工程')
    expect(w.text()).toContain('APP工程')
    expect(w.text()).toContain('计划 12 提供')
  })

  it('切到 Web 工程后文件树带 kind=web', async () => {
    repoApi.listAutomationRepos.mockResolvedValue([{ id: 2, kind: 'web', repo_url: 'https://g/web.git' }])
    repoApi.listFiles.mockResolvedValue({ name: 'web', path: '', is_dir: true, children: [] })

    const w = mountPane()
    await flushPromises()

    ;(w.vm as any).kind = 'web'
    await (w.vm as any).loadTree()
    await flushPromises()
    expect(repoApi.listFiles).toHaveBeenLastCalledWith(1, 'web')
  })

  it('当前 kind 无仓配置时提示未配置,保存仓配置调 PUT 并重拉配置与文件树', async () => {
    repoApi.listAutomationRepos
      .mockResolvedValueOnce([]) // 首次挂载:api 仓尚未配置
      .mockResolvedValue([{ id: 9, kind: 'api', repo_url: 'https://g/new.git', repo_token: null }])
    repoApi.listFiles.mockResolvedValue({ needs_config: true })
    repoApi.putAutomationRepo.mockResolvedValue({ id: 9, kind: 'api', repo_url: 'https://g/new.git', repo_token: null })

    const w = mountPane()
    await flushPromises()

    // 未配置:表单留空 + 提示
    expect(w.text()).toContain('未配置,保存后可用')
    expect(w.text()).toContain('该分类仓未配置,请先保存仓配置')

    const vm = w.vm as any
    vm.cfgUrl = 'https://g/new.git'
    vm.cfgToken = 'tk-1'
    await vm.saveConfig()
    await flushPromises()

    expect(repoApi.putAutomationRepo).toHaveBeenCalledWith(1, 'api', { repo_url: 'https://g/new.git', repo_token: 'tk-1' })
    // 保存后重拉配置(第 2 次)与文件树(挂载 1 次 + 保存后 1 次)
    expect(repoApi.listAutomationRepos).toHaveBeenCalledTimes(2)
    expect(repoApi.listFiles).toHaveBeenCalledTimes(2)
    // 重拉后不再显示未配置提示,且表单回填新仓地址
    expect(w.text()).not.toContain('未配置,保存后可用')
    expect((w.vm as any).cfgUrl).toBe('https://g/new.git')
  })

  it('拖拽分隔条横向调整文件树宽度并记忆,双击复位', async () => {
    localStorage.removeItem('repo-pane-tree-width')
    const w = mountPane()
    await flushPromises()

    const treeEl = () => w.find('.tree').element as HTMLElement
    expect(treeEl().style.width).toBe('260px')

    // mousedown 记起点,mousemove 按 dx 调宽(260 + 160-100 = 320),mouseup 落 localStorage
    await w.find('.splitter').trigger('mousedown', { clientX: 100 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 160 }))
    await flushPromises() // 等响应式宽度补丁到 DOM
    expect(treeEl().style.width).toBe('320px')
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 160 }))
    expect(localStorage.getItem('repo-pane-tree-width')).toBe('320')

    // 双击复位并落盘
    await w.find('.splitter').trigger('dblclick')
    await flushPromises()
    expect(treeEl().style.width).toBe('260px')
    expect(localStorage.getItem('repo-pane-tree-width')).toBe('260')
  })
})

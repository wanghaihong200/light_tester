import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'
import HomeView from '../../src/views/HomeView.vue'

vi.mock('../../src/api/projects', () => ({
  listProjects: vi.fn().mockResolvedValue([
    { id: 1, name: '商城系统', description: '电商核心', git_repo_url: null, created_at: '2026-08-15T10:00:00' },
    { id: 2, name: '风控平台', description: null, git_repo_url: null, created_at: '2026-08-14T09:00:00' },
  ]),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
}))

describe('HomeView', () => {
  it('渲染项目列表', async () => {
    const wrapper = mount(HomeView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('商城系统')
    expect(wrapper.text()).toContain('风控平台')
  })

  it('点击"新建项目"打开对话框', async () => {
    // el-dialog 默认 teleport 到 body,断言走 document.body 而非 wrapper
    const wrapper = mount(HomeView, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    await wrapper.find('button.new-project').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('新建项目')
  })

  it('编辑弹窗含 git_repo_url/git_token 字段;token 留空则不提交该字段', async () => {
    const { updateProject } = await import('../../src/api/projects')
    const wrapper = mount(HomeView, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    const editBtn = wrapper.findAll('button').find((b) => b.text() === '编辑')!
    await editBtn.trigger('click')
    await flushPromises()

    // body 里可能残留前一个用例未卸载的对话框,按标题"编辑项目"精确定位本用例的对话框
    const dlg = [...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('编辑项目'))!
    expect(dlg.textContent).toContain('Git 仓库')
    expect(dlg.textContent).toContain('Git Token')

    // 对话框内 input 顺序:名称 / Git 仓库 / Git Token(描述是 textarea)
    const inputs = dlg.querySelectorAll<HTMLInputElement>('.el-input__inner')
    expect(inputs[2].placeholder).toContain('留空表示不修改')
    inputs[1].value = 'http://localhost:8090/root/demo.git'
    inputs[1].dispatchEvent(new Event('input'))
    await flushPromises()

    const saveBtn = [...dlg.querySelectorAll('button')].find((b) => b.textContent === '保存')!
    saveBtn.click()
    await flushPromises()

    expect(updateProject).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ git_repo_url: 'http://localhost:8090/root/demo.git' }),
    )
    // token 留空 → payload 不含 git_token(后端 exclude_unset 语义:不出现即不修改)
    expect((updateProject as ReturnType<typeof vi.fn>).mock.calls[0][1]).not.toHaveProperty('git_token')
  })
})

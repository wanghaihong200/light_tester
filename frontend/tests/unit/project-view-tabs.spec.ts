import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import ProjectView from '../../src/views/ProjectView.vue'

vi.mock('../../src/api/projects', () => ({
  listProjects: vi.fn().mockResolvedValue([
    { id: 1, name: '商城系统', description: '电商核心', git_repo_url: null, created_at: '2026-08-15T10:00:00' },
  ]),
}))

// 四个子面板各自拉数据,与本用例无关,全部桩掉;成员弹窗含 el-table 作用域插槽,
// 本用例不装 Element Plus(裸渲染会触发插槽解构报错),同样桩掉
const stubs = { MindmapPane: true, DocumentsPane: true, JobsPane: true, RepoPane: true, ProjectMembersDialog: true }

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: ProjectView }],
  })
  await router.push(path)
  await router.isReady()
  return mount(ProjectView, { global: { plugins: [router], stubs } })
}

// 临时形态:页签机制已删除,仅保留页面文案断言(Task 3 全量重写本文件)
describe('ProjectView 页面渲染', () => {
  it('挂载后显示项目名;未命中项目显示「项目不存在」', async () => {
    const wrapper = await mountAt('/projects/1')
    await flushPromises()
    expect(wrapper.text()).toContain('商城系统')

    const bad = await mountAt('/projects/99')
    await flushPromises()
    expect(bad.text()).toContain('项目不存在')
  })
})

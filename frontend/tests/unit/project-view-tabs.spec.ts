import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import ProjectView from '../../src/views/ProjectView.vue'
import { resetTabs, useTabs } from '../../src/composables/useTabs'

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

describe('ProjectView 页签注册', () => {
  beforeEach(() => resetTabs())

  it('挂载后把项目注册进布局壳页签;未命中项目回填「未知项目」', async () => {
    const wrapper = await mountAt('/projects/1')
    await flushPromises()
    const { tabs } = useTabs()
    expect(tabs.value.some((t) => t.key === 'project-1' && t.name === '商城系统')).toBe(true)
    expect(wrapper.text()).toContain('商城系统')

    resetTabs()
    const bad = await mountAt('/projects/99')
    await flushPromises()
    expect(tabs.value.some((t) => t.key === 'project-99' && t.name === '未知项目')).toBe(true)
    expect(bad.text()).toContain('项目不存在')
  })
})

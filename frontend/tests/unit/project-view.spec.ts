import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, onMounted } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import ProjectView from '../../src/views/ProjectView.vue'

vi.mock('../../src/api/projects', () => ({
  listProjects: vi.fn().mockResolvedValue([
    { id: 1, name: '商城系统', description: '电商核心', git_repo_url: null, created_at: '2026-08-15T10:00:00' },
  ]),
}))

// 与真实路由表同构的测试路由(子路由直指 Pane,与 src/router/index.ts 的 component 指向一一对应;
// 组件替换为可计数的 stub)
function makeSectionStub(tag: string, onMountedCb?: () => void) {
  return defineComponent({
    props: { projectId: Number, projectName: String, project: Object },
    setup(_, { emit }) {
      onMounted(() => { onMountedCb?.(); if (tag === 'jobs') emit('staging-accepted') })
      return () => h('div', { class: `pane-stub-${tag}` })
    },
    emits: ['staging-accepted'],
  })
}

const mounts: Record<string, number> = {}
function counter(tag: string) {
  return () => { mounts[tag] = (mounts[tag] ?? 0) + 1 }
}

async function mountAt(path: string): Promise<{ w: ReturnType<typeof mount>; router: Router }> {
  // 清空计数:重挂断言只反映本用例的路由行为,不依赖用例声明顺序
  for (const k of Object.keys(mounts)) delete mounts[k]
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/projects/:id',
        component: ProjectView,
        children: [
          { path: '', redirect: (to) => ({ name: 'project-cases', params: to.params }) },
          { path: 'cases', name: 'project-cases', component: makeSectionStub('cases', counter('cases')) },
          { path: 'knowledge', name: 'project-knowledge', component: makeSectionStub('knowledge', counter('knowledge')) },
          { path: 'ai/jobs', name: 'project-ai-jobs', component: makeSectionStub('jobs', counter('jobs')) },
          { path: 'ai/repo', name: 'project-ai-repo', component: makeSectionStub('repo', counter('repo')) },
          { path: 'ai/cross', name: 'project-ai-cross', component: makeSectionStub('cross', counter('cross')) },
          { path: 'ui/web', name: 'project-ui-web', component: makeSectionStub('web', counter('web')) },
        ],
      },
    ],
  })
  await router.push(path)
  await router.isReady()
  // 成员弹窗含 el-table 作用域插槽,本用例不装 Element Plus(裸渲染会触发插槽解构报错),桩掉
  const w = mount(ProjectView, {
    global: { plugins: [router], stubs: { ProjectMembersDialog: true } },
  })
  await flushPromises()
  return { w, router }
}

describe('ProjectView 壳', () => {
  it('页头保留:项目名/描述/成员按钮;未命中项目显示「项目不存在」', async () => {
    const { w } = await mountAt('/projects/1/cases')
    expect(w.find('.panel-title').text()).toBe('商城系统')
    expect(w.text()).toContain('电商核心')
    expect(w.find('[data-test="members-btn"]').exists()).toBe(true)

    const { w: bad } = await mountAt('/projects/99/cases')
    expect(bad.find('.panel-title').text()).toBe('项目不存在')
    bad.unmount()
    w.unmount()
  })

  it.each([
    ['/projects/1/cases', 'pane-stub-cases'],
    ['/projects/1/knowledge', 'pane-stub-knowledge'],
    ['/projects/1/ai/jobs', 'pane-stub-jobs'],
    ['/projects/1/ai/repo', 'pane-stub-repo'],
    ['/projects/1/ai/cross', 'pane-stub-cross'],
    ['/projects/1/ui/web', 'pane-stub-web'],
  ])('%s 渲染对应功能段', async (path, cls) => {
    const { w } = await mountAt(path)
    expect(w.find(`.${cls}`).exists()).toBe(true)
    w.unmount()
  })

  it('壳内功能段切换只重挂功能段,壳不重挂(panel-title 不闪烁重载)', async () => {
    const { w, router } = await mountAt('/projects/1/cases')
    const titleEl = w.find('.panel-title').element
    await router.push('/projects/1/ai/jobs')
    await flushPromises()
    expect(w.find('.pane-stub-jobs').exists()).toBe(true)
    expect(w.find('.panel-title').element).toBe(titleEl) // 同一 DOM 节点 = 壳未重挂
    w.unmount()
  })

  it('暂存转正(staging-accepted)后切回 cases:导图重挂(key 计数),其他段不受影响', async () => {
    // jobs stub 挂载即 emit('staging-accepted')(见 makeSectionStub)
    const { w, router } = await mountAt('/projects/1/ai/jobs')
    await flushPromises()
    expect(mounts['cases']).toBeUndefined()

    await router.push('/projects/1/cases')
    await flushPromises()
    expect(mounts['cases']).toBe(1)

    // 再次转正场景:jobs 再挂一次(emit 一次),切回 cases 再重挂一次
    await router.push('/projects/1/ai/jobs')
    await flushPromises()
    await router.push('/projects/1/cases')
    await flushPromises()
    expect(mounts['cases']).toBe(2)
    w.unmount()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { defineComponent, h, onMounted } from 'vue'
import AppLayout from '../../src/components/layout/AppLayout.vue'

vi.mock('../../src/api/projects', () => ({
  listProjects: vi.fn().mockResolvedValue([
    { id: 1, name: '商城系统', description: null, git_repo_url: null, created_at: '2026-08-15T10:00:00' },
  ]),
}))

const routes = [
  { path: '/', component: { template: '<div class="home-stub">home</div>' } },
  { path: '/projects/:id', component: { template: '<div class="project-stub">project</div>' } },
]

async function mountLayout(): Promise<{ wrapper: ReturnType<typeof mount>; router: Router }> {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(AppLayout, {
    global: { plugins: [router, ElementPlus], stubs: { 'router-view': true } },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('AppLayout 布局壳', () => {
  it('渲染侧栏/顶栏/页脚;页签栏已移除', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.find('.side-menu').exists()).toBe(true)
    expect(wrapper.find('.top-header').exists()).toBe(true)
    expect(wrapper.find('.tab-bar').exists()).toBe(false)
    expect(wrapper.text()).toContain('Powered by Vue3 + FastAPI')
  })

  it('顶栏折叠钮发出 toggle-collapse', async () => {
    const { wrapper } = await mountLayout()
    await wrapper.find('.collapse-btn').trigger('click')
    expect(wrapper.find('.side-menu').classes()).toContain('collapsed')
  })

  it('项目间直达(参数变化):router-view 按 id 重挂载,不复用实例', async () => {
    let projectMounts = 0
    const CountingProject = defineComponent({
      setup() {
        onMounted(() => { projectMounts++ })
        return () => h('div', 'project')
      },
    })
    // 不 stub router-view:需要真实渲染路由组件来统计 mount 次数
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div class="home-stub">home</div>' } },
        { path: '/projects/:id', component: CountingProject },
      ],
    })
    await router.push('/projects/1')
    await router.isReady()
    mount(AppLayout, { global: { plugins: [router] } })
    await flushPromises()
    expect(projectMounts).toBe(1)

    await router.push('/projects/2')
    await flushPromises()
    expect(projectMounts).toBe(2)
  })

  it('同一项目内路径查询变化不重挂(本任务用 query 模拟;子路由语义 Task 3 落地)', async () => {
    let projectMounts = 0
    const CountingProject = defineComponent({
      setup() {
        onMounted(() => { projectMounts++ })
        return () => h('div', 'project')
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div class="home-stub">home</div>' } },
        { path: '/projects/:id', component: CountingProject },
      ],
    })
    await router.push('/projects/1')
    await router.isReady()
    mount(AppLayout, { global: { plugins: [router] } })
    await flushPromises()
    expect(projectMounts).toBe(1)

    await router.push({ path: '/projects/1', query: { keep: '1' } })
    await flushPromises()
    expect(projectMounts).toBe(1)
  })
})

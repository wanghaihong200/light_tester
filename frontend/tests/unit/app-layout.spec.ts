import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { defineComponent, h, onMounted } from 'vue'
import AppLayout from '../../src/components/layout/AppLayout.vue'
import { resetTabs, useTabs } from '../../src/composables/useTabs'

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
    global: { plugins: [router], stubs: { 'router-view': true } },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('AppLayout 布局壳', () => {
  beforeEach(() => resetTabs())

  it('渲染侧栏/顶栏/页签/页脚;只有首页页签时无关闭钮', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.find('.side-menu').exists()).toBe(true)
    expect(wrapper.find('.top-header').exists()).toBe(true)
    expect(wrapper.find('.tab-bar').exists()).toBe(true)
    expect(wrapper.text()).toContain('Powered by Vue3 + FastAPI')
    expect(wrapper.findAll('.tab-pill')).toHaveLength(1)
    expect(wrapper.find('.tab-pill .tab-close').exists()).toBe(false)
  })

  it('顶栏折叠钮发出 toggle-collapse', async () => {
    const { wrapper } = await mountLayout()
    await wrapper.find('.collapse-btn').trigger('click')
    expect(wrapper.find('.side-menu').classes()).toContain('collapsed')
  })

  it('进入项目路由:自动开占位页签并高亮、可关', async () => {
    const { wrapper, router } = await mountLayout()
    await router.push('/projects/1')
    await flushPromises()
    const pills = wrapper.findAll('.tab-pill')
    expect(pills).toHaveLength(2)
    expect(pills[1].classes()).toContain('active')
    expect(pills[1].find('.tab-close').exists()).toBe(true)
  })

  it('关闭活跃项目页签:跳回相邻页签(首页)', async () => {
    const { wrapper, router } = await mountLayout()
    useTabs().openProject(1, '商城系统')
    await router.push('/projects/1')
    await flushPromises()
    await wrapper.findAll('.tab-pill')[1].find('.tab-close').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
    expect(useTabs().tabs.value.map((t) => t.key)).toEqual(['home'])
  })

  it('项目间直达(参数变化):router-view 按路径重挂载,不复用实例', async () => {
    let projectMounts = 0
    const CountingProject = defineComponent({
      setup() {
        onMounted(() => {
          projectMounts++
        })
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
})

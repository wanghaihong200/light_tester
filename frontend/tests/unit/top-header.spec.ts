import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { ApiError } from '../../src/api/client'
import { resetAuth, useAuth } from '../../src/composables/useAuth'
import TopHeader from '../../src/components/layout/TopHeader.vue'

// mock api 层:auth 控制 fetchMe(/auth/me)结果,projects 控制切换下拉/面包屑名
const mocks = vi.hoisted(() => ({ me: vi.fn(), listProjects: vi.fn() }))
vi.mock('../../src/api/auth', () => ({ authApi: { login: vi.fn(), me: mocks.me } }))
vi.mock('../../src/api/projects', () => ({ listProjects: mocks.listProjects }))

const PROJECTS = [
  { id: 1, name: '商城系统', description: null, git_repo_url: null, created_at: '2026-08-15T10:00:00' },
  { id: 2, name: '风控平台', description: null, git_repo_url: null, created_at: '2026-08-14T09:00:00' },
]

function me(over: Record<string, unknown> = {}) {
  return { id: 2, username: 'wang', display_name: '王测试', is_admin: false, is_active: true, ...over }
}

// el-select 面板 teleport 到 body:卸载必须无条件执行(断言失败也不能残留,否则污染后续用例)
const mounted: VueWrapper[] = []
afterEach(() => {
  mounted.splice(0).forEach((w) => w.unmount())
})

async function mountHeader(path = '/'): Promise<{ w: VueWrapper; router: Router }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div/>' } },
      { path: '/projects/:id', component: { template: '<div/>' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(TopHeader, {
    props: { collapsed: false },
    global: { plugins: [router, ElementPlus] },
  })
  mounted.push(w)
  await flushPromises()
  return { w, router }
}

describe('TopHeader 顶栏', () => {
  beforeEach(() => {
    resetAuth()
    localStorage.clear()
    location.hash = '#/'
    mocks.me.mockReset()
    mocks.listProjects.mockReset().mockResolvedValue(PROJECTS)
  })

  // —— 用户区(原 5 用例平移,仅挂载方式变化) ——
  it('无 token 不拉 me、不渲染用户区', async () => {
    const { w } = await mountHeader()
    expect(mocks.me).not.toHaveBeenCalled()
    expect(w.find('.user-area').exists()).toBe(false)
  })

  it('有 token 挂载即 fetchMe 并显示 display_name;非管理员无「用户管理」', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    const { w } = await mountHeader()
    expect(mocks.me).toHaveBeenCalledOnce()
    expect(w.find('[data-test="user-name"]').text()).toBe('王测试')
    expect(w.find('[data-test="admin-link"]').exists()).toBe(false)
  })

  it('管理员才显示「用户管理」,链接指向 #/users', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me({ id: 1, username: 'admin', display_name: '管理员', is_admin: true }))
    const { w } = await mountHeader()
    expect(w.find('[data-test="admin-link"]').attributes('href')).toBe('#/users')
  })

  it('退出:清 token 与用户态、跳 #/login、用户区消失', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    const { w } = await mountHeader()
    await w.find('[data-test="logout"]').trigger('click')
    await flushPromises()
    expect(localStorage.getItem('tt_token')).toBeNull()
    expect(useAuth().user.value).toBeNull()
    expect(location.hash).toBe('#/login')
    expect(w.find('.user-area').exists()).toBe(false)
  })

  it('fetchMe 失败(401 踢登录)不阻塞布局', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockRejectedValue(new ApiError(401, '未登录或登录已过期'))
    const { w } = await mountHeader()
    await flushPromises()
    expect(w.find('.user-area').exists()).toBe(false)
  })

  // —— 项目切换下拉(本任务新增) ——
  // 注:本仓 element-plus 2.14.4 新版 select 的 placeholder/选中文案渲染在
  // `.el-select__placeholder` span 里,input 无 placeholder 属性且 value 恒为空
  it('任何路由都渲染切换下拉;首页态选中为空、placeholder「切换项目」', async () => {
    const { w } = await mountHeader('/')
    expect(w.find('[data-test="project-switcher"]').exists()).toBe(true)
    expect(w.find('.project-switcher input').exists()).toBe(true)
    expect(w.find('.project-switcher .el-select__placeholder').text()).toBe('切换项目')
  })

  it('项目路由:下拉选中当前项目,面包屑显示「首页 / 名称」', async () => {
    const { w } = await mountHeader('/projects/1')
    await flushPromises()
    expect(w.find('.project-switcher .el-select__placeholder').text()).toBe('商城系统')
    expect(w.find('.crumb-current').text()).toBe('商城系统')
  })

  it('选择另一项目:发出 navigate 到其默认页 /projects/<id>', async () => {
    const { w } = await mountHeader('/projects/1')
    // el-select 下拉面板 teleport 到 body,操作走 DOM
    await w.find('.project-switcher input').trigger('click')
    await flushPromises()
    const opt = [...document.querySelectorAll('.el-select-dropdown__item')].find(
      (el) => el.textContent === '风控平台',
    )!
    expect(opt).toBeTruthy()
    ;(opt as HTMLElement).click()
    await flushPromises()
    expect(w.emitted('navigate')![0]).toEqual(['/projects/2'])
  })

  it('面包屑名来自 listProjects 派生;接口失败不阻塞布局', async () => {
    mocks.listProjects.mockRejectedValue(new Error('network down'))
    const { w } = await mountHeader('/projects/1')
    await flushPromises()
    expect(w.find('.crumb-current').exists()).toBe(false)
    expect(w.find('[data-test="project-switcher"]').exists()).toBe(true)
  })
})

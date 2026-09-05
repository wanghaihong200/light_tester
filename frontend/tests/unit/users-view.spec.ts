import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import { resetAuth, useAuth } from '../../src/composables/useAuth'
import UserProjectsDialog from '../../src/components/UserProjectsDialog.vue'
import UsersView from '../../src/views/UsersView.vue'

// mock api 层(usersApi + authApi.me,后者供 useAuth().fetchMe 补拉;projects/listProjects 供授权弹窗)
const mocks = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), update: vi.fn(), me: vi.fn(), projects: vi.fn(), listProjects: vi.fn() }))
vi.mock('../../src/api/users', () => ({ usersApi: { list: mocks.list, create: mocks.create, update: mocks.update, projects: mocks.projects } }))
vi.mock('../../src/api/auth', () => ({ authApi: { login: vi.fn(), me: mocks.me } }))
vi.mock('../../src/api/projects', () => ({ listProjects: mocks.listProjects }))

const USERS = [
  { id: 1, username: 'admin', display_name: '管理员', is_admin: true, is_active: true },
  { id: 2, username: 'wang', display_name: '王测试', is_admin: false, is_active: false },
]

function me(over: Record<string, unknown> = {}) {
  return { id: 1, username: 'admin', display_name: '管理员', is_admin: true, is_active: true, ...over }
}

// 独立 memory 路由: UsersView 用 useRouter() 兜底跳转,断言路由结果而非真实 hash
async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/users', name: 'users', component: { template: '<div />' } },
    ],
  })
  router.push('/users')
  await router.isReady()
  const w = mount(UsersView, {
    attachTo: document.body, // el-dialog teleport 到 body,断言走 document
    global: { plugins: [ElementPlus, router] },
  })
  await flushPromises()
  return { w, router }
}

describe('UsersView 用户管理页', () => {
  beforeEach(() => {
    resetAuth()
    localStorage.clear()
    mocks.list.mockReset()
    mocks.create.mockReset()
    mocks.update.mockReset()
    mocks.me.mockReset()
    mocks.projects.mockReset()
    mocks.listProjects.mockReset()
  })

  it('admin 进入:fetchMe 后拉取列表并渲染用户/操作', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    mocks.list.mockResolvedValue(USERS)
    const { w } = await mountView()
    expect(mocks.me).toHaveBeenCalledOnce()
    expect(mocks.list).toHaveBeenCalledOnce()
    expect(w.find('[data-test="users-table"]').exists()).toBe(true)
    expect(w.text()).toContain('王测试')
    expect(w.findAll('[data-test="toggle-active"]').length).toBe(2)
    w.unmount()
  })

  it('非 admin 访问:提示需要管理员权限、回首页、不拉列表', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me({ id: 2, username: 'wang', display_name: '王测试', is_admin: false }))
    const warnSpy = vi.spyOn(ElMessage, 'warning')
    const { w, router } = await mountView()
    expect(warnSpy).toHaveBeenCalledWith('需要管理员权限')
    expect(router.currentRoute.value.path).toBe('/')
    expect(mocks.list).not.toHaveBeenCalled()
    w.unmount()
  })

  it('新建用户:提交 usersApi.create 并重拉列表', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    mocks.list.mockResolvedValue(USERS)
    mocks.create.mockResolvedValue({ id: 3, username: 'li', display_name: '李工', is_admin: false, is_active: true })
    const { w } = await mountView()
    await w.find('[data-test="new-user"]').trigger('click')
    await flushPromises()
    // 弹窗 teleport 到 body,取本用例对话框内输入框填写
    const dlg = [...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('新建用户'))!
    const inputs = dlg.querySelectorAll<HTMLInputElement>('.el-input__inner')
    const setVal = (el: HTMLInputElement, v: string) => {
      el.value = v
      el.dispatchEvent(new Event('input'))
    }
    setVal(inputs[0], 'li')
    setVal(inputs[1], '李工')
    setVal(inputs[2], 'secret66')
    ;[...dlg.querySelectorAll('button')].find((b) => b.textContent === '保存')!.click()
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith({ username: 'li', display_name: '李工', password: 'secret66' })
    expect(mocks.list).toHaveBeenCalledTimes(2) // 进页一次 + 建号后重拉
    w.unmount()
  })

  it('禁用操作:update 成功后重拉列表;409 时透出后端 detail 且不重拉', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    mocks.list.mockResolvedValue(USERS)
    const { w } = await mountView()
    // 成功路径:禁用 wang(id=2)
    mocks.update.mockResolvedValueOnce({ ...USERS[1], is_active: true })
    await w.findAll('[data-test="toggle-active"]')[1].trigger('click')
    await flushPromises()
    expect(mocks.update).toHaveBeenCalledWith(2, { is_active: true })
    expect(mocks.list).toHaveBeenCalledTimes(2)

    // 失败路径:后端 409(detail 原样透出),列表不重拉
    const errSpy = vi.spyOn(ElMessage, 'error')
    mocks.update.mockRejectedValueOnce(new ApiError(409, '不能操作自己的账号'))
    await w.findAll('[data-test="toggle-active"]')[0].trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('不能操作自己的账号')
    expect(mocks.list).toHaveBeenCalledTimes(2)
    w.unmount()
  })

  it('项目权限:点击行内按钮打开授权弹窗,props 传该行用户 id/username', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    mocks.list.mockResolvedValue(USERS)
    mocks.projects.mockResolvedValue([])
    mocks.listProjects.mockResolvedValue([]) // 弹窗 visible→true 会并行拉授权+全量项目
    const { w } = await mountView()
    await w.findAll('[data-test="assign-perm"]')[1].trigger('click') // wang(id=2)行
    await flushPromises()
    const dlg = w.findComponent(UserProjectsDialog)
    expect(dlg.exists()).toBe(true)
    expect(dlg.props('userId')).toBe(2)
    expect(dlg.props('username')).toBe('wang')
    expect(dlg.props('visible')).toBe(true)
    expect(mocks.projects).toHaveBeenCalledWith(2)
    w.unmount()
  })

  it('useAuth 单例:user 已加载且非 admin 时,路由守卫把 /users 拦回 home', async () => {
    // 守卫第一层(同步)口径:user 已加载 → 直接拦;未加载(刷新直达)→ 放行交 UsersView 自检
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me({ id: 2, username: 'wang', display_name: '王测试', is_admin: false }))
    // 走真实 router(含 src/router 的 beforeEach):只断言导航结果,不挂载组件(同 router.spec.ts 口径)
    const router = (await import('../../src/router')).default
    await useAuth().fetchMe() // 先让 useAuth 单例装载非 admin 用户(模拟已登录的非 admin 会话)
    await router.push('/users')
    expect(router.currentRoute.value.name).toBe('home')
  })
})

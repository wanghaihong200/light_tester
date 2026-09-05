import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import UserProjectsDialog from '../../src/components/UserProjectsDialog.vue'

// mock api 层:usersApi(projects)+ membersApi + 项目列表 listProjects(与 HomeView 同源模块)
const mocks = vi.hoisted(() => ({ projects: vi.fn(), list: vi.fn(), add: vi.fn(), changeRole: vi.fn(), remove: vi.fn(), listProjects: vi.fn() }))
vi.mock('../../src/api/users', () => ({ usersApi: { projects: mocks.projects } }))
vi.mock('../../src/api/members', () => ({
  membersApi: { list: mocks.list, add: mocks.add, changeRole: mocks.changeRole, remove: mocks.remove },
}))
vi.mock('../../src/api/projects', () => ({ listProjects: mocks.listProjects }))

const USER_ID = 7
const USERNAME = 'wang'

const PROJECTS = [
  { id: 1, name: 'alpha', description: null, git_repo_url: null, created_at: '2026-01-01T00:00:00' },
  { id: 2, name: 'beta', description: null, git_repo_url: null, created_at: '2026-01-02T00:00:00' },
  { id: 3, name: 'gamma', description: null, git_repo_url: null, created_at: '2026-01-03T00:00:00' },
]
// 只授权了 alpha(owner),beta/gamma 未授权(role=null 行,默认 viewer + 添加)
const GRANTED = [{ project_id: 1, project_name: 'alpha', role: 'owner' }]

function mockData(granted = GRANTED) {
  mocks.projects.mockResolvedValue(granted)
  mocks.listProjects.mockResolvedValue(PROJECTS)
}

function mountDialog(visible = true) {
  const w = mount(UserProjectsDialog, {
    attachTo: document.body, // el-dialog teleport 到 body,断言走 document
    props: { visible, userId: USER_ID, username: USERNAME },
    global: { plugins: [ElementPlus] },
  })
  return flushPromises().then(() => w)
}

function dialogEl(): HTMLElement {
  return [...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('项目权限'))!
}

function tableRows(): HTMLElement[] {
  return [...dialogEl().querySelectorAll('.el-table__body-wrapper tbody tr')]
}

// 按项目名找行内 select 组件实例(单表里每行一个 role-select,经 data-project-id 对应)
function selectOf(w: Awaited<ReturnType<typeof mountDialog>>, projectName: string) {
  const pid = tableRows()
    .find((r) => r.textContent?.includes(projectName))!
    .querySelector('[data-test="role-select"]')!
    .getAttribute('data-project-id')
  return w.findAllComponents({ name: 'ElSelect' }).find((c) => c.attributes('data-project-id') === pid)!
}

// select 当前显示值(父组件 :model-value 的实际取值)
function selectValue(w: Awaited<ReturnType<typeof mountDialog>>, projectName: string) {
  return selectOf(w, projectName).props('modelValue')
}

// 驱动行内 select 改值(emit update:modelValue → onRoleInput:未授权行落草稿 / 已授权行走 onRoleChange)
async function setRowDraft(w: Awaited<ReturnType<typeof mountDialog>>, projectName: string, role: string) {
  await selectOf(w, projectName).vm.$emit('update:modelValue', role)
  await flushPromises()
}

function rowBtn(projectName: string, test: string): HTMLButtonElement {
  const row = tableRows().find((r) => r.textContent?.includes(projectName))!
  return row.querySelector<HTMLButtonElement>(`[data-test="${test}"]`)!
}

describe('UserProjectsDialog 用户项目授权弹窗', () => {
  beforeEach(() => {
    mocks.projects.mockReset()
    mocks.list.mockReset()
    mocks.add.mockReset()
    mocks.changeRole.mockReset()
    mocks.remove.mockReset()
    mocks.listProjects.mockReset()
  })

  it('打开时并行拉授权列表+全量项目,表格渲染全部项目(已授权=角色下拉+移除,未授权=下拉+添加)', async () => {
    mockData()
    const w = await mountDialog()
    expect(mocks.projects).toHaveBeenCalledWith(USER_ID)
    expect(mocks.listProjects).toHaveBeenCalledOnce()
    // 全量项目 ∩ 授权:3 行,alpha 已授权(移除),beta/gamma 未授权(添加)
    expect(tableRows().length).toBe(3)
    expect(dialogEl().textContent).toContain('alpha')
    expect(dialogEl().textContent).toContain('beta')
    expect(dialogEl().textContent).toContain('gamma')
    expect(document.querySelectorAll('[data-test="role-select"]').length).toBe(3)
    expect(document.querySelectorAll('[data-test="remove-btn"]').length).toBe(1)
    expect(document.querySelectorAll('[data-test="assign-btn"]').length).toBe(2)
    w.unmount()
  })

  it('visible=false 不拉取', async () => {
    const w = await mountDialog(false)
    expect(mocks.projects).not.toHaveBeenCalled()
    expect(mocks.listProjects).not.toHaveBeenCalled()
    w.unmount()
  })

  it('未授权行选 editor 点「添加」:add 收到 (project_id, username, role),成功后重拉并 emit changed', async () => {
    mockData()
    const w = await mountDialog()
    await setRowDraft(w, 'beta', 'editor')
    mocks.projects.mockClear()
    rowBtn('beta', 'assign-btn')!.click()
    await flushPromises()
    expect(mocks.add).toHaveBeenCalledWith(2, USERNAME, 'editor')
    expect(mocks.projects).toHaveBeenCalledTimes(1) // 重拉授权列表
    expect(w.emitted('changed')).toBeTruthy()
    w.unmount()
  })

  it('未授权行不动下拉直接「添加」:默认 viewer', async () => {
    mockData()
    const w = await mountDialog()
    rowBtn('gamma', 'assign-btn')!.click()
    await flushPromises()
    expect(mocks.add).toHaveBeenCalledWith(3, USERNAME, 'viewer')
    w.unmount()
  })

  it('已授权行改角色(走行内 select 真实路径):changeRole 收到 (project_id, userId, role),成功后重拉并显示新角色', async () => {
    // 首次拉取授权为 owner,changeRole 成功重拉后返回 editor
    mocks.projects
      .mockResolvedValueOnce(GRANTED)
      .mockResolvedValueOnce([{ project_id: 1, project_name: 'alpha', role: 'editor' }])
    mocks.listProjects.mockResolvedValue(PROJECTS)
    const w = await mountDialog()
    await setRowDraft(w, 'alpha', 'editor') // onRoleInput → 已授权分支 → onRoleChange
    expect(mocks.changeRole).toHaveBeenCalledWith(1, USER_ID, 'editor') // 第二参=本弹窗用户
    expect(mocks.projects).toHaveBeenCalledTimes(2) // 成功后重拉授权列表
    expect(selectValue(w, 'alpha')).toBe('editor') // reload 后下拉显示新角色
    expect(w.emitted('changed')).toBeTruthy()
    w.unmount()
  })

  it('已授权行「移除」:remove 收到 (project_id, userId),成功后重拉并 emit changed', async () => {
    mockData()
    const w = await mountDialog()
    mocks.projects.mockClear()
    rowBtn('alpha', 'remove-btn')!.click()
    await flushPromises()
    expect(mocks.remove).toHaveBeenCalledWith(1, USER_ID)
    expect(mocks.projects).toHaveBeenCalledTimes(1)
    expect(w.emitted('changed')).toBeTruthy()
    w.unmount()
  })

  it('已授权行改角色被拒(409 末位 owner):透出后端 detail、下拉显示值回滚、不重拉', async () => {
    mockData()
    const errSpy = vi.spyOn(ElMessage, 'error')
    const w = await mountDialog()
    mocks.changeRole.mockRejectedValue(new ApiError(409, '项目至少需要一名 owner'))
    await setRowDraft(w, 'alpha', 'viewer') // onRoleInput → 已授权分支 → onRoleChange
    expect(mocks.changeRole).toHaveBeenCalledWith(1, USER_ID, 'viewer')
    expect(errSpy).toHaveBeenCalledWith('项目至少需要一名 owner')
    expect(selectValue(w, 'alpha')).toBe('owner') // 回滚:下拉显示值恢复原角色,不残留假角色
    expect(tableRows()[0].textContent).toContain('owner')
    expect(w.emitted('changed')).toBeFalsy()
    expect(mocks.projects).toHaveBeenCalledTimes(1) // 失败不重拉
    w.unmount()
  })

  it('过滤「alp」:表格只剩 alpha 行(本地过滤)', async () => {
    mockData()
    const w = await mountDialog()
    // el-input 的透传属性可能落在原生 input 上(Element Plus 绑 attrs 到 input),两种取法兜底
    const input = (dialogEl().querySelector<HTMLInputElement>('input[data-test="project-filter"]') ??
      dialogEl().querySelector<HTMLInputElement>('[data-test="project-filter"] input'))!
    input.value = 'alp'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    const rows = tableRows()
    expect(rows.length).toBe(1)
    expect(rows[0].textContent).toContain('alpha')
    w.unmount()
  })
})

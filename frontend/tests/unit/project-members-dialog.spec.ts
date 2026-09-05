import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import ProjectMembersDialog from '../../src/components/ProjectMembersDialog.vue'
import UserSearchSelect from '../../src/components/UserSearchSelect.vue'

// mock api 层:捕获入参、控制成功/失败
const mocks = vi.hoisted(() => ({ list: vi.fn(), add: vi.fn(), changeRole: vi.fn(), remove: vi.fn(), search: vi.fn() }))
vi.mock('../../src/api/members', () => ({
  membersApi: { list: mocks.list, add: mocks.add, changeRole: mocks.changeRole, remove: mocks.remove },
}))
vi.mock('../../src/api/users', () => ({
  usersApi: { search: mocks.search },
}))

const MEMBERS = [
  { id: 11, user_id: 1, username: 'admin', display_name: '管理员', role: 'owner' },
  { id: 12, user_id: 2, username: 'wang', display_name: '王测试', role: 'viewer' },
]

function mountDialog(visible = true) {
  const w = mount(ProjectMembersDialog, {
    attachTo: document.body, // el-dialog teleport 到 body,断言走 document
    props: { visible, projectId: 1 },
    global: { plugins: [ElementPlus] },
  })
  return flushPromises().then(() => w)
}

function dialogEl(): HTMLElement {
  return [...document.querySelectorAll('.el-dialog')].find((d) => d.textContent?.includes('项目成员'))!
}

// 驱动添加行的 UserSearchSelect:远程搜索 → 点选下拉项(驱动方式同 user-search-select.spec)
async function selectUser(w: Awaited<ReturnType<typeof mountDialog>>, name: string) {
  await (w.findComponent(UserSearchSelect).vm as any).remoteMethod(name)
  await flushPromises()
  ;[...document.querySelectorAll('.el-select-dropdown__item')]
    .find((el) => el.textContent?.includes(name))!
    .click()
  await flushPromises()
}

describe('ProjectMembersDialog 项目成员弹窗', () => {
  beforeEach(() => {
    mocks.list.mockReset()
    mocks.add.mockReset()
    mocks.changeRole.mockReset()
    mocks.remove.mockReset()
    mocks.search.mockReset()
  })

  it('打开时拉成员列表并渲染显示名/用户名/角色选择/移除', async () => {
    mocks.list.mockResolvedValue(MEMBERS)
    const w = await mountDialog()
    expect(mocks.list).toHaveBeenCalledWith(1)
    expect(dialogEl().textContent).toContain('王测试')
    expect(dialogEl().textContent).toContain('wang')
    expect(document.querySelectorAll('[data-test="role-select"]').length).toBe(2)
    expect(document.querySelectorAll('[data-test="remove-member"]').length).toBe(2)
    w.unmount()
  })

  it('visible=false 不拉列表', async () => {
    const w = await mountDialog(false)
    expect(mocks.list).not.toHaveBeenCalled()
    w.unmount()
  })

  it('添加成员:搜索选中用户,add 收到 (pid, username, role),列表追加并 emit changed', async () => {
    mocks.list.mockResolvedValue([MEMBERS[0]])
    mocks.add.mockResolvedValue(MEMBERS[1])
    mocks.search.mockResolvedValue([{ id: 9, username: 'bob', display_name: 'Bob' }])
    const w = await mountDialog()
    await selectUser(w, 'bob')
    expect(mocks.search).toHaveBeenCalledWith('bob')
    // 选角色 editor(弹窗里带 data-test="add-role" 的那个 el-select)
    const addRoleSelect = w
      .findAllComponents({ name: 'ElSelect' })
      .find((c) => c.attributes('data-test') === 'add-role')!
    await addRoleSelect.vm.$emit('update:modelValue', 'editor')
    await flushPromises()
    dialogEl().querySelector<HTMLButtonElement>('[data-test="add-submit"]')!.click()
    await flushPromises()
    expect(mocks.add).toHaveBeenCalledWith(1, 'bob', 'editor')
    expect(dialogEl().textContent).toContain('王测试') // 新成员追加进表格
    expect(w.emitted('changed')).toBeTruthy()
    w.unmount()
  })

  it('添加成员 403:透出后端 detail,不 emit changed', async () => {
    mocks.list.mockResolvedValue(MEMBERS)
    mocks.search.mockResolvedValue([{ id: 9, username: 'bob', display_name: 'Bob' }])
    const errSpy = vi.spyOn(ElMessage, 'error')
    const w = await mountDialog()
    await selectUser(w, 'bob')
    mocks.add.mockRejectedValue(new ApiError(403, '无项目操作权限'))
    dialogEl().querySelector<HTMLButtonElement>('[data-test="add-submit"]')!.click()
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('无项目操作权限')
    expect(w.emitted('changed')).toBeFalsy()
    w.unmount()
  })

  it('改角色 409(末位 owner 自降):透出后端 detail 并回滚角色', async () => {
    mocks.list.mockResolvedValue(MEMBERS)
    const errSpy = vi.spyOn(ElMessage, 'error')
    const w = await mountDialog()
    mocks.changeRole.mockRejectedValue(new ApiError(409, '项目至少需要一名 owner'))
    await (w.vm as any).onRoleChange(MEMBERS[0], 'viewer')
    expect(mocks.changeRole).toHaveBeenCalledWith(1, 1, 'viewer')
    expect(errSpy).toHaveBeenCalledWith('项目至少需要一名 owner')
    expect(MEMBERS[0].role).toBe('owner') // 回滚,不残留假角色
    expect(w.emitted('changed')).toBeFalsy()
    w.unmount()
  })

  it('改角色成功:更新行角色并 emit changed', async () => {
    mocks.list.mockResolvedValue(MEMBERS)
    mocks.changeRole.mockResolvedValue({ ...MEMBERS[1], role: 'editor' })
    const w = await mountDialog()
    const row = { ...MEMBERS[1] }
    await (w.vm as any).onRoleChange(row, 'editor')
    expect(row.role).toBe('editor')
    expect(w.emitted('changed')).toBeTruthy()
    w.unmount()
  })
})

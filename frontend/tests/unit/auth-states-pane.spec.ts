import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'

const mocks = vi.hoisted(() => ({
  list: vi.fn(async () => [
    { id: 1, project_id: 1, name: '管理员登录态', created_at: '2026-09-02' },
  ]),
  collect: vi.fn(async () => ({ collect_id: 5 })),
  save: vi.fn(async () => ({ id: 2, project_id: 1, name: '管理员登录态', created_at: '2026-09-03' })),
  cancel: vi.fn(async () => undefined),
  del: vi.fn(async () => undefined),
}))
vi.mock('../../src/api/uiAutomation', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  listUiAuthStates: mocks.list,
  collectAuthState: mocks.collect,
  saveAuthState: mocks.save,
  cancelAuthCollect: mocks.cancel,
  deleteUiAuthState: mocks.del,
}))
import AuthStatesPane from '../../src/components/webauto/AuthStatesPane.vue'

function mountPane() {
  return mount(AuthStatesPane, {
    props: { projectId: 1 },
    global: { plugins: [ElementPlus] },
  })
}
const btn = (w: ReturnType<typeof mountPane>, text: string) =>
  w.findAll('button').find((b) => b.text().trim() === text)!

describe('AuthStatesPane', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.list.mockResolvedValue([{ id: 1, project_id: 1, name: '管理员登录态', created_at: '2026-09-02' }])
  })

  it('列出登录态,行操作删除带确认', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const w = mountPane()
    await flushPromises()
    expect(mocks.list).toHaveBeenCalledWith(1)
    expect(w.text()).toContain('管理员登录态')

    await btn(w, '删除').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(mocks.del).toHaveBeenCalledWith(1)
    expect(mocks.list).toHaveBeenCalledTimes(2) // 删除后刷新
  })

  it('采集→保存→刷新;仍在采集时关闭对话框则取消采集(防会话泄漏)', async () => {
    const w = mountPane()
    await flushPromises()

    const nameInput = w.findAll('input').find((i) => (i.element as HTMLInputElement).placeholder.includes('登录态名称'))!
    await nameInput.setValue('管理员登录态')
    await btn(w, '采集新登录态').trigger('click')
    await flushPromises()
    expect(mocks.collect).toHaveBeenCalledWith(1, '管理员登录态')
    expect(w.text()).toContain('保存登录态')
    expect(w.text()).toContain('在弹出的浏览器里完成登录后回来点保存')

    await btn(w, '保存登录态').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledWith(5)
    expect(mocks.cancel).not.toHaveBeenCalled()
    expect(mocks.list).toHaveBeenCalledTimes(2) // 保存成功刷新列表
    expect(w.text()).not.toContain('在弹出的浏览器里完成登录后回来点保存') // 采集状态已复位

    // 再次进入采集态后直接关对话框 → cancel
    // (jsdom 没有 CSS 过渡,el-dialog 的 close 事件经 transition before-leave 才发,故直接对组件 emit)
    await nameInput.setValue('管理员登录态')
    await btn(w, '采集新登录态').trigger('click')
    await flushPromises()
    w.findComponent({ name: 'ElDialog' }).vm.$emit('close')
    await flushPromises()
    expect(mocks.cancel).toHaveBeenCalledWith(5)
    expect(w.emitted('closed')).toBeTruthy()
  })

  it('save 抛 500 等非 409/404 错误:保留采集会话可重试保存,不误复位', async () => {
    const w = mountPane()
    await flushPromises()
    const nameInput = w.findAll('input').find((i) => (i.element as HTMLInputElement).placeholder.includes('登录态名称'))!
    await nameInput.setValue('管理员登录态')
    await btn(w, '采集新登录态').trigger('click')
    await flushPromises()

    // 500/网络抖动:后端槽位与浏览器窗口仍占着,cid 不能丢
    mocks.save.mockRejectedValueOnce(new ApiError(500, 'Internal Server Error'))
    await btn(w, '保存登录态').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('保存登录态')
    expect(w.text()).toContain('在弹出的浏览器里完成登录后回来点保存')
    expect(mocks.cancel).not.toHaveBeenCalled()

    // 同一会话直接重试即可成功
    await btn(w, '保存登录态').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledTimes(2)
    expect(w.text()).not.toContain('在弹出的浏览器里完成登录后回来点保存')
  })
})

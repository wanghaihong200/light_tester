import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import { resetAuth, useAuth } from '../../src/composables/useAuth'
import TopHeader from '../../src/components/layout/TopHeader.vue'

// mock api 层:控制 fetchMe(/auth/me)结果
const mocks = vi.hoisted(() => ({ me: vi.fn() }))
vi.mock('../../src/api/auth', () => ({ authApi: { login: vi.fn(), me: mocks.me } }))

function me(over: Record<string, unknown> = {}) {
  return { id: 2, username: 'wang', display_name: '王测试', is_admin: false, is_active: true, ...over }
}

function mountHeader() {
  return mount(TopHeader, {
    props: { projectName: '', collapsed: false },
    global: { plugins: [ElementPlus] },
  })
}

describe('TopHeader 顶栏用户区', () => {
  beforeEach(() => {
    resetAuth()
    localStorage.clear()
    location.hash = '#/'
    mocks.me.mockReset()
  })

  it('无 token 不拉 me、不渲染用户区', async () => {
    const w = mountHeader()
    await flushPromises()
    expect(mocks.me).not.toHaveBeenCalled()
    expect(w.find('.user-area').exists()).toBe(false)
    w.unmount()
  })

  it('有 token 挂载即 fetchMe 并显示 display_name;非管理员无「用户管理」', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    const w = mountHeader()
    await flushPromises()
    expect(mocks.me).toHaveBeenCalledOnce()
    expect(w.find('[data-test="user-name"]').text()).toBe('王测试')
    expect(w.find('[data-test="admin-link"]').exists()).toBe(false)
    w.unmount()
  })

  it('管理员才显示「用户管理」,链接指向 #/users', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me({ id: 1, username: 'admin', display_name: '管理员', is_admin: true }))
    const w = mountHeader()
    await flushPromises()
    expect(w.find('[data-test="admin-link"]').attributes('href')).toBe('#/users')
    w.unmount()
  })

  it('退出:清 token 与用户态、跳 #/login、用户区消失', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockResolvedValue(me())
    const w = mountHeader()
    await flushPromises()
    await w.find('[data-test="logout"]').trigger('click')
    await flushPromises()
    expect(localStorage.getItem('tt_token')).toBeNull()
    expect(useAuth().user.value).toBeNull()
    expect(location.hash).toBe('#/login')
    expect(w.find('.user-area').exists()).toBe(false)
    w.unmount()
  })

  it('fetchMe 失败(401 踢登录)不阻塞布局', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    mocks.me.mockRejectedValue(new ApiError(401, '未登录或登录已过期'))
    const w = mountHeader()
    await flushPromises() // 若拒绝外漏,vitest 会以 unhandled error 判红
    expect(w.find('.user-area').exists()).toBe(false)
    w.unmount()
  })
})

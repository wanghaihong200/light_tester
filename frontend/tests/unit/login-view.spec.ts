import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import { resetAuth } from '../../src/composables/useAuth'
import LoginView from '../../src/views/LoginView.vue'

// mock api 层(composable 经 authApi 调用):捕获入参、控制成功/失败
const mocks = vi.hoisted(() => ({ login: vi.fn() }))
vi.mock('../../src/api/auth', () => ({ authApi: { login: mocks.login, me: vi.fn() } }))

const ADMIN_USER = {
  id: 1, username: 'admin', display_name: '管理员', is_admin: true, is_active: true,
}

function mountLogin() {
  return mount(LoginView, { global: { plugins: [ElementPlus] }, attachTo: document.body })
}

async function fillAndSubmit(wrapper: ReturnType<typeof mountLogin>, username: string, password: string) {
  const inputs = wrapper.findAll<HTMLInputElement>('input')
  await inputs[0].setValue(username)
  await inputs[1].setValue(password)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('LoginView 登录页', () => {
  beforeEach(() => {
    resetAuth()
    localStorage.clear()
    location.hash = '#/login'
    mocks.login.mockReset()
  })

  it('渲染用户名/密码输入与提交按钮', () => {
    const w = mountLogin()
    expect(w.find('[data-test="username"]').exists()).toBe(true)
    expect(w.find('[data-test="password"]').exists()).toBe(true)
    expect(w.find('[data-test="submit"]').exists()).toBe(true)
    w.unmount()
  })

  it('提交成功:login 收到账密、token 落地、跳 #/', async () => {
    mocks.login.mockResolvedValue({ token: 'jwt-1', user: ADMIN_USER })
    const w = mountLogin()
    await fillAndSubmit(w, 'admin', 'secret')
    expect(mocks.login).toHaveBeenCalledWith('admin', 'secret')
    expect(localStorage.getItem('tt_token')).toBe('jwt-1')
    expect(location.hash).toBe('#/')
    w.unmount()
  })

  it('提交失败:显示后端 detail,不跳转', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    mocks.login.mockRejectedValue(new ApiError(401, '用户名或密码错误'))
    const w = mountLogin()
    await fillAndSubmit(w, 'admin', 'bad')
    expect(errSpy).toHaveBeenCalled()
    expect(String(errSpy.mock.calls[0][0])).toBe('用户名或密码错误')
    expect(location.hash).toBe('#/login')
    w.unmount()
  })

  it('账密任一为空:不发请求', async () => {
    const w = mountLogin()
    const inputs = w.findAll<HTMLInputElement>('input')
    await inputs[0].setValue('admin') // 密码留空
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.login).not.toHaveBeenCalled()
    w.unmount()
  })
})

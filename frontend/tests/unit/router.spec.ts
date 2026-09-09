import { beforeEach, describe, expect, it } from 'vitest'
import router from '../../src/router'

// 走真实 router(含 beforeEach 守卫与 /login 路由):只断言导航结果,不挂载组件。
// 注意:不手动改 location.hash —— hashchange 会触发与显式 push 竞争的自动导航,干扰断言
describe('路由守卫', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('未登录访问首页 → 踢到 /login', async () => {
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('登录页自身放行,不被守卫拦截(防循环)', async () => {
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('有 token 放行受保护路由;登录页仍可访问;token 移除后重新受保护', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/')
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/login')
    localStorage.removeItem('tt_token')
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('项目内六功能段:路径/命名契约;空段重定向到功能用例管理', async () => {
    localStorage.setItem('tt_token', 'jwt-1')
    await router.push('/projects/1')
    expect(router.currentRoute.value.path).toBe('/projects/1/cases')
    expect(router.currentRoute.value.name).toBe('project-cases')

    const table: [string, string][] = [
      ['/projects/1/knowledge', 'project-knowledge'],
      ['/projects/1/ai/jobs', 'project-ai-jobs'],
      ['/projects/1/ai/repo', 'project-ai-repo'],
      ['/projects/1/ai/cross', 'project-ai-cross'],
      ['/projects/1/ui/web', 'project-ui-web'],
    ]
    for (const [path, name] of table) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe(name)
    }
    localStorage.removeItem('tt_token')
  })

  it('接口Mock段:project-mock-http 解析 /projects/1/mock/http', () => {
    // 组件为懒加载且 MockPane 属 Task 9:resolve 只匹配路由记录、不触发组件加载,验路由契约即可
    const r = router.resolve('/projects/1/mock/http')
    expect(r.name).toBe('project-mock-http')
    expect(r.path).toBe('/projects/1/mock/http')
  })
})

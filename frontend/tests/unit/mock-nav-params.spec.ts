import { describe, expect, it } from 'vitest'
import router from '../../src/router'

// 守卫(计划15 T11 评审修复):HTTP Mock 下钻链全部命名路由 push 均须带父级 /projects/:id 的 id 参数。
// vue-router 命名跳转按整条匹配链组路径,链上任一必选参数缺失即在 resolve/push 时抛
// 「Missing required param」——真实浏览器曾因此导航全断(单测 mock 掉 useRouter 掩盖了它)。
// 此处直接用真实路由表 router.resolve 验证(与 push 同一 matcher 同一校验,不跑守卫/不发请求)。
describe('HTTP Mock 下钻链命名路由参数完整性', () => {
  it('带全链参数(id+instanceId)resolve 成功,fullPath 含父级 id', () => {
    const list = router.resolve({ name: 'project-mock-http', params: { id: 3 } })
    expect(list.fullPath).toBe('/projects/3/mock/http')
    const detail = router.resolve({ name: 'project-mock-http-detail', params: { id: 3, instanceId: 5 } })
    expect(detail.fullPath).toBe('/projects/3/mock/http/5')
    const hits = router.resolve({ name: 'project-mock-http-hits', params: { id: 3, instanceId: 5 } })
    expect(hits.fullPath).toBe('/projects/3/mock/http/5/hits')
  })

  it('缺父级 id:resolve 抛 Missing required param(钉住根因,防调用点再犯)', () => {
    expect(() => router.resolve({ name: 'project-mock-http', params: {} }))
      .toThrow(/Missing required param/)
    expect(() => router.resolve({ name: 'project-mock-http-detail', params: { instanceId: 5 } }))
      .toThrow(/Missing required param/)
    expect(() => router.resolve({ name: 'project-mock-http-hits', params: { instanceId: 5 } }))
      .toThrow(/Missing required param/)
  })
})

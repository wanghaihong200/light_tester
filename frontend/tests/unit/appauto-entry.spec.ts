// frontend/tests/unit/appauto-entry.spec.ts
import { describe, expect, it, vi } from 'vitest'

const push = vi.fn()
// 计划稿 erratum:全量 mock 会掏空 createRouter,src/router 模块求值即崩(套件永红);
// 按 brief 注「mock 形态以现文件为准」改为 importOriginal 展开,仅覆写组合式 API(本文件断言不消费,保留原形)
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '1' }, name: 'project-cases', path: '/projects/1/cases' }),
  useRouter: () => ({ push }),
}))

import router from '../../src/router'
import SideMenu from '../../src/components/layout/SideMenu.vue'
import { mount } from '@vue/test-utils'

describe('APP自动化入口(计划 12)', () => {
  it('注册 project-ui-app 路由', () => {
    const r = router.getRoutes().find((x) => x.name === 'project-ui-app')
    expect(r).toBeTruthy()
    expect(r!.path.endsWith('/ui/app')).toBe(true)
  })

  it('SideMenu 渲染「APP自动化」菜单项(UI自动化组,非 AI 分组轴)', () => {
    // mount 套路对齐 tests/unit/side-menu.spec.ts(props 全给,防 Vue 缺省 prop 告警)
    const w = mount(SideMenu, {
      props: { activeKey: 'project-3:cases', collapsed: false, projectId: 3 },
      global: { stubs: { 'router-link': { template: '<a><slot/></a>' } } },
    })
    expect(w.text()).toContain('APP自动化')
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SideMenu from '../../src/components/layout/SideMenu.vue'

describe('SideMenu 持续集成组', () => {
  it('项目态渲染组与两个子项', () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:cicd-plans', collapsed: false, projectId: 3 } })
    const text = w.text()
    expect(text).toContain('持续集成')
    expect(text).toContain('执行计划')
    expect(text).toContain('执行记录')
  })

  it('激活执行计划时组内子项高亮', () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:cicd-plans', collapsed: false, projectId: 3 } })
    const active = w.find('.menu-item.active')
    expect(active.text()).toContain('执行计划')
  })
})

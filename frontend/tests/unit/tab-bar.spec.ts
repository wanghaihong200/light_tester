import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import TabBar from '../../src/components/layout/TabBar.vue'
import { resetTabs, useTabs } from '../../src/composables/useTabs'

describe('TabBar', () => {
  beforeEach(() => resetTabs())

  it('渲染页签名;首页页签没有关闭钮', () => {
    useTabs().openProject(1, '商城系统')
    const wrapper = mount(TabBar, { props: { activeKey: 'home' } })
    const pills = wrapper.findAll('.tab-pill')
    expect(pills).toHaveLength(2)
    expect(pills[0].text()).toContain('首页')
    expect(pills[1].text()).toContain('商城系统')
    expect(pills[0].find('.tab-close').exists()).toBe(false)
    expect(pills[1].find('.tab-close').exists()).toBe(true)
    expect(pills[0].classes()).toContain('active')
  })

  it('点击页签发出 select(key);点关闭只发出 close 不触发 select', async () => {
    useTabs().openProject(1, '商城系统')
    const wrapper = mount(TabBar, { props: { activeKey: 'project-1' } })
    await wrapper.findAll('.tab-pill')[0].trigger('click')
    expect(wrapper.emitted('select')![0]).toEqual(['home'])
    await wrapper.findAll('.tab-pill')[1].find('.tab-close').trigger('click')
    expect(wrapper.emitted('close')![0]).toEqual(['project-1'])
    // .stop 修饰:关闭不冒泡成 select
    expect(wrapper.emitted('select')).toHaveLength(1)
  })
})

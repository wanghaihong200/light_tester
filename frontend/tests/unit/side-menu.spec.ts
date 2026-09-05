import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import SideMenu from '../../src/components/layout/SideMenu.vue'

vi.mock('../../src/api/projects', () => ({
  listProjects: vi.fn().mockResolvedValue([
    { id: 1, name: '商城系统', description: null, git_repo_url: null, created_at: '2026-08-15T10:00:00' },
    { id: 2, name: '风控平台', description: null, git_repo_url: null, created_at: '2026-08-14T09:00:00' },
  ]),
}))

describe('SideMenu', () => {
  it('渲染品牌/首页/项目列表;点击发出 navigate', async () => {
    const wrapper = mount(SideMenu, { props: { activeKey: 'home', collapsed: false } })
    await flushPromises()
    expect(wrapper.text()).toContain('轻测试')
    expect(wrapper.text()).toContain('首页')
    expect(wrapper.text()).toContain('商城系统')
    expect(wrapper.text()).toContain('风控平台')
    await wrapper.findAll('.menu-item')[1].trigger('click') // 0=首页,1=第一个项目
    expect(wrapper.emitted('navigate')![0]).toEqual(['/projects/1'])
  })

  it('activeKey 命中的菜单项高亮', async () => {
    const wrapper = mount(SideMenu, { props: { activeKey: 'project-2', collapsed: false } })
    await flushPromises()
    const items = wrapper.findAll('.menu-item')
    expect(items[1].classes()).not.toContain('active')
    expect(items[2].classes()).toContain('active')
  })

  it('折叠态:隐藏文字、项目名转 title 提示', async () => {
    const wrapper = mount(SideMenu, { props: { activeKey: 'home', collapsed: true } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('商城系统')
    expect(wrapper.find('.brand-name').exists()).toBe(false)
    expect(wrapper.find('[title="商城系统"]').exists()).toBe(true)
  })
})

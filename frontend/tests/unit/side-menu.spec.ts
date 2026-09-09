import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import SideMenu from '../../src/components/layout/SideMenu.vue'

// 侧栏已不拉项目列表(项目入口=顶栏下拉+首页卡片墙);mock 兜底防误用
vi.mock('../../src/api/projects', () => ({ listProjects: vi.fn() }))

describe('SideMenu', () => {
  it('首页态:仅品牌+首页,无项目列表、无功能菜单', () => {
    const w = mount(SideMenu, { props: { activeKey: 'home', collapsed: false, projectId: null } })
    expect(w.text()).toContain('LightTester')
    expect(w.findAll('.menu-item')).toHaveLength(1)
    expect(w.text()).not.toContain('功能用例管理')
    expect(w.text()).not.toContain('商城系统')
    w.unmount()
  })

  it('项目态:渲染功能菜单树(叶子两项+两组各子项),无项目名列表', () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:cases', collapsed: false, projectId: 3 } })
    for (const label of ['功能用例管理', '知识库', 'AI测试', '生成任务', '自动化工程', '多端 UI 自动化', 'UI自动化', 'Web自动化', '接口Mock', 'HTTP Mock']) {
      expect(w.text()).toContain(label)
    }
    expect(w.text()).not.toContain('商城系统')
    w.unmount()
  })

  it('接口Mock 组:子项 HTTP Mock 导航到 mock/http', async () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:mock-http', collapsed: false, projectId: 3 } })
    const item = w.findAll('.menu-item').find((i) => i.find('.menu-name').text() === 'HTTP Mock')!
    await item.trigger('click')
    expect(w.emitted('navigate')![0]).toEqual(['/projects/3/mock/http'])
    expect(item.classes()).toContain('active')
    w.unmount()
  })

  it('点击叶子项:navigate 到对应子路由', async () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:knowledge', collapsed: false, projectId: 3 } })
    // 叶子项 text() = icon+label 无缝拼接,按 .menu-name 精确匹配(brief 原式 `i.text() === label` 对带 icon 项不成立)
    const kb = w.findAll('.menu-item').find((i) => i.find('.menu-name').text() === '知识库')!
    await kb.trigger('click')
    expect(w.emitted('navigate')![0]).toEqual(['/projects/3/knowledge'])
    w.unmount()
  })

  it('点击组头折叠/再展开子项;点击子项 navigate', async () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:ai-jobs', collapsed: false, projectId: 3 } })
    const groupHead = w.findAll('.menu-item').find((i) => i.text().includes('AI测试'))!
    await groupHead.trigger('click') // 折叠
    expect(w.text()).not.toContain('生成任务')
    await groupHead.trigger('click') // 展开
    expect(w.text()).toContain('生成任务')
    await w.findAll('.menu-item').find((i) => i.text() === '生成任务')!.trigger('click')
    expect(w.emitted('navigate')![0]).toEqual(['/projects/3/ai/jobs'])
    w.unmount()
  })

  it('激活子项所在组被折叠时,自动展开(watch activeKey)', async () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:cases', collapsed: false, projectId: 3 } })
    // 先手动折叠 UI 组
    const uiHead = w.findAll('.menu-item').find((i) => i.text().includes('UI自动化'))!
    await uiHead.trigger('click')
    expect(w.text()).not.toContain('Web自动化')
    // 激活 UI 组子项 → 组自动展开
    await w.setProps({ activeKey: 'project-3:ui-web' })
    expect(w.text()).toContain('Web自动化')
    w.unmount()
  })

  it('高亮:activeKey 命中的项带 active;组头不高亮', () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:knowledge', collapsed: false, projectId: 3 } })
    const kb = w.findAll('.menu-item').find((i) => i.find('.menu-name').text() === '知识库')!
    expect(kb.classes()).toContain('active')
    const aiHead = w.findAll('.menu-item').find((i) => i.text().includes('AI测试'))!
    expect(aiHead.classes()).not.toContain('active')
    w.unmount()
  })

  it('首页项高亮与导航不受项目态影响', async () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:cases', collapsed: false, projectId: 3 } })
    const home = w.findAll('.menu-item')[0]
    expect(home.classes()).not.toContain('active')
    await home.trigger('click')
    expect(w.emitted('navigate')![0]).toEqual(['/'])
    w.unmount()
  })

  it('折叠态:隐藏文字,组头/叶子转 title,点组头直达第一个子项', async () => {
    const w = mount(SideMenu, { props: { activeKey: 'project-3:cases', collapsed: true, projectId: 3 } })
    expect(w.text()).not.toContain('功能用例管理')
    expect(w.find('[title="功能用例管理"]').exists()).toBe(true)
    expect(w.find('[title="AI测试"]').exists()).toBe(true)
    const aiHead = w.find('[title="AI测试"]')
    await aiHead.trigger('click')
    expect(w.emitted('navigate')![0]).toEqual(['/projects/3/ai/jobs'])
    w.unmount()
  })
})

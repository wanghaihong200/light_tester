import { beforeEach, describe, expect, it } from 'vitest'
import { resetTabs, useTabs } from '../../src/composables/useTabs'

describe('useTabs', () => {
  beforeEach(() => resetTabs())

  it('初始只有不可关的首页页签', () => {
    const { tabs, closeTab } = useTabs()
    expect(tabs.value).toEqual([{ key: 'home', name: '首页' }])
    expect(closeTab('home', 'home')).toBeNull()
    expect(tabs.value).toHaveLength(1)
  })

  it('openProject 追加页签;重复打开不重复且同步新名称', () => {
    const { tabs, openProject } = useTabs()
    openProject(1, '商城系统')
    openProject(1, '商城系统改') // 同一项目再次打开:改名不重复
    openProject(2, '风控平台')
    expect(tabs.value.map((t) => t.key)).toEqual(['home', 'project-1', 'project-2'])
    expect(tabs.value[1].name).toBe('商城系统改')
  })

  it('关闭非活跃页签:移除并返回 null(停留原页)', () => {
    const { tabs, openProject, closeTab } = useTabs()
    openProject(1, '商城系统')
    openProject(2, '风控平台')
    expect(closeTab('project-1', 'project-2')).toBeNull()
    expect(tabs.value.map((t) => t.key)).toEqual(['home', 'project-2'])
  })

  it('关闭活跃页签:返回相邻页签 key(优先左侧)', () => {
    const { openProject, closeTab } = useTabs()
    openProject(1, '商城系统')
    openProject(2, '风控平台')
    expect(closeTab('project-2', 'project-2')).toBe('project-1')
    expect(closeTab('project-1', 'project-1')).toBe('home')
    expect(closeTab('home', 'home')).toBeNull()
  })

  it('关闭不存在的页签返回 null', () => {
    const { closeTab } = useTabs()
    expect(closeTab('project-99', 'home')).toBeNull()
  })
})

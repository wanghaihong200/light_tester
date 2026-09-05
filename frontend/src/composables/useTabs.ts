import { ref } from 'vue'

// 布局壳页签状态:首页页签固定,项目页签按访问动态开关(设计 §3)
export interface TabItem {
  key: string // 'home' | 'project-<id>'
  id?: number // 项目 id;undefined 即首页(不可关)
  name: string
}

const tabs = ref<TabItem[]>([{ key: 'home', name: '首页' }])

export function useTabs() {
  // 打开/更新项目页签:已存在则同步名称(项目改名、异步加载回填),不存在则追加
  function openProject(id: number, name: string): void {
    const key = `project-${id}`
    const existing = tabs.value.find((t) => t.key === key)
    if (existing) existing.name = name
    else tabs.value.push({ key, id, name })
  }

  // 关闭页签。返回应跳往的页签 key;关非活跃页签/首页/不存在 → null(停留原页)
  function closeTab(key: string, activeKey: string): string | null {
    const idx = tabs.value.findIndex((t) => t.key === key)
    if (idx < 0 || tabs.value[idx].id === undefined) return null
    tabs.value.splice(idx, 1)
    if (activeKey !== key) return null
    const next = tabs.value[Math.max(0, idx - 1)]
    return next.key
  }

  return { tabs, openProject, closeTab }
}

// 仅测试用:模块级状态在用例间共享,需要显式复位
export function resetTabs(): void {
  tabs.value = [{ key: 'home', name: '首页' }]
}

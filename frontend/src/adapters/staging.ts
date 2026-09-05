import type { MindmapNode } from './tree'
import type { StagingGroup } from '../types'

/** 将暂存区用例转换为导图树(根节点为模块名,功能点为中间层,用例为叶子) */
export function stagedToMindmap(moduleName: string, groups: StagingGroup[]): MindmapNode {
  return {
    data: { text: moduleName, uid: 'root', nodeType: 'root' },
    children: groups.map((group, idx) => ({
      data: { text: group.feature_point_name, uid: `staged-fp-${idx}`, nodeType: 'feature' },
      children: group.cases.map((c) => ({
        data: {
          text: `[${c.priority}] ${c.title}`,
          uid: `staged-case-${c.id}`,
          nodeType: 'case',
        },
        children: [],
      })),
    })),
  }
}

/** 计算暂存区总用例数 */
export function stagedTotal(groups: StagingGroup[]): number {
  return groups.reduce((sum, g) => sum + g.cases.length, 0)
}

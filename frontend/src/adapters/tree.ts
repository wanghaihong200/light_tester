import type { CaseSummary, ModuleNode } from '../types'

export type NodeType = 'root' | 'module' | 'feature' | 'case'

export interface MindmapNodeData {
  text: string
  uid: string
  nodeType: NodeType
  refId?: number
}
export interface MindmapNode {
  data: MindmapNodeData
  children: MindmapNode[]
}

/** 用例叶子显示文本:执行结果标记(✓ 通过 / ✗ 未通过),恒带优先级前缀 */
export function caseLabel(c: CaseSummary): string {
  const mark = c.executed_pass === true ? '✓ ' : c.executed_pass === false ? '✗ ' : ''
  return `${mark}[${c.priority}] ${c.title}`
}

function caseToNode(c: CaseSummary): MindmapNode {
  return { data: { text: caseLabel(c), uid: `case-${c.id}`, nodeType: 'case', refId: c.id }, children: [] }
}

function featureToNode(f: { id: number; name: string; cases: CaseSummary[] }): MindmapNode {
  return {
    data: { text: f.name, uid: `feature-${f.id}`, nodeType: 'feature', refId: f.id },
    children: f.cases.map(caseToNode),
  }
}

function moduleToNode(m: ModuleNode): MindmapNode {
  // 子模块在前、功能点在后,与手工建树习惯一致
  return {
    data: { text: m.name, uid: `module-${m.id}`, nodeType: 'module', refId: m.id },
    children: [...m.children.map(moduleToNode), ...m.feature_points.map(featureToNode)],
  }
}

export function toMindmapData(projectName: string, modules: ModuleNode[]): MindmapNode {
  return {
    data: { text: projectName, uid: 'root', nodeType: 'root' },
    children: modules.map(moduleToNode),
  }
}

/** 各节点类型允许新增的子节点类型(树形约束:模块→任意嵌套模块;功能点下只能是用例) */
export function canAddChild(nodeType: NodeType): Array<'module' | 'feature' | 'case'> {
  if (nodeType === 'root') return ['module']
  if (nodeType === 'module') return ['module', 'feature']
  if (nodeType === 'feature') return ['case']
  return []
}

export interface NodeMeta {
  name: string
  parentId: number | null
}

/** 从导图树回查节点名称与父模块 refId(仅模块/功能点;用例 text 带优先级前缀,不走此查询) */
export function findNodeMeta(root: MindmapNode | null, refId: number): NodeMeta {
  let result: NodeMeta = { name: '', parentId: null }
  function walk(node: MindmapNode, parentRefId: number | null) {
    if ((node.data.nodeType === 'module' || node.data.nodeType === 'feature') && node.data.refId === refId) {
      result = { name: node.data.text, parentId: parentRefId }
      return
    }
    node.children.forEach((c) => walk(c, node.data.nodeType === 'module' ? (node.data.refId ?? null) : parentRefId))
  }
  if (root) walk(root, null)
  return result
}

/** 拍平模块树供下拉选择;excludeSubtreeOf 排除该模块及其整个子树(移动模块时防自嵌套) */
export function flattenModules(modules: ModuleNode[], excludeSubtreeOf?: number): Array<{ id: number; name: string; depth: number }> {
  const out: Array<{ id: number; name: string; depth: number }> = []
  function walk(list: ModuleNode[], depth: number) {
    for (const m of list) {
      if (m.id === excludeSubtreeOf) continue
      out.push({ id: m.id, name: m.name, depth })
    }
    for (const m of list) {
      if (m.id === excludeSubtreeOf) continue
      walk(m.children, depth + 1)
    }
  }
  walk(modules, 0)
  return out
}

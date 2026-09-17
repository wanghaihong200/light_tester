// frontend/tests/unit/case-tree.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CaseTree from '../../src/components/cicd/CaseTree.vue'
import type { CaseRow } from '../../src/components/cicd/CaseTree.vue'

const rows: CaseRow[] = [
  { class_name: 'com.x.A', name: 'ok1', status: 'passed', time_s: 0.1, message: null },
  { class_name: 'com.x.B', name: 'dd[admin](1)', status: 'passed', time_s: 0.2, message: null },
  { class_name: 'com.x.B', name: 'dd[admin](2)', status: 'failed', time_s: 0.3, message: 'boom' },
  { class_name: 'com.x.C', name: 'sk', status: 'not_run', time_s: 0,
    message: '仓内导出文件缺失', skipped_note: true },
]

function mountTree(r: CaseRow[] = rows) {
  return mount(CaseTree, { props: { rows: r } })
}

describe('CaseTree', () => {
  it('类分组展示短名,数据驱动重名方法合并为一组', async () => {
    const w = mountTree()
    await flushPromises()
    expect(w.text()).toContain('A')
    expect(w.text()).toContain('B')
    expect(w.text()).toContain('C')
    // B(含失败)默认展开:方法组标签是去后缀的 base 名
    expect(w.text()).toContain('dd')
    expect(w.text()).toContain('dd[admin](1)')
    expect(w.text()).toContain('dd[admin](2)')
    expect(w.text()).toContain('boom')
  })

  it('全通过的类默认收起,未执行的类默认展开', async () => {
    const w = mountTree()
    await flushPromises()
    // A 全通过 → 收起,叶子不可见;C 含未执行 → 展开
    expect(w.text()).not.toContain('ok1')
    expect(w.text()).toContain('sk')
  })

  it('点击收起的类行展开,叶子出现', async () => {
    const w = mountTree()
    await flushPromises()
    const aRow = w.findAll('.row').find((r) => r.text() === 'A✓0.10 秒')
      ?? w.findAll('.row').find((r) => r.text().includes('A'))
    await aRow!.trigger('click')
    expect(w.text()).toContain('ok1')
  })

  it('点击叶子 emit locate 且带整行;叶子点击不触发展开切换', async () => {
    const w = mountTree()
    await flushPromises()
    const leaf = w.findAll('.row.leaf').find((r) => r.text().includes('dd[admin](1)'))
    await leaf!.trigger('click')
    const emitted = w.emitted('locate')
    expect(emitted).toHaveLength(1)
    expect((emitted![0][0] as CaseRow).name).toBe('dd[admin](1)')
  })

  it('空数据渲染占位', () => {
    const w = mountTree([])
    expect(w.text()).toContain('暂无用例数据')
  })
})

// tests/unit/perf-summary-table.spec.ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import PerfSummaryTable from '../../src/components/perf/PerfSummaryTable.vue'

// jsdom 无 ResizeObserver,el-table 依赖其测量列宽(mindmap-editor.spec 同款 stub)
vi.stubGlobal('ResizeObserver', class { observe() { /* noop */ } unobserve() { /* noop */ } disconnect() { /* noop */ } })

// 装真 Element Plus(对齐 appauto-pane.spec:不桩 el-table,否则列渲染不出)
const mountTable = (props: Record<string, unknown>) =>
  mount(PerfSummaryTable, { props, global: { plugins: [ElementPlus] } })

describe('PerfSummaryTable', () => {
  it('columns 渲染统计行;浮点列两位小数,样本数整数直显,缺失键显 —', async () => {
    // CPU 行全键(浮点列 toFixed(2)、样本数整数直显);FPS 行缺 min/median;Mem 行缺 sampleCount
    const w = mountTable({
      summary: {
        columns: [
          { index: 'CPU', sampleCount: 60, min: 1, max: 9, mean: 4.5, median: 4, p90: 8 },
          { index: 'FPS', sampleCount: 120, max: 58, mean: 57.5, p90: 58 },
          { index: 'Mem', min: 1, max: 2 },
        ],
      },
    })
    // el-table 表体渲染跨多个内部 tick,轮询等待稳定(vi.waitFor 默认 1s 上限)
    await vi.waitFor(() => {
      expect(w.text()).toContain('CPU')
    })
    const text = w.text()
    expect(text).toContain('4.50') // toFixed(2) → "4.50"
    expect(text).toContain('60') // 样本数整数直显,不掺两位小数(计划14 终审)
    expect(text).not.toContain('60.00')
    expect(text).toContain('120')
    expect(text).not.toContain('120.00')
    expect(text).toContain('均值')
    expect(text).toContain('FPS')
    expect(text).toContain('—') // 缺失键 null 防御
    const memRow = w.findAll('.el-table__row').find((r) => r.text().includes('Mem'))
    expect(memRow?.text()).toContain('—') // Mem 行 sampleCount 缺失 → '—'
    w.unmount()
  })

  it('summary.error → el-alert 错误文案;空 summary 显示占位', () => {
    const err = mountTable({ summary: { error: 'csv 解析失败' } })
    expect(err.text()).toContain('csv 解析失败')
    err.unmount()
    const w = mountTable({ summary: null })
    expect(w.text()).toContain('暂无统计')
    w.unmount()
  })
})

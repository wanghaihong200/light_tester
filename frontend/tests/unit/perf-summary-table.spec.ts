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
  it('columns 渲染统计行;缺失键显 —', async () => {
    // 首行全键(验证 toFixed(2)),次行缺 min/median(验证 null → '—')
    const w = mountTable({
      summary: {
        columns: [
          { index: 'CPU', sampleCount: 60, min: 1, max: 9, mean: 4.5, median: 4, p90: 8 },
          { index: 'FPS', sampleCount: 60, max: 60, mean: 59.5, p90: 60 },
        ],
      },
    })
    // el-table 表体渲染跨多个内部 tick,轮询等待稳定(vi.waitFor 默认 1s 上限)
    await vi.waitFor(() => {
      expect(w.text()).toContain('CPU')
    })
    const text = w.text()
    expect(text).toContain('4.5') // toFixed(2) → "4.50",包含 4.5
    expect(text).toContain('均值')
    expect(text).toContain('FPS')
    expect(text).toContain('—') // 缺失键 null 防御
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

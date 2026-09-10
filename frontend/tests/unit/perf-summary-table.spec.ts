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

  // ── 计划14 冒烟修复:CLI perf-analyze 真实结构 {files:[…]} 在表内先归一(修2)──
  it('CLI files 结构 summary:表内 normalize,指标列显 fileKey · 列名 短形', async () => {
    const w = mountTable({
      summary: {
        files: [{
          path: 'CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789.csv',
          columns: [
            { name: 'CPU温度(度)', index: 1, kind: 'numeric', mean: 50.5, p90: 56.4, sampleCount: 56 },
            { name: 'extra', index: 2, kind: 'skipped' },
          ],
        }],
      },
    })
    await vi.waitFor(() => {
      expect(w.text()).toContain('Temperature · CPU温度(度)') // 短形:<fileKey> · <列名>
    })
    expect(w.text()).toContain('50.50')
    expect(w.text()).not.toContain('skipped') // 非数值列不进统计
    // 全量完整键保留在行数据上(el-table 的 data 行对象 index 属性)
    const data = w.findComponent({ name: 'ElTable' }).props('data') as { index: string }[]
    expect(data[0].index).toBe('CPU温度_Temperature_6f1c725f5fab3cd4_1789_1789::CPU温度(度)')
    w.unmount()
  })

  // ── 计划14 冒烟修复(修5):行数 >12 折叠,≤12 平铺 ──
  it('行数>12:套 el-collapse 默认收起,标题含列数;点标题展开见全表', async () => {
    const cols = Array.from({ length: 15 }, (_, i) => ({ index: `M${i}`, mean: i }))
    const w = mountTable({ summary: { columns: cols } })
    await vi.waitFor(() => {
      expect(w.find('[data-test="stat-collapse"]').exists()).toBe(true)
    })
    expect(w.text()).toContain('统计明细(15 列)')
    const table = w.find('[data-test="stat-table"]')
    expect(table.exists()).toBe(true)
    expect(table.isVisible()).toBe(false) // 默认收起,抽屉不被统计表撑爆
    await w.find('.el-collapse-item__header').trigger('click')
    // 展开态以 collapse 自身状态断言(过渡清理在 jsdom 有宏任务抖动,isVisible 偶发滞后)
    await vi.waitFor(() => {
      expect(w.find('.el-collapse-item__header').attributes('aria-expanded')).toBe('true')
    })
    expect(w.find('.el-collapse-item').classes()).toContain('is-active')
    expect(w.findAll('.el-table__row')).toHaveLength(15) // 展开见全表
    w.unmount()
  })

  it('行数≤12:直接平铺不折叠(既有小样例场景不受影响)', async () => {
    const cols = Array.from({ length: 12 }, (_, i) => ({ index: `M${i}`, mean: i }))
    const w = mountTable({ summary: { columns: cols } })
    await vi.waitFor(() => {
      expect(w.find('[data-test="stat-table"]').exists()).toBe(true)
    })
    expect(w.find('[data-test="stat-collapse"]').exists()).toBe(false)
    expect(w.find('[data-test="stat-table"]').isVisible()).toBe(true)
    w.unmount()
  })
})

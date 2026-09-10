<script setup lang="ts">
// src/components/perf/PerfSummaryTable.vue
// 性能汇总统计表:summary 先过 normalizePerfSummary(CLI perf-analyze 真实 {files:[…]} →
// 平台标准形,幂等;计划14 冒烟修复),extractStatRows 出行;error 摘要呈错误条,空呈占位文案。
// 指标列显示短形 `<fileKey> · <列名>`(归一化后完整键 `<stem>::<列名>` 保留在行数据 index);
// 行数>12 套 el-collapse 默认收起(修5:51 文件 × 1-4 列可逾百行,防详情抽屉被统计表撑爆)。
import { computed } from 'vue'
import { extractStatRows, normalizePerfSummary, type PerfSummary, type StatRow } from './perfOption'

// 超过该行数改折叠呈现,≤12 直接平铺(既有小样例场景不受影响)
const FLAT_ROW_LIMIT = 12

const props = defineProps<{ summary?: PerfSummary }>()

const rows = computed<StatRow[]>(() => extractStatRows(normalizePerfSummary(props.summary ?? null)))
const collapsible = computed(() => rows.value.length > FLAT_ROW_LIMIT)
const errorMsg = computed(() => {
  const e = props.summary?.error
  return e == null ? '' : String(e)
})

// 指标列短形:归一化行有 fileKey/name 拼 `<fileKey> · <列名>`;人工/legacy summary 回退完整 index
function labelOf(r: StatRow): string {
  return r.fileKey && r.name ? `${r.fileKey} · ${r.name}` : r.index
}

// 数值列:null 防御 + 两位小数;样本数是计数,整数直显(计划14 终审)
const VALUE_COLS: { prop: keyof StatRow; label: string; fmt: (v: unknown) => string }[] = [
  { prop: 'sampleCount', label: '样本数', fmt: fmtInt },
  { prop: 'min', label: '最小', fmt: fmtFloat },
  { prop: 'max', label: '最大', fmt: fmtFloat },
  { prop: 'mean', label: '均值', fmt: fmtFloat },
  { prop: 'median', label: '中位', fmt: fmtFloat },
  { prop: 'p90', label: 'P90', fmt: fmtFloat },
]

function fmtFloat(v: unknown): string {
  return v == null ? '—' : Number(v).toFixed(2)
}

function fmtInt(v: unknown): string {
  return v == null ? '—' : String(Number(v))
}
</script>

<template>
  <el-alert v-if="errorMsg" type="error" :closable="false" :title="`性能汇总解析失败:${errorMsg}`" />
  <p v-else-if="!rows.length" class="empty">暂无统计</p>
  <!-- 折叠/平铺两分支的表体标记须保持一致(仅外层容器不同) -->
  <el-collapse v-else-if="collapsible" class="stat-collapse" data-test="stat-collapse">
    <el-collapse-item :title="`统计明细(${rows.length} 列)`" name="stat">
      <el-table :data="rows" size="small" data-test="stat-table">
        <el-table-column label="指标" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ labelOf(row) }}</template>
        </el-table-column>
        <el-table-column v-for="c in VALUE_COLS" :key="c.prop" min-width="72" :label="c.label">
          <template #default="{ row }">{{ c.fmt(row[c.prop]) }}</template>
        </el-table-column>
      </el-table>
    </el-collapse-item>
  </el-collapse>
  <el-table v-else :data="rows" size="small" data-test="stat-table">
    <el-table-column label="指标" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">{{ labelOf(row) }}</template>
    </el-table-column>
    <el-table-column v-for="c in VALUE_COLS" :key="c.prop" min-width="72" :label="c.label">
      <template #default="{ row }">{{ c.fmt(row[c.prop]) }}</template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.empty { color: var(--el-text-color-secondary); }
</style>

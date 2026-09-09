<script setup lang="ts">
// src/components/perf/PerfSummaryTable.vue
// 性能汇总统计表:extractStatRows → el-table;error 摘要呈错误条,空呈占位文案。
import { computed } from 'vue'
import { extractStatRows, type PerfSummary, type StatRow } from './perfOption'

const props = defineProps<{ summary?: PerfSummary }>()

const rows = computed<StatRow[]>(() => extractStatRows(props.summary ?? null))
const errorMsg = computed(() => {
  const e = props.summary?.error
  return e == null ? '' : String(e)
})

// 指标列直显,其余数值列统一 null 防御 + 两位小数
const VALUE_COLS: { prop: keyof StatRow; label: string }[] = [
  { prop: 'sampleCount', label: '样本数' },
  { prop: 'min', label: '最小' },
  { prop: 'max', label: '最大' },
  { prop: 'mean', label: '均值' },
  { prop: 'median', label: '中位' },
  { prop: 'p90', label: 'P90' },
]

function fmt(v: unknown): string {
  return v == null ? '—' : Number(v).toFixed(2)
}
</script>

<template>
  <el-alert v-if="errorMsg" type="error" :closable="false" :title="`性能汇总解析失败:${errorMsg}`" />
  <p v-else-if="!rows.length" class="empty">暂无统计</p>
  <el-table v-else :data="rows" size="small" data-test="stat-table">
    <el-table-column prop="index" label="指标" min-width="110" />
    <el-table-column v-for="c in VALUE_COLS" :key="c.prop" min-width="72" :label="c.label">
      <template #default="{ row }">{{ fmt(row[c.prop]) }}</template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.empty { color: var(--el-text-color-secondary); }
</style>

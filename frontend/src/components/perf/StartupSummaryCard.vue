<script setup lang="ts">
// src/components/perf/StartupSummaryCard.vue
// 启动耗时卡片:startup_summary 是后端透传的原始 JSON,键集不固定——
// 已知键(LaunchState/ThisTime/TotalTime/WaitTime)按固定顺序优先,其余键防御追加,不猜字段名。
import { computed } from 'vue'

const props = defineProps<{ summary?: Record<string, unknown> | null }>()

const KNOWN_ORDER = ['ThisTime', 'TotalTime', 'WaitTime', 'LaunchState'] as const

const entries = computed<[string, unknown][]>(() => {
  const s = props.summary
  if (!s || typeof s !== 'object') return []
  const known = KNOWN_ORDER.filter((k) => k in s).map((k) => [k, s[k]] as [string, unknown])
  const rest = Object.keys(s)
    .filter((k) => !(KNOWN_ORDER as readonly string[]).includes(k))
    .map((k) => [k, s[k]] as [string, unknown])
  return [...known, ...rest]
})

const errorMsg = computed(() => {
  const e = props.summary?.error
  return e == null ? '' : String(e)
})

function fmtVal(v: unknown): string {
  if (v == null) return '—'
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}
</script>

<template>
  <el-alert v-if="errorMsg" type="error" :closable="false" :title="`启动汇总解析失败:${errorMsg}`" />
  <p v-else-if="!entries.length" class="empty">暂无启动数据</p>
  <el-descriptions v-else size="small" :column="2" border class="startup-card">
    <el-descriptions-item v-for="[k, v] in entries" :key="k" :label="k">{{ fmtVal(v) }}</el-descriptions-item>
  </el-descriptions>
</template>

<style scoped>
.startup-card { margin-bottom: 8px; }
.empty { color: var(--el-text-color-secondary); }
</style>

<script setup lang="ts">
import { computed } from 'vue'
import type { AppPerfSeries } from '../../types'

const props = defineProps<{ series: AppPerfSeries[] }>()
const W = 480
const H = 140

interface Chart { item: string; points: string; color: string }

const PALETTE = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399']

function numericCol(s: AppPerfSeries): number {
  for (let c = 1; c < s.columns.length; c++) {
    if (s.rows.every((r) => Number.isFinite(Number(r[c])))) return c
  }
  return -1
}

const charts = computed<Chart[]>(() => {
  const out: Chart[] = []
  props.series.forEach((s, si) => {
    const c = numericCol(s)
    if (c < 0 || s.rows.length < 2) return
    const vals = s.rows.map((r) => Number(r[c]))
    const min = Math.min(...vals)
    const max = Math.max(...vals)
    const span = max - min || 1
    const pts = vals
      .map((v, i) => `${(i / (vals.length - 1)) * W},${H - ((v - min) / span) * (H - 10) - 5}`)
      .join(' ')
    out.push({ item: s.item, points: pts, color: PALETTE[si % PALETTE.length] })
  })
  return out
})
</script>

<template>
  <div class="perf-chart">
    <svg :viewBox="`0 0 ${W} ${H}`" class="grid">
      <polyline v-for="c in charts" :key="c.item" :points="c.points" fill="none"
                :stroke="c.color" stroke-width="1.5" />
    </svg>
    <div class="legend">
      <span v-for="c in charts" :key="c.item" :style="{ color: c.color }">{{ c.item }}</span>
      <span v-for="s in series.filter((x) => numericCol(x) < 0)" :key="s.item" class="skip">{{ s.item }}(无数值列)</span>
    </div>
  </div>
</template>

<style scoped>
.grid { width: 100%; background: var(--el-fill-color-light); border-radius: 4px; }
.legend { display: flex; gap: 12px; font-size: 12px; margin-top: 4px; }
.legend .skip { color: var(--el-text-color-secondary); }
</style>

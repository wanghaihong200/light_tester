<script setup lang="ts">
// 分发批量对比(计划12入口保留;计划14 Task12 换芯):
// 性能汇总列 JSON 折叠 → PerfSummaryTable;表格下新增跨 run 曲线叠加(item 前缀设备号,单图对比)。
import { onMounted, ref } from 'vue'
import { getAppComparison, getAppRunPerfSeries } from '../../api/appAutomation'
import type { AppPerfSeries, AppRun } from '../../types'
import PerfCharts from '../perf/PerfCharts.vue'
import PerfSummaryTable from '../perf/PerfSummaryTable.vue'

const props = defineProps<{ projectId: number; batchId: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const scriptName = ref('')
const runs = ref<AppRun[]>([])
// 只对有 perf_summary 的 run 拉曲线;全部失败/无数据时为空数组 → 叠加区块整体不渲染
const mergedSeries = ref<AppPerfSeries[]>([])

onMounted(async () => {
  const r = await getAppComparison(props.projectId, props.batchId)
  scriptName.value = r.script_name
  runs.value = r.runs
  // allSettled:单个 run 曲线拉取失败静默跳过,不影响其余设备;收集后一次性 set,
  // PerfCharts 的 watch(series) 只触发一次重渲染
  const settled = await Promise.allSettled(
    r.runs.filter((run) => run.perf_summary).map(async (run) => {
      const { series } = await getAppRunPerfSeries(run.id)
      return series.map((s) => ({ ...s, item: `${run.device_serial} · ${s.item}` }))
    }),
  )
  mergedSeries.value = settled.flatMap((s) => (s.status === 'fulfilled' ? s.value : []))
})
</script>

<template>
  <el-dialog :model-value="true" :title="`分发批量对比 · ${scriptName}`" width="820px"
             @update:model-value="emit('close')">
    <el-table :data="runs">
      <el-table-column prop="device_serial" label="设备" />
      <el-table-column label="平台状态">
        <template #default="{ row }">{{ row.status }}<template v-if="row.run_state"> / {{ row.run_state }}</template></template>
      </el-table-column>
      <el-table-column label="检查点">
        <template #default="{ row }">
          <template v-if="row.check_results">
            前置 {{ (row.check_results.pre ?? []).every((c: any) => c.passed) ? '✅' : '❌' }}
            后置 {{ (row.check_results.post ?? []).every((c: any) => c.passed) ? '✅' : '❌' }}
          </template>
          <template v-else>—</template>
        </template>
      </el-table-column>
      <el-table-column prop="error" label="失败原因" />
      <el-table-column label="性能汇总">
        <template #default="{ row }">
          <PerfSummaryTable v-if="row.perf_summary" :summary="row.perf_summary" />
          <template v-else>—</template>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="mergedSeries.length" class="overlay" data-test="compare-perf-charts">
      <h4>性能曲线叠加</h4>
      <PerfCharts :series="mergedSeries" />
    </div>
  </el-dialog>
</template>

<style scoped>
.overlay { margin-top: 12px; }
.overlay h4 { margin: 0 0 8px; }
</style>

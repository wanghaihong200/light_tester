<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAppComparison } from '../../api/appAutomation'
import type { AppRun } from '../../types'

const props = defineProps<{ projectId: number; batchId: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const scriptName = ref('')
const runs = ref<AppRun[]>([])

onMounted(async () => {
  const r = await getAppComparison(props.projectId, props.batchId)
  scriptName.value = r.script_name
  runs.value = r.runs
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
          <details v-if="row.perf_summary"><summary>展开</summary>
            <pre>{{ JSON.stringify(row.perf_summary, null, 2) }}</pre></details>
          <template v-else>—</template>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

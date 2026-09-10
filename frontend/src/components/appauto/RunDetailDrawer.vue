<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getAppRun, getAppRunPerfSeries, subscribeAppRunEvents, forceFinishAppRun } from '../../api/appAutomation'
import type { AppPerfSeries, AppRun } from '../../types'
import PerfCharts from '../perf/PerfCharts.vue'
import PerfSummaryTable from '../perf/PerfSummaryTable.vue'
import StartupSummaryCard from '../perf/StartupSummaryCard.vue'
// CLI perf-analyze 真实结构 {files:[…]} → 标准形(幂等;计划14 冒烟修复),曲线/统计表共用
import { normalizePerfSummary, type PerfSummary } from '../perf/perfOption'

const props = defineProps<{ visible: boolean; run: AppRun | null }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'changed'): void }>()

const current = ref<AppRun | null>(null)
const series = ref<AppPerfSeries[]>([])
const perfSummary = computed<PerfSummary>(() => normalizePerfSummary(current.value?.perf_summary))
let closeFn: (() => void) | null = null
const TERMINAL = ['passed', 'failed', 'cancelled']

function closeStream() {
  closeFn?.()
  closeFn = null
}

watch(() => [props.visible, props.run?.id] as const, async ([v, id]) => {
  if (!v || id == null) return
  current.value = props.run
  try { series.value = (await getAppRunPerfSeries(id)).series } catch { series.value = [] }
  closeStream()
  if (props.run && !TERMINAL.includes(props.run.status)) {
    closeFn = subscribeAppRunEvents(id, async (e) => {
      // snapshot = SSE 断线兜底回读的终态(api 层 onerror),消费语义与 done 一致
      if (e.type === 'done' || e.type === 'error' || e.type === 'snapshot') {
        closeStream()
        try { current.value = await getAppRun(id) } catch { /* 忽略 */ }
        emit('changed')
      }
    })
  }
}, { immediate: true })

// brief 实现注意②:drawer 关闭即断流(组件卸载同理),避免关抽屉后 EventSource 挂着重连
watch(() => props.visible, (v) => {
  if (!v) closeStream()
})
onUnmounted(closeStream)

async function forceFinish() {
  if (!current.value) return
  try {
    await forceFinishAppRun(current.value.id)
    current.value = await getAppRun(current.value.id)
    emit('changed')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '强制结束失败')
  }
}
</script>

<template>
  <el-drawer :model-value="visible" size="55%" :title="`执行 #${run?.id} 详情`"
             @update:model-value="emit('update:visible', $event)">
    <template v-if="current">
      <p>设备 <b>{{ current.device_serial }}</b> · 平台状态 <b>{{ current.status }}</b>
         · 端上终态 <b>{{ current.run_state ?? '—' }}</b></p>
      <el-alert v-if="current.error" type="error" :closable="false" :title="current.error" />
      <h4>检查点</h4>
      <template v-for="kind in (['pre', 'post'] as const)" :key="kind">
        <div v-if="current.check_results?.[kind]?.length">
          <b>{{ kind === 'pre' ? '前置' : '后置' }}</b>
          <div v-for="(r, i) in current.check_results[kind]" :key="i">
            {{ r.passed ? '✅' : '❌' }} {{ r.detail }}
          </div>
        </div>
      </template>
      <h4>性能曲线</h4>
      <PerfCharts :series="series" :summary="perfSummary" />
      <h4>性能汇总 / 启动耗时</h4>
      <PerfSummaryTable :summary="perfSummary" />
      <StartupSummaryCard :summary="current.startup_summary" />
      <h4>端上步骤结果</h4>
      <pre v-if="current.results">{{ JSON.stringify(current.results, null, 2) }}</pre>
      <el-button v-if="!TERMINAL.includes(current.status)" type="danger" @click="forceFinish">强制结束</el-button>
    </template>
  </el-drawer>
</template>

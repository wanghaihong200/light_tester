<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getAppRun, getAppRunPerfSeries, subscribeAppRunEvents, forceFinishAppRun } from '../../api/appAutomation'
import type { AppPerfSeries, AppRun } from '../../types'
import PerfChart from './PerfChart.vue'

const props = defineProps<{ visible: boolean; run: AppRun | null }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'changed'): void }>()

const current = ref<AppRun | null>(null)
const series = ref<AppPerfSeries[]>([])
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
      if (e.type === 'done' || e.type === 'error') {
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
      <PerfChart v-if="series.length" :series="series" />
      <p v-else style="color: var(--el-text-color-secondary)">本次未采集性能或数据未落盘</p>
      <h4>性能汇总 / 启动耗时</h4>
      <pre v-if="current.perf_summary">{{ JSON.stringify(current.perf_summary, null, 2) }}</pre>
      <pre v-if="current.startup_summary">{{ JSON.stringify(current.startup_summary, null, 2) }}</pre>
      <h4>端上步骤结果</h4>
      <pre v-if="current.results">{{ JSON.stringify(current.results, null, 2) }}</pre>
      <el-button v-if="!TERMINAL.includes(current.status)" type="danger" @click="forceFinish">强制结束</el-button>
    </template>
  </el-drawer>
</template>

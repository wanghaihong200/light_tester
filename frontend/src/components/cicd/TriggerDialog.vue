<!-- frontend/src/components/cicd/TriggerDialog.vue -->
<template>
  <el-dialog :model-value="modelValue" title="执行确认" width="640px" @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <el-table :data="rows" size="small" v-loading="loading">
      <el-table-column prop="name" label="计划" min-width="130" />
      <el-table-column prop="kind" label="类型" width="70" />
      <el-table-column prop="branch" label="分支" width="120" />
      <el-table-column label="新鲜度" min-width="150">
        <template #default="{ row }">
          <el-tag v-if="row.freshness?.stale" type="warning" size="small">有新代码未同步</el-tag>
          <el-tag v-else type="success" size="small">新鲜</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="物料" width="110">
        <template #default="{ row }">可执行 {{ row.valid }} / 缺失 {{ row.missing }}</template>
      </el-table-column>
      <el-table-column label="错误" min-width="140">
        <template #default="{ row }"><span class="err">{{ row.error ?? '' }}</span></template>
      </el-table-column>
    </el-table>

    <el-alert v-if="hasStale" class="stale-alert" type="warning" :closable="false"
              title="部分计划所在分支检测到未推送变更(老代码执行)" />
    <el-checkbox v-if="hasStale" v-model="agree" class="agree-box">
      我已知悉:将按 Jenkins 侧远端现状(老代码)执行
    </el-checkbox>
    <div v-if="failures.length" class="failures">
      <div v-for="f in failures" :key="f.plan_id" class="err">计划 {{ f.plan_id }}:{{ f.error }}</div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button class="do-trigger" type="primary" :disabled="!canTrigger" :loading="triggering" @click="doTrigger">
        执行({{ planIds.length }})
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { preflight, triggerRuns } from '../../api/cicd'
import type { CiRun, PreflightItem } from '../../api/cicd'

const props = defineProps<{ projectId: number; planIds: number[]; modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'triggered', runs: CiRun[]): void }>()

const rows = ref<PreflightItem[]>([])
const agree = ref(false)
const loading = ref(false)
const triggering = ref(false)
const failures = ref<{ plan_id: number; error: string }[]>([])

const hasStale = computed(() => rows.value.some((r) => r.freshness?.stale))
const hasError = computed(() => rows.value.some((r) => r.error))
const canTrigger = computed(() => !loading.value && !hasError.value && (!hasStale.value || agree.value))

async function doTrigger(): Promise<void> {
  triggering.value = true
  try {
    const res = await triggerRuns(props.projectId, props.planIds, agree.value)
    failures.value = res.failures
    if (res.runs.length) {
      ElMessage.success(`已触发 ${res.runs.length} 条执行`)
      emit('triggered', res.runs)
    }
    if (!res.failures.length) emit('update:modelValue', false)
  } finally {
    triggering.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    rows.value = await preflight(props.projectId, props.planIds)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.agree-box { margin: 10px 0; }
.err { color: var(--el-color-danger); font-size: 12px; }
.failures { margin-top: 8px; }
</style>

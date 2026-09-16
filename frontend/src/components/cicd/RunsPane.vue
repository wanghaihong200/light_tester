<!-- frontend/src/components/cicd/RunsPane.vue -->
<template>
  <div class="runs-pane">
    <div class="toolbar"><h2>执行记录</h2></div>
    <el-table :data="runs" @row-click="(row: CiRun) => goDetail(row.id)">
      <el-table-column prop="id" label="#" width="70" class-name="row-click" />
      <el-table-column prop="plan_name" label="计划" min-width="150" class-name="row-click" show-overflow-tooltip />
      <el-table-column label="类型" width="80" class-name="row-click">
        <template #default="{ row }">{{ row.kind === 'ui' ? 'UI' : '接口' }}</template>
      </el-table-column>
      <el-table-column prop="branch" label="分支" width="140" class-name="row-click" show-overflow-tooltip />
      <el-table-column label="build" width="100" class-name="row-click">
        <template #default="{ row }">{{ row.build_number ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="TAG[row.status]">{{ STATUS_LABEL[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="通过/总数" width="110" class-name="row-click">
        <template #default="{ row }">{{ row.passed }}/{{ row.total }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="触发时间" width="180" class-name="row-click" />
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="goDetail(row.id)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listCiRuns } from '../../api/cicd'
import type { CiRun } from '../../api/cicd'

const props = defineProps<{ projectId: number }>()
const router = useRouter()

const TAG: Record<string, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
  queued: 'info', running: 'primary', success: 'success', failure: 'danger', aborted: 'warning', error: 'danger',
}
const STATUS_LABEL: Record<string, string> = {
  queued: '排队中', running: '执行中', success: '成功', failure: '失败', aborted: '已终止', error: '异常',
}

const runs = ref<CiRun[]>([])
let timer: ReturnType<typeof setInterval> | null = null

async function load(): Promise<void> {
  runs.value = await listCiRuns(props.projectId)
  const active = runs.value.some((r) => r.status === 'queued' || r.status === 'running')
  if (active && timer === null) timer = setInterval(load, 3000)
  if (!active && timer !== null) { clearInterval(timer); timer = null }
}

function goDetail(id: number): void {
  void router.push({ name: 'project-cicd-run-detail', params: { runId: String(id) } })
}

onMounted(load)
onUnmounted(() => { if (timer !== null) clearInterval(timer) })
</script>

<style scoped>
.runs-pane { padding: 16px 20px; }
.toolbar h2 { font-size: 18px; margin: 0 0 12px; }
.row-click { cursor: pointer; }
</style>

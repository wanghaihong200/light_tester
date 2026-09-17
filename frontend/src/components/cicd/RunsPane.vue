<!-- frontend/src/components/cicd/RunsPane.vue -->
<template>
  <div class="runs-pane">
    <div class="toolbar"><h2>执行记录</h2></div>
    <div class="table-wrap">
    <el-table :data="paged">
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column prop="plan_name" label="计划" min-width="150" show-overflow-tooltip />
      <el-table-column label="类型" width="80">
        <template #default="{ row }">{{ row.kind === 'ui' ? 'UI' : '接口' }}</template>
      </el-table-column>
      <el-table-column prop="branch" label="分支" width="140" show-overflow-tooltip />
      <el-table-column label="build" width="100">
        <template #default="{ row }">{{ row.build_number ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="TAG[row.status]">{{ STATUS_LABEL[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="通过/总数" width="110">
        <template #default="{ row }">{{ row.passed }}/{{ row.total }}</template>
      </el-table-column>
      <el-table-column label="执行时长" width="100">
        <template #default="{ row }">{{ ciRunDurationText(row.started_at, row.finished_at) }}</template>
      </el-table-column>
      <el-table-column label="触发时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button link type="primary" @click="goDetail(row.id)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>
    </div>
    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="runs.length"
        background
        layout="total, sizes, prev, pager, next"
        size="small"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ciRunDurationText, listCiRuns } from '../../api/cicd'
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

// 前端分页:后端一次回近 100 条,页内切片即可
const page = ref(1)
const pageSize = ref(10)
const paged = computed(() => runs.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
// 记录减少(如清库/刷新)时把页码拉回合法范围
watch(() => runs.value.length, (len) => {
  const maxPage = Math.max(1, Math.ceil(len / pageSize.value))
  if (page.value > maxPage) page.value = maxPage
})

function fmtTime(iso: string): string {
  return iso ? iso.replace('T', ' ') : '-'
}

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
.runs-pane { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 8px 12px; }
.toolbar h2 { font-size: 18px; margin: 0 0 8px; }
.table-wrap { flex: 1 1 auto; min-height: 0; overflow: auto; }
.pager { display: flex; flex-shrink: 0; justify-content: flex-end; margin-top: 8px; }
</style>

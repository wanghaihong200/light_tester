<!-- frontend/src/components/cicd/RunDetailPage.vue -->
<template>
  <div class="run-detail">
    <div class="header">
      <el-button link @click="router.back()">← 返回</el-button>
      <h2>#{{ run?.id }} {{ run?.plan_name }}</h2>
      <el-tag v-if="run" :type="TAG[run.status]" size="small">{{ STATUS_LABEL[run.status] }}</el-tag>
      <div class="actions">
        <el-button v-if="run && isActive" size="small" type="warning" @click="doStop">停止</el-button>
        <el-button v-if="run" size="small" @click="doRerun">重跑</el-button>
        <el-button v-if="run?.jenkins_url" size="small" tag="a" :href="run.jenkins_url" target="_blank">
          Jenkins build {{ run.build_number }}
        </el-button>
      </div>
    </div>

    <div v-if="run" class="summary">
      <div class="stat"><span class="num">{{ run.total }}</span><span class="lbl">总数</span></div>
      <div class="stat pass"><span class="num">{{ run.passed }}</span><span class="lbl">通过</span></div>
      <div class="stat fail"><span class="num">{{ run.failed }}</span><span class="lbl">失败</span></div>
      <div class="stat"><span class="num">{{ run.skipped }}</span><span class="lbl">跳过</span></div>
      <div class="stat"><span class="num">{{ run.branch }}</span><span class="lbl">分支</span></div>
      <div class="stat" v-if="run.error"><span class="err">{{ run.error }}</span></div>
    </div>

    <el-table v-if="run" :data="caseRows" size="small" class="cases">
      <el-table-column prop="class_name" label="测试类" min-width="220" show-overflow-tooltip />
      <el-table-column prop="name" label="用例/方法" min-width="160" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'passed' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
            {{ ROW_LABEL[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="耗时(s)" width="90">
        <template #default="{ row }">{{ row.skipped_note ? '-' : row.time_s }}</template>
      </el-table-column>
      <el-table-column prop="message" label="失败信息" min-width="200" show-overflow-tooltip />
    </el-table>

    <pre v-if="run" class="console" ref="consoleEl">{{ logText }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ciRunEventsUrl, getCiRun, rerunCiRun, stopCiRun } from '../../api/cicd'
import type { CiRun } from '../../api/cicd'
import { withSseToken } from '../../api/client'

const route = useRoute()
const router = useRouter()

const TAG: Record<string, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
  queued: 'info', running: 'primary', success: 'success', failure: 'danger', aborted: 'warning', error: 'danger',
}
const STATUS_LABEL: Record<string, string> = {
  queued: '排队中', running: '执行中', success: '成功', failure: '失败', aborted: '已终止', error: '异常',
}
const ROW_LABEL: Record<string, string> = { passed: '通过', failed: '失败', skipped: '跳过', not_run: '未执行' }

const run = ref<CiRun | null>(null)
const logText = ref('')
const consoleEl = ref<HTMLElement | null>(null)
let es: EventSource | null = null

const isActive = computed(() => run.value?.status === 'queued' || run.value?.status === 'running')

// 报告行 = Jenkins 产物行 + 快照 skipped 行(未执行标注,ADR-0012 决策 4 的「报告标注」出口)
const caseRows = computed(() => {
  if (!run.value) return []
  const skippedRows = (run.value.selection ?? [])
    .filter((s) => s.skipped)
    .map((s) => ({
      class_name: 'name' in s ? s.name : s.ref,  // 判别键用必需的 name(ref? 可选无法窄化,vue-tsc TS2339)
      name: 'method' in s ? s.method : '脚本',
      status: 'not_run',
      time_s: 0,
      message: s.skip_reason === 'stale' ? '注册表已失效(标 stale)' : '仓内导出文件缺失',
      skipped_note: true,
    }))
  return [...(run.value.results ?? []), ...skippedRows]
})

function scrollBottom(): void {
  void nextTick(() => { if (consoleEl.value) consoleEl.value.scrollTop = consoleEl.value.scrollHeight })
}

async function load(): Promise<void> {
  run.value = await getCiRun(Number(route.params.runId))
  if (isActive.value) openStream()
}

function openStream(): void {
  es = new EventSource(withSseToken(ciRunEventsUrl(run.value!.id)))
  es.addEventListener('log', (e: MessageEvent) => {
    const d = JSON.parse(e.data) as { text: string }
    logText.value += d.text
    scrollBottom()
  })
  es.addEventListener('status', (e: MessageEvent) => {
    const d = JSON.parse(e.data) as { status: CiRun['status'] }
    if (run.value) run.value.status = d.status
  })
  es.addEventListener('done', async (e: MessageEvent) => {
    const d = JSON.parse(e.data) as { status: CiRun['status'] }
    es?.close()
    es = null
    if (run.value) run.value.status = d.status
    await load()  // done 后整跑重拉:results/统计就位
  })
}

async function doStop(): Promise<void> {
  await stopCiRun(run.value!.id)
  ElMessage.success('已停止')
  await load()
}

async function doRerun(): Promise<void> {
  const fresh = await rerunCiRun(run.value!.id)
  ElMessage.success('已重新触发')
  void router.replace({ name: 'project-cicd-run-detail', params: { runId: String(fresh.id) } })
  logText.value = ''
  await load()
}

onMounted(load)
onBeforeUnmount(() => { es?.close() })
</script>

<style scoped>
.run-detail { padding: 16px 20px; }
.header { align-items: center; display: flex; gap: 12px; margin-bottom: 12px; }
.header h2 { font-size: 18px; margin: 0; }
.actions { display: flex; gap: 8px; margin-left: auto; }
.summary { display: flex; gap: 24px; margin-bottom: 14px; }
.stat { display: flex; flex-direction: column; }
.stat .num { font-size: 20px; font-weight: 700; }
.stat .lbl { color: var(--pro-muted); font-size: 12px; }
.stat.pass .num { color: var(--el-color-success); }
.stat.fail .num { color: var(--el-color-danger); }
.console { background: #0d1117; color: #c9d1d9; font-size: 12px; height: 320px;
  margin-top: 14px; overflow: auto; padding: 10px; white-space: pre-wrap; }
</style>

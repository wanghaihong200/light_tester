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

    <div v-if="run" class="cases-wrap">
      <CaseTree :rows="caseRows" @locate="onLocate" />
    </div>

    <div class="console-head">
      <span class="console-title">执行日志</span>
      <span v-if="search" class="locate-info">定位「{{ search }}」命中 {{ matches.length }} 处</span>
      <el-button v-if="search" link size="small" @click="clearLocate">清除定位</el-button>
      <el-button class="full-btn" size="small" @click="fullLogVisible = true">全量日志</el-button>
    </div>
    <pre v-if="run" class="console" ref="consoleEl" v-html="consoleHtml"></pre>

    <el-dialog v-model="fullLogVisible" title="全量日志" width="80%" top="4vh" destroy-on-close>
      <pre class="log-full">{{ logText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ciRunEventsUrl, getCiRun, getCiRunConsole, rerunCiRun, stopCiRun } from '../../api/cicd'
import type { CiCaseRow, CiRun } from '../../api/cicd'
import { withSseToken } from '../../api/client'
import CaseTree from './CaseTree.vue'
import type { CaseRow } from './CaseTree.vue'

const route = useRoute()
const router = useRouter()

const TAG: Record<string, 'info' | 'primary' | 'success' | 'danger' | 'warning'> = {
  queued: 'info', running: 'primary', success: 'success', failure: 'danger', aborted: 'warning', error: 'danger',
}
const STATUS_LABEL: Record<string, string> = {
  queued: '排队中', running: '执行中', success: '成功', failure: '失败', aborted: '已终止', error: '异常',
}

const run = ref<CiRun | null>(null)
const logText = ref('')
const consoleEl = ref<HTMLElement | null>(null)
const fullLogVisible = ref(false)
const search = ref('')
const curMatch = ref(0)
let es: EventSource | null = null

const isActive = computed(() => run.value?.status === 'queued' || run.value?.status === 'running')

// 报告行 = Jenkins 产物行 + 快照 skipped 行(未执行标注,ADR-0012 决策 4 的「报告标注」出口)
const caseRows = computed<CaseRow[]>(() => {
  if (!run.value) return []
  const skippedRows = (run.value.selection ?? [])
    .filter((s) => s.skipped)
    .map((s): CaseRow => ({
      class_name: 'name' in s ? s.name : s.ref,  // 判别键用必需的 name(ref? 可选无法窄化,vue-tsc TS2339)
      name: 'method' in s ? s.method : '脚本',
      status: 'not_run',
      time_s: 0,
      message: s.skip_reason === 'stale' ? '未执行 · 注册表已失效(标 stale)' : '未执行 · 仓内导出文件缺失',
      skipped_note: true,
    }))
  return [...(run.value.results ?? []), ...skippedRows]
})

// ── 日志定位:命中处 <mark> 高亮,点击同用例循环跳下一条 ──

const matches = computed<number[]>(() => {
  const text = logText.value
  const needle = search.value
  if (!needle) return []
  const out: number[] = []
  let pos = 0
  while ((pos = text.indexOf(needle, pos)) !== -1) {
    out.push(pos)
    pos += needle.length
  }
  return out
})

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const consoleHtml = computed(() => {
  const text = logText.value
  const hits = matches.value
  if (!search.value || !hits.length) return escapeHtml(text)
  const parts: string[] = []
  let pos = 0
  hits.forEach((idx, i) => {
    parts.push(escapeHtml(text.slice(pos, idx)))
    const seg = escapeHtml(text.slice(idx, idx + search.value.length))
    parts.push(i === curMatch.value
      ? `<mark class="cur" data-i="${i}">${seg}</mark>`
      : `<mark data-i="${i}">${seg}</mark>`)
    pos = idx + search.value.length
  })
  parts.push(escapeHtml(text.slice(pos)))
  return parts.join('')
})

function onLocate(row: CiCaseRow): void {
  if (!logText.value) {
    ElMessage.info('日志为空,暂无可定位内容')
    return
  }
  if (search.value !== row.name) {
    search.value = row.name
    curMatch.value = 0
    if (!matches.value.length) {
      ElMessage.info('日志中没有该用例的独立输出片段(测试框架未逐用例输出)')
      return
    }
  } else {
    if (!matches.value.length) return
    curMatch.value = (curMatch.value + 1) % matches.value.length  // 循环跳下一条
  }
  void nextTick(() => {
    // jsdom 未实现 scrollIntoView,可选调用保测试环境不炸
    consoleEl.value?.querySelector('mark.cur')?.scrollIntoView?.({ block: 'center' })
  })
}

function clearLocate(): void {
  search.value = ''
  curMatch.value = 0
}

// ── 加载与直播 ──

async function load(): Promise<void> {
  const runId = Number(route.params.runId)
  run.value = await getCiRun(runId)
  // 全量日志走 REST;SSE 只负责活跃期增量直播(不再回放尾部,防重复/不完整)
  logText.value = await getCiRunConsole(runId)
  openStream()
}

function openStream(): void {
  if (es) es.close()  // 守卫:旧 run 流未关时重开(如 rerun 后)会把旧日志串进新 run
  es = new EventSource(withSseToken(ciRunEventsUrl(run.value!.id)))
  // 后端 _sse 只发 data-only 帧(事件名默认 message),addEventListener('log'…) 永不触发;
  // 须像 api/jobs.ts 一样用 onmessage 收,再按帧内 type 分发。
  es.onmessage = (e: MessageEvent) => {
    const d = JSON.parse(e.data) as { type: string; text?: string; status?: CiRun['status'] }
    if (d.type === 'log') {
      logText.value += d.text ?? ''
      void nextTick(() => { if (consoleEl.value) consoleEl.value.scrollTop = consoleEl.value.scrollHeight })
    } else if (d.type === 'status') {
      if (run.value && d.status) run.value.status = d.status
    } else if (d.type === 'snapshot') {
      // 终态流:快照即止。不显式关流会被 EventSource 视为断线自动重连,反复拉流
      es?.close()
      es = null
    } else if (d.type === 'done') {
      es?.close()
      es = null
      if (run.value && d.status) run.value.status = d.status
      // 终态落定:统计与全量日志一并重拉(REST 全量替换,直播文本与落盘日志完全对齐)
      void reload()
    }
  }
}

async function reload(): Promise<void> {
  const runId = Number(route.params.runId)
  const [fresh, consoleText] = await Promise.all([getCiRun(runId), getCiRunConsole(runId)])
  run.value = fresh
  logText.value = consoleText
}

async function doStop(): Promise<void> {
  await stopCiRun(run.value!.id)
  ElMessage.success('已停止')
  await load()
}

async function doRerun(): Promise<void> {
  const fresh = await rerunCiRun(run.value!.id)
  ElMessage.success('已重新触发')
  es?.close()  // 先关旧流:旧 run 仍活跃时其 log 事件不得串入新 run 的 logText
  es = null
  await router.replace({ name: 'project-cicd-run-detail', params: { runId: String(fresh.id) } })  // 等路由生效,load 才拉到新 runId
  logText.value = ''
  search.value = ''
  await load()
}

onMounted(load)
onBeforeUnmount(() => { es?.close() })
</script>

<style scoped>
/* 壳(.panel-body)已把本组件限高:整页纵向 flex,用例树与日志区各自内滚,不再溢出底部白框 */
.run-detail { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 16px 20px; }
.header { align-items: center; display: flex; gap: 12px; margin-bottom: 12px; }
.header h2 { font-size: 18px; margin: 0; }
.actions { display: flex; gap: 8px; margin-left: auto; }
.summary { display: flex; gap: 24px; margin-bottom: 12px; }
.stat { display: flex; flex-direction: column; }
.stat .num { font-size: 20px; font-weight: 700; }
.stat .lbl { color: var(--pro-muted); font-size: 12px; }
.stat.pass .num { color: var(--el-color-success); }
.stat.fail .num { color: var(--el-color-danger); }
.cases-wrap { border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  flex: 1 1 auto; margin-top: 4px; min-height: 120px; overflow: auto; padding: 6px; }
.console-head { align-items: center; display: flex; gap: 10px; margin-top: 10px; }
.console-title { font-size: 13px; font-weight: 600; }
.locate-info { color: var(--el-color-primary); font-size: 12px; }
.full-btn { margin-left: auto; }
.console { background: #0d1117; color: #c9d1d9; flex: 0 0 280px; font-size: 12px;
  margin-top: 6px; overflow: auto; padding: 10px; white-space: pre-wrap; }
.console :deep(mark) { background: rgba(210, 153, 34, 0.45); color: inherit; }
.console :deep(mark.cur) { background: var(--el-color-primary); color: #fff; }
.log-full { background: #0d1117; color: #c9d1d9; font-size: 12px; height: 70vh;
  margin: 0; overflow: auto; padding: 10px; white-space: pre-wrap; }
</style>

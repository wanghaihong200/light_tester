<template>
  <el-dialog
    :model-value="true"
    :title="historyMode ? `执行历史 · ${historyScriptName}` : 'UI 执行'"
    fullscreen
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @close="onClose"
  >
    <!-- ── 历史模式:只读回看,无 SSE ── -->
    <div v-if="historyMode" class="history">
      <aside class="run-list">
        <div
          v-for="r in historyRuns"
          :key="r.id"
          class="run-item"
          :class="{ active: r.id === selectedRunId }"
          @click="selectedRunId = r.id"
        >
          <div class="run-name">#{{ r.id }} {{ r.script_name }}</div>
          <div class="run-meta">
            <el-tag size="small" :type="statusTag(r.status)" disable-transitions>{{ statusText(r.status) }}</el-tag>
            <span class="muted">{{ formatTime(r.finished_at || r.started_at) }}</span>
          </div>
          <div class="muted">
            通过 {{ r.steps_passed }}/{{ r.steps_total }}<template v-if="r.steps_failed"> · 失败 {{ r.steps_failed }}</template>
          </div>
        </div>
        <div v-if="!historyRuns.length" class="empty">该脚本暂无执行记录</div>
      </aside>

      <section class="run-detail">
        <el-table
          v-if="selectedRun"
          :data="selectedRun.step_results"
          :row-class-name="rowClass"
          border
          size="small"
        >
          <el-table-column label="#" width="56">
            <template #default="{ row }">{{ row.index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="action" label="动作" min-width="120" />
          <el-table-column label="状态" width="70">
            <template #default="{ row }">{{ row.status === 'passed' ? '✅' : '❌' }}</template>
          </el-table-column>
          <el-table-column label="错误" min-width="180">
            <template #default="{ row }">
              <span v-if="row.error" class="err">{{ row.error }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="90">
            <template #default="{ row }">{{ row.elapsed_ms }}ms</template>
          </el-table-column>
          <el-table-column label="截图" width="150">
            <template #default="{ row }">
              <el-image
                v-if="row.screenshot"
                class="shot"
                :src="shotUrl(row.screenshot)"
                :preview-src-list="historyShots"
                preview-teleported
                hide-on-click-modal
                fit="cover"
              />
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="empty">选择左侧执行记录查看步骤详情</div>
      </section>
    </div>

    <!-- ── 执行模式:变量表单分步 → 帧图 + 步骤日志 ── -->
    <div v-else class="runner">
      <div class="queue-head">
        <span class="q-title">第 {{ idx + 1 }}/{{ queue.length }} 个:{{ current?.script.name }}</span>
        <el-tag v-if="runStatus !== 'pending'" size="small" :type="statusTag(runStatus)" disable-transitions>
          {{ statusText(runStatus) }}
        </el-tag>
        <el-tag v-if="allDone" size="small" type="success" disable-transitions>全部执行完毕</el-tag>
        <span v-if="summary" class="summary" :class="{ bad: runStatus === 'failed' }">{{ summary }}</span>
        <span class="spacer" />
        <el-button
          v-if="!historyMode && running && !finished"
          size="small" type="danger" plain :loading="forcing" @click="onForceFinish"
        >强制结束</el-button>
        <el-button v-if="allDone" size="small" @click="onClose">关闭</el-button>
      </div>

      <div class="runner-body">
        <section class="frame-pane">
          <div class="frame-box">
            <template v-if="frame">
              <img class="frame" :src="'data:image/jpeg;base64,' + frame" alt="执行画面" />
              <span v-if="frameStep >= 0" class="frame-badge">第 {{ frameStep + 1 }} 步</span>
            </template>
            <div v-else class="frame-empty">{{ waitingVars ? '等待确认执行参数…' : '等待浏览器画面…' }}</div>
          </div>
        </section>

        <!-- 步骤 1:脚本声明了变量、或项目存在登录态时,先在同一对话框内收集变量与登录态 -->
        <section v-if="waitingVars" class="side-pane">
          <div class="pane-head">执行「{{ waitingVars.name }}」前请确认参数</div>
          <div class="vars-body">
            <div v-for="v in waitingVars.script.variables" :key="v.name" class="var-item">
              <label class="var-label">{{ v.desc || v.name }}</label>
              <el-input v-model="varsForm[v.name]" :placeholder="v.name" maxlength="200" />
            </div>
            <div v-if="authStates.length" class="var-item">
              <label class="var-label">登录态</label>
              <el-select v-model="authId" class="auth-select" placeholder="不使用">
                <el-option label="不使用" value="" />
                <el-option v-for="a in authStates" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </div>
          </div>
          <div class="foot">
            <el-button type="primary" @click="confirmVars">开始执行本脚本</el-button>
          </div>
        </section>

        <!-- 步骤 2:执行中的步骤日志(step_start 建行,step_end 原位更新) -->
        <section v-else class="side-pane">
          <div class="pane-head">
            <span>步骤日志</span>
            <span class="muted">共 {{ current?.script.script.steps.length ?? 0 }} 步</span>
          </div>
          <el-scrollbar class="log-list">
            <div v-for="l in logs" :key="l.index" class="log-row" :class="l.status">
              <span class="idx">{{ l.index < 0 ? '-' : l.index + 1 }}</span>
              <span class="txt">{{ l.label }}</span>
              <span class="mark">{{ l.status === 'passed' ? '✅' : l.status === 'failed' ? '❌' : '⏳' }}</span>
              <el-image
                v-if="l.screenshot && running"
                class="shot"
                :src="runShotUrl(l.screenshot)"
                :preview-src-list="runShots"
                preview-teleported
                hide-on-click-modal
                fit="cover"
              />
              <div v-if="l.error" class="err">{{ l.error }}</div>
            </div>
            <div v-if="!logs.length" class="empty">等待执行…</div>
          </el-scrollbar>
        </section>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
// 执行对话框:两种互斥模式,由 WebAutoPane 接线(同一时间只喂一路)。
//  - queue 模式:按序批量执行。每脚本开跑前若声明了变量,先在本对话框内收集变量与登录态
//    (登录态下拉仅在项目存在登录态时出现),再 createUiRun → subscribeRunEvents 渲染;
//    done/error 即终态断流,800ms 后跑下一个;
//    入口 4xx(脚本不合法/无效 script_id/auth_state_id)透传 detail,跳过该脚本继续队列。
//  - history 模式:只读回看历史执行,点选左侧 run 渲染每步结果与截图,无 SSE。
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fetchBlobUrl } from '../../api/client'
import { createUiRun, forceFinishRun, listUiAuthStates, subscribeRunEvents } from '../../api/uiAutomation'
import type { UiAuthState, UiRun, UiScript, UiStep, UiStepResult } from '../../types'

type QueueItem = { script: UiScript; mode: 'headless' | 'headed' }

const props = defineProps<{
  projectId: number
  queue: QueueItem[]
  // WebAutoPane.onHistory 传 { script, runs }(listUiRuns 按脚本过滤结果)
  history?: { script: UiScript; runs: UiRun[] } | null
}>()
const emit = defineEmits<{ (e: 'closed'): void }>()

// ── 历史模式 ──────────────────────────────────
const historyRuns = computed<UiRun[]>(() => props.history?.runs ?? [])
const historyMode = computed(() => props.queue.length === 0 && props.history != null)
const historyScriptName = computed(() => props.history?.script.name ?? '')
const selectedRunId = ref<number | null>(null)
const selectedRun = computed(() => historyRuns.value.find((r) => r.id === selectedRunId.value) ?? null)
// run 列表变化(首次进入/切换脚本)时默认选中第一条,进来即可看步骤详情
watch(() => historyRuns.value.map((r) => r.id).join(','), (ids) => {
  if (!ids || !historyRuns.value.some((r) => r.id === selectedRunId.value)) {
    selectedRunId.value = historyRuns.value[0]?.id ?? null
  }
}, { immediate: true })

function statusTag(status: string): 'success' | 'danger' | 'primary' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'primary'
  return 'info'
}
function statusText(status: string): string {
  const map: Record<string, string> = { pending: '等待中', running: '执行中', completed: '已完成', failed: '失败' }
  return map[status] ?? status
}
function formatTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '-'
}
// 历史表失败步骤整行红标(配合 ❌ 与红色错误文案)
function rowClass({ row }: { row: UiStepResult }): string {
  return row.status === 'failed' ? 'row-failed' : ''
}
// 步骤中文摘要,口径与后端 events.step_summary / RecorderPanel 一致
function stepSummary(s: UiStep): string {
  const p = (s.params ?? {}) as Record<string, string>
  const loc = s.locator?.name || s.locator?.value || ''
  const map: Record<string, string> = {
    goto: `打开 ${p.url ?? ''}`, click: `点击 ${loc}`, fill: `输入 ${loc}=${p.text ?? ''}`,
    press: `按键 ${p.key ?? ''}`, select_option: `选择 ${loc}=${p.value ?? ''}`,
    wait: `等待 ${p.ms ?? 0}ms`, set_var: `设变量 ${p.name}=${p.value ?? ''}`,
    scroll: `滚动 横向${p.dx ?? 0} 纵向${p.dy ?? 0}`,
    assert_visible: `断言 可见 ${loc}`, assert_exists: `断言 存在 ${loc}`,
    assert_text: `断言 文本${p.mode === 'equals' ? '等于' : '包含'} ${p.text ?? ''}`,
  }
  return map[s.action] ?? s.action
}

// ── 执行模式 ──────────────────────────────────
interface LogRow { index: number; label: string; status: 'running' | 'passed' | 'failed'; error: string | null; screenshot: string | null }

const frame = ref('')
const frameStep = ref(-1)
const logs = ref<LogRow[]>([])
const running = ref<UiRun | null>(null)
const runStatus = ref('pending')
const summary = ref('')
const finished = ref(false)
const idx = ref(-1)
const stopFns: (() => void)[] = []
let stopped = false // 用户关闭对话框后不再继续队列
let releaseRun: (() => void) | null = null // 当前 run 的 Promise 放行(终态/关框都要能解阻塞)
let varsResolve: (() => void) | null = null

const current = computed<QueueItem | null>(() =>
  idx.value >= 0 && idx.value < props.queue.length ? props.queue[idx.value] : null)
const allDone = ref(false) // 批量全部跑完:停汇总页,由用户手动关闭(拍板 2026-09-04)

function stepLabel(index: number): string {
  const s = current.value?.script.script.steps[index]
  return s ? stepSummary(s) : `步骤 ${index + 1}`
}

// 日志行按 index upsert:step_start 建行「运行中」,step_end 原位更新状态/错误/截图
function upsert(row: LogRow) {
  const i = logs.value.findIndex((l) => l.index === row.index)
  if (i >= 0) logs.value[i] = { ...logs.value[i], ...row }
  else logs.value.push(row)
}

function closeStreams() {
  stopFns.forEach((f) => f())
  stopFns.length = 0
}

function finish() {
  finished.value = true
  closeStreams() // 终态即断流:后端关流后 EventSource 自动重连会打到 404 → 误报「连接中断」
  releaseRun?.()
  releaseRun = null
}

function onRunEvent(e: Record<string, unknown>) {
  const t = e.type
  if (t === 'frame') {
    frame.value = String(e.data ?? '')
    frameStep.value = Number(e.step_index ?? -1)
  } else if (t === 'step_start') {
    const i = Number(e.index)
    if (i < 0) {
      // index=-1 是环境预启步(后端步骤循环前发出):占位行,不是真实步骤
      logs.value.push({ index: -1, label: '启动浏览器…', status: 'running', error: null, screenshot: null })
      return
    }
    const env = logs.value.find((l) => l.index === -1 && l.status === 'running')
    if (env) env.status = 'passed' // 第一个真实步骤开始,预启步收尾
    upsert({ index: i, label: stepLabel(i), status: 'running', error: null, screenshot: null })
  } else if (t === 'step_end') {
    const i = Number(e.index)
    upsert({
      index: i,
      label: stepLabel(i),
      status: (e.status as LogRow['status']) ?? 'passed',
      error: (e.error as string) ?? null,
      screenshot: (e.screenshot as string) ?? null,
    })
  } else if (t === 'status') {
    runStatus.value = String(e.status ?? 'running')
  } else if (t === 'done') {
    if (finished.value) return // 已终态(snapshot/error 先到):迟到 done 不覆盖结论
    const s = (e.summary ?? {}) as { total?: number; passed?: number; duration_ms?: number }
    runStatus.value = e.status === 'failed' ? 'failed' : 'completed'
    summary.value = `通过 ${s.passed ?? 0}/${s.total ?? 0} · 耗时 ${((s.duration_ms ?? 0) / 1000).toFixed(1)} 秒`
    finish()
  } else if (t === 'error') {
    if (finished.value) return // 已终态:迟到/重连事件不再打扰
    runStatus.value = 'failed'
    summary.value = String(e.message ?? '执行异常')
    logs.value.forEach((l) => { if (l.status === 'running') l.status = 'failed' }) // 环境级错误:停在「运行中」的行收尾
    finish()
  } else if (t === 'snapshot') {
    // 订阅时 run 已终态(后端直接补快照):按快照收尾,避免队列挂起
    if (finished.value) return
    runStatus.value = e.status === 'failed' ? 'failed' : 'completed'
    summary.value = e.error
      ? String(e.error)
      : `通过 ${Number(e.steps_passed ?? 0)}/${Number(e.steps_total ?? 0)}`
    finish()
  }
}

// 强制结束(2026-09-04 需求:异常挂起在「执行中」时手动收口):后端置「执行异常」并向 SSE 推
// done;本地同时收尾放行队列(双路径幂等,后到者被 finished 守卫忽略),800ms 后继续下一个脚本
const forcing = ref(false)
async function onForceFinish() {
  if (running.value == null || finished.value || forcing.value) return
  try {
    await ElMessageBox.confirm('确定强制结束当前执行?状态将记为「执行异常」。', '强制结束', {
      confirmButtonText: '强制结束', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return // 用户取消
  }
  forcing.value = true
  try {
    await forceFinishRun(running.value.id)
    runStatus.value = 'failed'
    summary.value = '执行异常 · 用户强制结束'
    finish()
  } catch (e) {
    ElMessage.error(`强制结束失败:${(e as Error).message}`)
  } finally {
    forcing.value = false
  }
}

async function runOne(item: QueueItem, vars: Record<string, string>, authStateId?: number) {  logs.value = []
  frame.value = ''
  frameStep.value = -1
  summary.value = ''
  finished.value = false
  const run = await createUiRun(props.projectId, {
    script_id: item.script.id, mode: item.mode, variables: vars, auth_state_id: authStateId,
  })
  running.value = run
  return new Promise<void>((resolve) => {
    releaseRun = resolve
    stopFns.push(subscribeRunEvents(run.id, onRunEvent))
  })
}

// 执行前参数确认(同一对话框内分步,不套第二个 dialog):脚本声明了变量、或「项目存在
// 可用登录态但脚本没录登录态」才出面板;录了登录态的无变量脚本直接默认执行不询问(拍板:
// 变更入口在脚本编辑页)。表单预填 default;面板内存在可用登录态才出下拉(默认=录制的登录态)。
const waitingVars = ref<UiScript | null>(null)
const varsForm = ref<Record<string, string>>({})
const authStates = ref<UiAuthState[]>([])
const authId = ref<number | ''>('') // '' = 不使用登录态

// 脚本录制时用的登录态(仍在可用列表才有效;被删则视为没录,回退询问)
function recordedAuth(script: UiScript): number | null {
  const id = script.script.meta?.auth_state_id
  return id != null && authStates.value.some((a) => a.id === id) ? id : null
}

async function collectPreRun(script: UiScript) {
  varsForm.value = Object.fromEntries((script.script.variables ?? []).map((v) => [v.name, v.default ?? '']))
  authId.value = recordedAuth(script) ?? ''
  waitingVars.value = script
  await new Promise<void>((r) => { varsResolve = r }) // 模板「开始执行本脚本」按钮触发
  waitingVars.value = null
}

function confirmVars() {
  varsResolve?.()
  varsResolve = null
}

async function startQueue() {
  try {
    authStates.value = await listUiAuthStates(props.projectId)
  } catch {
    authStates.value = [] // 拉不到登录态不阻塞执行(面板退化为纯变量确认)
  }
  for (idx.value = 0; idx.value < props.queue.length; idx.value++) {
    if (stopped) return
    const item = props.queue[idx.value]
    varsForm.value = {} // 每脚本重置:上一脚本填的变量不得带给未声明变量的脚本
    const rec = recordedAuth(item.script)
    // 出面板条件:有变量要收集;或需要用户选登录态(项目有登录态但脚本没录)。录了登录态
    // 且无变量的脚本在此直跑,批量不顺停(有变量才停在变量表单)
    if (item.script.script.variables?.length || (authStates.value.length && rec == null)) {
      await collectPreRun(item.script)
      if (stopped) return
    } else {
      authId.value = rec ?? ''
    }
    try {
      await runOne(item, { ...varsForm.value }, authId.value === '' ? undefined : authId.value)
    } catch (e) {
      // 入口 400/409:后端 detail 透传给用户,跳过该脚本继续队列下一个
      ElMessage.error(`启动「${item.script.name}」失败:${(e as Error).message}`)
      continue
    }
    if (stopped) return
    await new Promise((r) => setTimeout(r, 800)) // 两个脚本间留出间隔,便于看清结果
  }
  // 拍板(2026-09-04):批量跑完停汇总页不自动关框,用户手动关闭
  allDone.value = true
}

// 停队列、断流、放行挂起的 async 帧(runPromise/varsResolve),避免组件实例悬挂泄漏。
// 两条路径共用:右上 X(@close → onClose)与父级直接卸载(切 tab 摘掉 v-if,@close 不触发)。
function abortAll() {
  stopped = true
  closeStreams()
  releaseRun?.()
  releaseRun = null
  varsResolve?.()
  varsResolve = null
}

function onClose() {
  abortAll()
  emit('closed')
}

// ── 截图鉴权加载:后端 401 门禁后 <img>/el-image 直链带不了 Authorization,
//    改 fetch→blob objectURL 渲染(键 runId/file,同图只取一次,卸载统一 revoke)──
const shotUrls = ref<Record<string, string>>({})
const shotPending = new Set<string>()

async function loadShot(runId: number, file: string): Promise<void> {
  const key = `${runId}/${file}`
  if (shotUrls.value[key] || shotPending.has(key)) return
  shotPending.add(key)
  try {
    shotUrls.value[key] = await fetchBlobUrl(`/ui-runs/${runId}/screens/${file}`)
  } catch {
    /* 404/401:缩略图留空,不打断执行/回看页 */
  }
}

function shotUrl(file: string): string {
  if (!selectedRun.value) return ''
  void loadShot(selectedRun.value.id, file)
  return shotUrls.value[`${selectedRun.value.id}/${file}`] ?? ''
}
function runShotUrl(file: string): string {
  if (!running.value) return ''
  void loadShot(running.value.id, file)
  return shotUrls.value[`${running.value.id}/${file}`] ?? ''
}

// 大图查看器的完整截图列表:el-image 以点击项在列表中的位置为起点,前后箭头跨步切换
const historyShots = computed(() =>
  (selectedRun.value?.step_results ?? []).filter((r) => r.screenshot).map((r) => shotUrl(r.screenshot!)))
const runShots = computed(() =>
  logs.value.filter((l) => l.screenshot).map((l) => runShotUrl(l.screenshot!)))

if (props.queue.length) startQueue()
onBeforeUnmount(() => {
  abortAll()
  for (const url of Object.values(shotUrls.value)) URL.revokeObjectURL(url)
})
</script>

<style scoped>
/* ── 历史模式 ── */
.history {
  display: flex;
  gap: 12px;
  height: calc(100vh - 150px);
  min-height: 320px;
}
.run-list {
  width: 300px;
  flex-shrink: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  background: var(--pro-card-bg);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-base);
}
.run-item {
  padding: 8px 10px;
  border: 1px solid var(--pro-line);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.run-item:hover {
  background: var(--el-fill-color-light);
}
.run-item.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.run-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}
.run-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}
.run-detail {
  flex: 1;
  min-width: 0;
}
.muted {
  font-size: 12px;
  color: var(--pro-muted);
}
.err {
  color: var(--el-color-danger);
  font-size: 12px;
  word-break: break-all;
}
.empty {
  padding: 16px 8px;
  font-size: 13px;
  color: var(--pro-muted);
}
.shot {
  width: 130px;
  height: 56px;
  border-radius: 4px;
  border: 1px solid var(--pro-line);
  cursor: zoom-in;
}
:deep(.el-table .row-failed) {
  background: var(--el-color-danger-light-9);
}

/* ── 执行模式 ── */
.runner {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: calc(100vh - 150px);
  min-height: 320px;
}
.queue-head {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.queue-head .summary {
  font-weight: 400;
  font-size: 13px;
  color: var(--el-color-primary);
}
.queue-head .summary.bad {
  color: var(--el-color-danger); /* 失败终态摘要用危险色,与主题蓝区分 */
}
.queue-head .spacer {
  flex: 1;
}
.runner-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 12px;
}
.frame-pane {
  flex: 1.5;
  min-width: 0;
  display: flex;
}
.frame-box {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-base);
  overflow: hidden;
}
.frame {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
/* 帧角标:头像式,标注当前画面所属步骤 */
.frame-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  color: var(--el-color-white);
  background: rgb(0 0 0 / 55%);
}
.frame-empty {
  color: var(--pro-muted);
  font-size: 13px;
}
.side-pane {
  flex: 1;
  min-width: 300px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--pro-card-bg);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-base);
}
.pane-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.pane-head .muted {
  font-weight: 400;
}
.log-list {
  flex: 1;
  min-height: 0;
}
.log-row {
  position: relative;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  border-left: 2px solid transparent;
}
.log-row:nth-child(odd) {
  background: var(--el-fill-color-light);
}
.log-row.running {
  border-left-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9); /* step_start 高亮当前行 */
}
.log-row .idx {
  min-width: 18px;
  text-align: right;
  font-size: 12px;
  color: var(--pro-muted);
}
.log-row .txt {
  word-break: break-all;
}
.log-row .shot {
  width: 64px;
  height: 32px;
  margin-left: auto;
}
.log-row .err {
  flex-basis: 100%;
}
.vars-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 4px;
}
.var-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.var-label {
  font-size: 12px;
  color: var(--pro-muted);
}
.foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--pro-line);
}
</style>

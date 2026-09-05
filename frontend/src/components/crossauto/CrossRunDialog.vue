<template>
  <el-dialog
    :model-value="visible"
    :title="`跨端运行 · ${script?.name ?? ''}`"
    fullscreen
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- ── 运行前:执行方式 + 变量收集 + 登录态/快照选择 ── -->
    <div v-if="!run" class="prep">
      <el-form label-width="96px" class="prep-form">
        <el-form-item v-if="target === 'web'" label="执行方式">
          <el-radio-group v-model="mode">
            <el-radio-button value="headless">无头执行</el-radio-button>
            <el-radio-button value="headed">有头执行</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-for="v in script?.script.variables ?? []" :key="v.name" :label="v.desc || v.name">
          <el-input v-model="varValues[v.name]" :placeholder="v.default ? `默认:${v.default}` : v.name" maxlength="200" />
        </el-form-item>
        <el-form-item v-if="authOptions.length" :label="authLabel">
          <el-select v-model="authId" placeholder="不使用">
            <el-option label="不使用" value="" />
            <el-option v-for="a in authOptions" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <div class="prep-tip">
        {{ targetTip }}
      </div>
    </div>

    <!-- ── 运行中/后:当前帧 + 步骤结果 + 终态摘要 ── -->
    <div v-else class="runner">
      <div class="run-head">
        <el-tag size="small" :type="statusTag(run.status)" disable-transitions>{{ statusText(run.status) }}</el-tag>
        <span v-if="reportPath" class="report">执行报告:{{ reportPath }}</span>
      </div>
      <div class="frame-box">
        <img v-if="frameUrl" class="frame" :src="frameUrl" alt="执行画面" />
        <div v-else class="frame-empty">等待画面…</div>
      </div>
      <el-table :data="run.step_results" border size="small" :row-class-name="rowClass">
        <el-table-column label="#" width="56">
          <template #default="{ row }">{{ row.index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="action" label="动作" min-width="120" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'passed' ? 'success' : 'danger'" disable-transitions>
              {{ row.status === 'passed' ? '通过' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ row.elapsed_ms }}ms</template>
        </el-table-column>
        <el-table-column label="错误" min-width="220">
          <template #default="{ row }">
            <span v-if="row.error" class="err">{{ row.error }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary" :class="{ bad: run.status === 'failed' }">
        <template v-if="run.status === 'completed' || run.status === 'failed'">
          {{ statusText(run.status) }} · 通过 {{ run.steps_passed }}/{{ run.steps_total }}<template v-if="run.steps_failed"> · 失败 {{ run.steps_failed }}</template>
          <span v-if="aiTokens" class="muted"> · AI tokens:{{ aiTokens }}</span>
        </template>
      </div>
    </div>

    <template #footer>
      <template v-if="!run">
        <el-button @click="emit('update:visible', false)">取消</el-button>
        <el-button type="primary" @click="submit">开始执行</el-button>
      </template>
      <el-button v-else @click="emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 跨端运行对话框(计划 10):运行前收变量/登录态(web_storage 或 android_snapshot),
// 提交 createUiRun 后订阅执行 SSE;预览帧是 b64 jpeg 事件,直接 data URL 渲染(不走截图文件端点)。
import { ElMessage } from 'element-plus'
import { computed, onUnmounted, ref, watch } from 'vue'
import type { UiAuthState, UiRun, UiScript } from '../../types'
import { createUiRun, getUiRun, subscribeRunEvents } from '../../api/uiAutomation'
import { listAuthStates } from '../../api/crossAutomation'

const props = defineProps<{ visible: boolean; projectId: number; script: UiScript | null }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const mode = ref<'headless' | 'headed'>('headless')
const varValues = ref<Record<string, string>>({})
const authId = ref<number | '' | null>(null)
const authOptions = ref<UiAuthState[]>([])
const run = ref<UiRun | null>(null)
const frameUrl = ref('')
const reportPath = ref('')
let unsub: (() => void) | null = null

const target = computed(() => props.script?.script.meta.target ?? 'web')
let kind: 'web_storage' | 'android_snapshot' | undefined

const authLabel = computed(() => (target.value === 'android' ? '应用数据快照' : '网页登录态'))
const targetTip = computed(() => {
  if (target.value === 'android') return '将恢复所选应用数据快照后,在真机/模拟器上执行 AI 步骤。'
  if (target.value === 'harmony') return '将在鸿蒙模拟器上执行 AI 步骤(暂不支持登录态)。'
  return '将在无头/有头浏览器中执行脚本,可选择已保存的网页登录态。'
})
// done 事件 usage 里的输入 token 数(后端 usage:{input_tokens,output_tokens,cost_usd,report_path})
const aiTokens = computed(() => {
  const u = run.value?.ai_usage as Record<string, unknown> | null | undefined
  return u && typeof u === 'object' && 'input_tokens' in u ? Number((u as Record<string, unknown>).input_tokens || 0) : 0
})

watch(() => props.visible, async (v) => {
  if (!v) return
  run.value = null; reportPath.value = ''; frameUrl.value = ''
  varValues.value = Object.fromEntries((props.script?.script.variables ?? []).map((x) => [x.name, x.default ?? '']))
  kind = target.value === 'android' ? 'android_snapshot' : target.value === 'web' ? 'web_storage' : undefined
  authOptions.value = kind ? await listAuthStates(props.projectId, kind) : []
  authId.value = null
})

async function onEvent(e: Record<string, unknown>) {
  // 预览帧是 b64 jpeg 事件,直接 data URL 渲染(不走截图文件端点)
  if (e.type === 'frame' && typeof e.data === 'string') {
    frameUrl.value = `data:image/jpeg;base64,${e.data}`
  } else if (e.type === 'step_end') {
    await refresh()
  } else if (e.type === 'done') {
    reportPath.value = String(e.report_path || '')
    await refresh()
  } else if (e.type === 'snapshot' || e.type === 'status') {
    await refresh()
  }
}

async function refresh(_e?: unknown) {
  if (!run.value) return
  run.value = await getUiRun(run.value.id)
  if (run.value.ai_usage && typeof run.value.ai_usage === 'object' && 'report_path' in (run.value.ai_usage as Record<string, unknown>)) {
    reportPath.value = String((run.value.ai_usage as Record<string, unknown>).report_path || reportPath.value)
  }
}

async function submit() {
  if (!props.script) return
  try {
    run.value = await createUiRun(props.projectId, {
      script_id: props.script.id, mode: mode.value,
      variables: { ...varValues.value },
      // 「不使用」选项 value 是空串,须归一为 undefined,否则后端 auth_state_id: int | None 会 422
      auth_state_id: authId.value || undefined,
    })
    unsub = subscribeRunEvents(run.value.id, onEvent)
  } catch (e) {
    ElMessage.error(String(e))
  }
}

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
function rowClass({ row }: { row: { status: string } }): string {
  return row.status === 'failed' ? 'row-failed' : ''
}

function onClose() {
  unsub?.()
  unsub = null
  emit('update:visible', false)
}
onUnmounted(() => unsub?.())
</script>

<style scoped>
.prep {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.prep-form {
  max-width: 640px;
}
.prep-tip {
  padding: 6px 10px;
  font-size: 12px;
  color: var(--pro-muted);
  background: var(--el-fill-color-light);
  border-radius: var(--border-radius-base);
}
.runner {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.run-head {
  align-items: center;
  display: flex;
  gap: 12px;
}
.report {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}
.frame-box {
  align-items: center;
  background: var(--el-fill-color-light);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-base);
  display: flex;
  justify-content: center;
  min-height: 220px;
  padding: 8px;
}
.frame {
  max-height: 420px;
  max-width: 100%;
}
.frame-empty {
  color: var(--pro-muted);
  font-size: 13px;
}
.muted {
  color: var(--pro-muted);
  font-size: 12px;
}
.err {
  color: var(--el-color-danger);
  font-size: 12px;
}
.summary {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.summary.bad {
  color: var(--el-color-danger);
}
</style>

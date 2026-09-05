<template>
  <el-dialog
    :model-value="true"
    title="UI 录制"
    fullscreen
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @close="onDiscard"
  >
    <div class="recorder">
      <!-- 左:实时画面 -->
      <section class="frame-pane">
        <div class="pane-head">
          <span class="live-dot" :class="{ off: !!stopDraft }" />
          <span>{{ stopDraft ? '录制已结束' : '录制中' }}</span>
          <span class="muted">已录 {{ steps.length }} 步</span>
        </div>
        <div class="frame-box">
          <img v-if="frame" class="frame" :src="'data:image/jpeg;base64,' + frame" alt="实时画面" />
          <div v-else class="frame-empty">等待浏览器画面…</div>
        </div>
      </section>

      <!-- 右:实时步骤 + 停止/保存 -->
      <section class="steps-pane">
        <div class="pane-head">录制步骤</div>
        <el-scrollbar class="step-list">
          <div v-for="(s, i) in steps" :key="s.id" class="rec-step">
            <span class="idx">{{ i + 1 }}</span>
            <span class="txt">{{ summary(s) }}</span>
          </div>
          <div v-if="steps.length === 0" class="step-empty">暂无步骤,去浏览器里操作试试</div>
        </el-scrollbar>
        <div class="foot">
          <el-button v-if="!stopDraft" type="danger" :loading="stopping" @click="onStop">停止并保存</el-button>
          <el-button v-else type="primary" :loading="saving" @click="onSave">保存已录步骤</el-button>
          <el-button @click="onDiscard">放弃</el-button>
        </div>
      </section>
    </div>

    <!-- 断言类型选择(assert_candidate 点击后的小选择框) -->
    <el-dialog
      :model-value="!!assertTarget"
      title="添加断言"
      width="440"
      :close-on-click-modal="false"
      @update:model-value="closeAssert"
    >
      <div v-if="assertTarget" class="assert-target">
        目标元素:<span class="tgt">{{ targetDesc(assertTarget) }}</span>
      </div>
      <el-radio-group v-model="assertChoice" class="assert-choices">
        <el-radio value="assert_visible">可见</el-radio>
        <el-radio value="contains">文本包含</el-radio>
        <el-radio value="equals">文本等于</el-radio>
        <el-radio value="assert_exists">元素存在</el-radio>
      </el-radio-group>
      <el-input
        v-if="isTextChoice"
        v-model="assertText"
        placeholder="输入要断言的文本"
        maxlength="200"
      />
      <template #footer>
        <el-button @click="closeAssert">取消</el-button>
        <el-button type="primary" :loading="asserting" @click="confirmAssert">确定</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
// 录制面板:全屏对话框,左侧实时帧、右侧步骤流。流式 action 事件按 step.id 原位刷新
// (逐字输入同一 fill 的 id 恒定、text 逐次更新),summary 前端自算(重连补发不带该字段);
// 断言候选选定类型后回调 insertAssert,断言步骤由后端以 action 事件推回,前端不本地拼。
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  cancelRecording, createUiScript, insertAssert, startRecording, stopRecording,
  subscribeRecordingEvents,
} from '../../api/uiAutomation'
import type { UiScriptDoc, UiStep, UiVariable } from '../../types'

// authStateId:父级(WebAutoPane 录制入口选择框)选定的登录态,启动录制浏览器时注入
const props = defineProps<{ projectId: number; authStateId?: number }>()
const emit = defineEmits<{ (e: 'saved'): void; (e: 'closed'): void }>()

const rid = ref<number | null>(null)
const frame = ref('')
const steps = ref<UiStep[]>([])
// 断言候选(assert_candidate 带来的 target)与用户选择
const assertTarget = ref<Record<string, unknown> | null>(null)
const assertChoice = ref<'assert_visible' | 'assert_exists' | 'contains' | 'equals'>('assert_visible')
const assertText = ref('')
const isTextChoice = computed(() => assertChoice.value === 'contains' || assertChoice.value === 'equals')
// 停止产出的草稿:主动停止取 stop API 返回;用户直接关浏览器窗(stopped)时本地兜底
const stopDraft = ref<{ meta: { start_url: string }; variables: UiVariable[]; steps: UiStep[] } | null>(null)
const stopping = ref(false)
// 防重复提交:断言确认 / 保存 await 期间按钮 loading 并早退(与 stopping 同款守卫)
const asserting = ref(false)
const saving = ref(false)
let unsubscribe: (() => void) | null = null

// 中文摘要,与后端 events.step_summary 口径一致
function summary(s: UiStep): string {
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

function targetDesc(t: Record<string, unknown>): string {
  const tag = t.tag ? String(t.tag) : '元素'
  const id = t.id ? `#${t.id}` : ''
  const text = t.text ? `「${String(t.text).slice(0, 20)}」` : ''
  return `${tag}${id} ${text}`.trim()
}

function localDraft() {
  const p = (steps.value.find((s) => s.action === 'goto')?.params ?? {}) as { url?: string }
  return { meta: { start_url: p.url ?? '' }, variables: [] as UiVariable[], steps: [...steps.value] }
}

function onEvent(e: Record<string, unknown>) {
  if (e.type === 'frame') {
    frame.value = String(e.data ?? '')
  } else if (e.type === 'action') {
    const st = e.step as UiStep
    const i = steps.value.findIndex((s) => s.id === st.id)
    if (i >= 0) steps.value[i] = st // 原位刷新:逐字输入 / 断线重连补发
    else steps.value.push(st)
  } else if (e.type === 'assert_candidate') {
    assertTarget.value = (e.target ?? {}) as Record<string, unknown>
    assertChoice.value = 'assert_visible'
    assertText.value = ''
  } else if (e.type === 'stopped') {
    // 终态即无条件断流:后端关流后 EventSource 会自动重连打到 404 → onerror 误报「连接中断」;
    // 主动停止(stopping 在途)时这里只断流,草稿仍以随后返回的 stop API 结果为权威。
    closeStream()
    if (stopping.value || stopDraft.value) return
    stopDraft.value = localDraft()
    ElMessage.warning('浏览器窗口已关闭,可保存已录步骤')
  } else if (e.type === 'error') {
    if (stopDraft.value || stopping.value) return // 已终态 / 停止在途:重连失败不必打扰
    ElMessage.error(String(e.message ?? '连接中断'))
  }
}

function closeStream() {
  unsubscribe?.()
  unsubscribe = null
}

async function begin() {
  try {
    const { recording_id } = await startRecording(props.projectId, props.authStateId)
    rid.value = recording_id
    unsubscribe = subscribeRecordingEvents(recording_id, onEvent)
  } catch (e) {
    ElMessage.error(`启动录制失败:${(e as Error).message}`)
    emit('closed')
  }
}
begin()

function closeAssert() {
  assertTarget.value = null
  assertText.value = ''
}

async function confirmAssert() {
  if (asserting.value || !assertTarget.value || rid.value == null) return
  const text = assertText.value.trim()
  if (isTextChoice.value && !text) {
    ElMessage.warning('请输入断言文本')
    return
  }
  asserting.value = true
  try {
    await insertAssert(rid.value, {
      target: assertTarget.value,
      assert_type: isTextChoice.value ? 'assert_text' : assertChoice.value,
      text: isTextChoice.value ? text : undefined,
      mode: isTextChoice.value ? assertChoice.value : undefined,
    })
    closeAssert()
  } catch (e) {
    ElMessage.error(`添加断言失败:${(e as Error).message}`)
  } finally {
    asserting.value = false
  }
}

async function onStop() {
  if (rid.value == null || stopDraft.value) return
  stopping.value = true
  try {
    stopDraft.value = await stopRecording(rid.value)
    closeStream() // 同 stopped 路径:终态即断流,避免重连 404 误报
  } catch (e) {
    ElMessage.error(`停止录制失败:${(e as Error).message}`)
  } finally {
    stopping.value = false
  }
}

async function onSave() {
  if (saving.value || !stopDraft.value) return
  saving.value = true
  try {
    let name: string
    try {
      const r = await ElMessageBox.prompt('请输入脚本名称', '保存录制脚本', {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '脚本名称不能为空',
      })
      name = r.value.trim()
    } catch {
      return // 用户取消
    }
    const draft = stopDraft.value
    // 录制时选定的登录态写进 meta:执行默认带上(选择框"不使用"则不写该键)
    const meta = { ...draft.meta }
    if (props.authStateId != null) meta.auth_state_id = props.authStateId
    const doc: UiScriptDoc = {
      version: 1, meta, variables: draft.variables, steps: draft.steps,
    }
    await createUiScript(props.projectId, { name, script: doc })
    ElMessage.success('脚本已保存')
    emit('saved')
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

async function onDiscard() {
  if (rid.value != null) await cancelRecording(rid.value).catch(() => {})
  emit('closed')
}

onBeforeUnmount(closeStream)
</script>

<style scoped>
.recorder {
  display: flex;
  gap: 12px;
  height: calc(100vh - 150px);
  min-height: 320px;
}
.frame-pane {
  flex: 1.5;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.frame-box {
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
.frame-empty {
  color: var(--pro-muted);
  font-size: 13px;
}
.steps-pane {
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
.step-list {
  flex: 1;
  min-height: 0;
}
.rec-step {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.rec-step:nth-child(odd) {
  background: var(--el-fill-color-light);
}
.rec-step .idx {
  min-width: 18px;
  text-align: right;
  font-size: 12px;
  color: var(--pro-muted);
}
.rec-step .txt {
  word-break: break-all;
}
.step-empty {
  padding: 16px 8px;
  font-size: 13px;
  color: var(--pro-muted);
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
  font-size: 12px;
  color: var(--pro-muted);
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-danger);
  animation: rec-blink 1.2s infinite;
}
.live-dot.off {
  background: var(--pro-muted);
  animation: none;
}
@keyframes rec-blink {
  50% {
    opacity: 0.25;
  }
}
.foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--pro-line);
}
.assert-target {
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.assert-target .tgt {
  color: var(--el-color-primary);
}
.assert-choices {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}
</style>

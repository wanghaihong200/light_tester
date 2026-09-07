<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createAppScript, updateAppScript } from '../../api/appAutomation'
import type { AppCaseJson, AppCaseStep, AppScript } from '../../types'

const props = defineProps<{ projectId: number; script: AppScript | null }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved', s: AppScript): void }>()

// 与后端 appium_export.SUPPORTED 对齐(勿加 IF/WHILE:官方 CLI 对内部动作编写/导入/回放一律拒绝)
const ACTIONS = ['CLICK', 'LONG_CLICK', 'INPUT', 'CLICK_AND_INPUT', 'SLEEP', 'ASSERT', 'LET'] as const
const NODE_ACTIONS = new Set(['CLICK', 'LONG_CLICK', 'INPUT', 'CLICK_AND_INPUT', 'ASSERT'])

interface Draft {
  action: string
  rid: string; nodeText: string; desc: string; xpath: string
  paramText: string; assertMode: string; assertContent: string
  allocKey: string; allocValue: string
  raw: AppCaseStep | null // 未支持动作的原步骤,保存时原样回填
}

const caseName = ref('')
const pkg = ref('')
const desc = ref('')
const steps = ref<Draft[]>([])
const busy = ref(false)

const baseCase = computed<Partial<AppCaseJson>>(() => (props.script?.case_json ?? {}))

function toDraft(st: AppCaseStep): Draft {
  const action = st.operationMethod?.actionEnum ?? ''
  const node = (st.operationNode ?? {}) as Record<string, string>
  const p = st.operationMethod?.operationParam ?? {}
  return {
    action, rid: node.resourceId ?? '', nodeText: node.text ?? '', desc: node.description ?? '',
    xpath: node.xpath ?? '', paramText: p.text ?? '', assertMode: p.assertMode ?? 'assert_contain',
    assertContent: p.assertInputContent ?? '', allocKey: p.allocKey ?? '', allocValue: p.allocValue ?? '',
    raw: ACTIONS.includes(action as (typeof ACTIONS)[number]) ? null : st,
  }
}

function emptyDraft(): Draft {
  return { action: 'CLICK', rid: '', nodeText: '', desc: '', xpath: '', paramText: '',
           assertMode: 'assert_contain', assertContent: '', allocKey: '', allocValue: '', raw: null }
}

watch(() => props.script, (s) => {
  caseName.value = s?.case_json?.caseName ?? ''
  pkg.value = s?.case_json?.targetAppPackage ?? ''
  desc.value = s?.case_json?.caseDesc ?? ''
  steps.value = (s?.case_json?.operationLog?.steps ?? []).map(toDraft)
}, { immediate: true })

function buildStep(d: Draft, i: number): AppCaseStep {
  if (d.raw) return d.raw
  const node = NODE_ACTIONS.has(d.action)
    ? { resourceId: d.rid, text: d.nodeText, description: d.desc, xpath: d.xpath, className: '', nodeBound: '' }
    : null
  let params: Record<string, string> = {}
  if (d.action === 'INPUT' || d.action === 'CLICK_AND_INPUT') params = { text: d.paramText }
  else if (d.action === 'SLEEP') params = { text: d.paramText || '1000' }
  else if (d.action === 'ASSERT') params = { assertMode: d.assertMode, assertInputContent: d.assertContent }
  else if (d.action === 'LET') params = { allocKey: d.allocKey, allocValue: d.allocValue, allocType: '1' }
  return {
    operationNode: node,
    operationMethod: { actionEnum: d.action, operationParam: params, encrypt: false, safeEncrypt: false },
    operationIndex: i, operationId: 'manual', stepId: `step-${i + 1}`,
  }
}

async function save() {
  if (!caseName.value.trim() || !pkg.value.trim() || steps.value.length === 0) {
    ElMessage.warning('用例名/包名必填,且至少一个步骤')
    return
  }
  busy.value = true
  try {
    const stepsJson = steps.value.map(buildStep)
    const unknown = steps.value.filter((d) => d.raw).length
    if (unknown) ElMessage.info(`${unknown} 个未支持动作步骤将原样保留`)
    const next: AppCaseJson = {
      ...(baseCase.value as AppCaseJson),
      caseName: caseName.value.trim(),
      targetAppPackage: pkg.value.trim(),
      caseDesc: desc.value || undefined,
      operationLog: { steps: stepsJson },
    }
    const saved = props.script
      ? await updateAppScript(props.script.id, { case: next, name: caseName.value.trim() })
      : await createAppScript(props.projectId, { case: next })
    ElMessage.success('已保存')
    emit('saved', saved)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  } finally { busy.value = false }
}

function move(i: number, delta: number) {
  const j = i + delta
  if (j < 0 || j >= steps.value.length) return
  const arr = steps.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

// 暴露给测试与父组件:brief 测试经 vm 直调/直设内部状态(script setup 默认对外封闭)
defineExpose({ caseName, pkg, steps, save })
</script>

<template>
  <el-dialog :model-value="true" :title="script ? `编辑用例:${script.name}` : '新建用例'" width="860px"
             @update:model-value="emit('close')">
    <el-form label-width="90px">
      <el-form-item label="用例名"><el-input v-model="caseName" /></el-form-item>
      <el-form-item label="被测包名"><el-input v-model="pkg" placeholder="com.example.app" /></el-form-item>
      <el-form-item label="描述"><el-input v-model="desc" /></el-form-item>
    </el-form>
    <div v-for="(s, i) in steps" :key="i" class="step-row">
      <el-select v-model="s.action" style="width: 160px" :disabled="!!s.raw">
        <el-option v-for="a in ACTIONS" :key="a" :value="a" :label="a" />
      </el-select>
      <template v-if="!s.raw">
        <template v-if="NODE_ACTIONS.has(s.action)">
          <el-input v-model="s.rid" placeholder="resourceId(可短名 btn_ok)" style="width: 200px" />
          <el-input v-model="s.nodeText" placeholder="text" style="width: 110px" />
          <el-input v-model="s.desc" placeholder="description" style="width: 110px" />
        </template>
        <el-input v-if="['INPUT', 'CLICK_AND_INPUT', 'SLEEP'].includes(s.action)"
                  v-model="s.paramText" :placeholder="s.action === 'SLEEP' ? '毫秒' : '输入文本'" style="width: 140px" />
        <template v-if="s.action === 'ASSERT'">
          <el-select v-model="s.assertMode" style="width: 140px">
            <el-option value="assert_accurate" label="完全相等" />
            <el-option value="assert_contain" label="包含" />
            <el-option value="assert_regular" label="正则" />
          </el-select>
          <el-input v-model="s.assertContent" placeholder="断言内容" style="width: 150px" />
        </template>
        <template v-if="s.action === 'LET'">
          <el-input v-model="s.allocKey" placeholder="变量名" style="width: 110px" />
          <el-input v-model="s.allocValue" placeholder="值" style="width: 140px" />
        </template>
      </template>
      <span v-else class="raw-hint">未支持动作,原样保留</span>
      <el-button link @click="move(i, -1)">↑</el-button>
      <el-button link @click="move(i, 1)">↓</el-button>
      <el-button link type="danger" @click="steps.splice(i, 1)">删</el-button>
    </div>
    <el-button style="margin-top: 8px" @click="steps.push(emptyDraft())">+ 加步骤</el-button>
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="busy" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.step-row { display: flex; gap: 6px; align-items: center; margin-top: 6px; }
.raw-hint { color: var(--el-color-warning); font-size: 12px; }
</style>

<template>
  <el-dialog
    :model-value="visible"
    title="跨端脚本编辑"
    fullscreen
    :close-on-click-modal="false"
    @close="emit('update:visible', false)"
  >
    <div class="editor">
      <!-- 脚本信息区 -->
      <section class="card">
        <div class="card-head">脚本信息</div>
        <el-form label-width="96px" class="info-form">
          <el-form-item label="脚本名">
            <el-input v-model="name" placeholder="请输入脚本名" maxlength="200" />
          </el-form-item>
          <el-form-item label="目标端">
            <el-radio-group v-model="target">
              <el-radio-button value="web">Web</el-radio-button>
              <el-radio-button value="android">Android</el-radio-button>
              <el-radio-button value="harmony">鸿蒙</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <!-- web 用 start_url;android/harmony 用 launch_target(包名 / Bundle 名) -->
          <el-form-item v-if="target === 'web'" label="起始 URL">
            <el-input v-model="startUrl" placeholder="https://example.com" />
          </el-form-item>
          <el-form-item v-else :label="target === 'android' ? '包名' : 'Bundle 名'">
            <el-input v-model="launchTarget" :placeholder="target === 'android' ? '如 com.example.app' : '如 com.example.myapp'" />
            <div class="field-tip">{{ target === 'android' ? 'Android 填应用包名,格式 com.xxx.yyy' : '鸿蒙填应用 Bundle 名' }}</div>
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="description" placeholder="选填" maxlength="500" />
          </el-form-item>
        </el-form>
      </section>

      <!-- 变量区 -->
      <section class="card">
        <div class="card-head">
          <span>变量({{ variables.length }})</span>
          <el-button size="small" @click="addVariable">添加变量</el-button>
        </div>
        <el-table :data="variables" border size="small">
          <el-table-column label="名" min-width="150">
            <template #default="{ row }">
              <el-input v-model="row.name" size="small" placeholder="变量名" maxlength="100" />
            </template>
          </el-table-column>
          <el-table-column label="默认值" min-width="180">
            <template #default="{ row }">
              <el-input v-model="row.default" size="small" placeholder="默认值" />
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="200">
            <template #default="{ row }">
              <el-input v-model="row.desc" size="small" placeholder="选填" maxlength="200" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ $index }">
              <el-button size="small" text type="danger" @click="variables.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 步骤区 -->
      <section class="card">
        <div class="card-head">
          <span>步骤({{ steps.length }})</span>
          <el-button type="primary" size="small" @click="addStep">添加步骤</el-button>
        </div>
        <el-table :data="steps" border size="small">
          <el-table-column type="index" label="#" width="52" />
          <el-table-column label="动作" width="170">
            <template #default="{ row }">
              <el-select v-model="row.action" size="small">
                <el-option v-for="a in ACTIONS" :key="a" :value="a" :label="a" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="参数" min-width="420">
            <template #default="{ row }">
              <div v-if="PARAM_FIELDS[row.action]" class="params">
                <label v-for="f in PARAM_FIELDS[row.action]" :key="f.key" class="param">
                  <span class="lbl">{{ f.label }}</span>
                  <el-select v-if="f.kind === 'direction'" v-model="row.params[f.key]" size="small">
                    <el-option v-for="d in DIRECTIONS" :key="d" :value="d" :label="d" />
                  </el-select>
                  <!-- 子脚本下拉:选项来自跨端脚本列表(排除自身);就近渲染,便于断言与嵌套弹层稳定 -->
                  <el-select
                    v-else-if="f.kind === 'script_id'"
                    v-model="row.params[f.key]"
                    size="small"
                    placeholder="选择子脚本"
                    :teleported="false"
                  >
                    <el-option v-for="s in subOptions" :key="s.id" :value="String(s.id)" :label="`${s.name}(#${s.id})`" />
                  </el-select>
                  <el-select v-else-if="f.kind === 'mode'" v-model="row.params[f.key]" size="small">
                    <el-option value="equals" label="equals" />
                    <el-option value="contains" label="contains" />
                  </el-select>
                  <el-input v-else v-model="row.params[f.key]" size="small" :placeholder="f.hint" />
                </label>
              </div>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170">
            <template #default="{ $index }">
              <el-button size="small" text :disabled="$index === 0" @click="move($index, -1)">上移</el-button>
              <el-button size="small" text :disabled="$index === steps.length - 1" @click="move($index, 1)">下移</el-button>
              <el-button size="small" text type="danger" @click="removeStep($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="steps-tip">定位类 Web 动作(click/fill 等)建议在「Web自动化」编辑器维护;跨端脚本以 ai_* 动作与 goto/fill 等参数驱动动作为主。</div>
      </section>

      <!-- 校验错误区 -->
      <section v-if="errors.length" class="card err-card">
        <div class="card-head">校验提示</div>
        <ul class="err-list">
          <li v-for="(e, i) in errors" :key="i" class="err">{{ e }}</li>
        </ul>
      </section>
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 跨端脚本编辑器(计划 10):目标端(radio)+ 启动目标 + 变量 + 步骤行编辑。
// 行模型把 params 统一存字符串便于输入;保存时按后端契约把整型参数转回 number(dsl.py 校验要求 int)。
// 前端 REQUIRED 校验只做「缺参」提示,格式类校验以后端 validate_script 为权威(400 detail 由父组件透出)。
import { computed, ref, watch } from 'vue'
import type { UiScript, UiScriptDoc, UiVariable } from '../../types'

type AiAction = 'ai_tap' | 'ai_input' | 'ai_scroll' | 'ai_wait' | 'ai_assert' | 'ai_extract' | 'run_sub'
  | 'goto' | 'click' | 'fill' | 'press' | 'select_option' | 'wait' | 'set_var' | 'scroll'
  | 'assert_visible' | 'assert_exists' | 'assert_text'

const props = defineProps<{ visible: boolean; projectId: number; script: UiScript | null; crossScripts: UiScript[] }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'save', payload: { name: string; description: string | null; script: UiScriptDoc }): void }>()

const ACTIONS = ['ai_tap', 'ai_input', 'ai_scroll', 'ai_wait', 'ai_assert', 'ai_extract', 'run_sub',
  'goto', 'click', 'fill', 'press', 'select_option', 'wait', 'set_var', 'scroll',
  'assert_visible', 'assert_exists', 'assert_text'] as const
const DIRECTIONS = ['up', 'down', 'left', 'right'] as const

const name = ref(''); const description = ref(''); const target = ref<'web' | 'android' | 'harmony'>('web')
const startUrl = ref(''); const launchTarget = ref(''); const variables = ref<UiVariable[]>([])
// 行模型:action + params 表单字段(params 里的自由键用 record 承载)
const steps = ref<{ id: string; action: AiAction; params: Record<string, string> }[]>([])

watch(() => props.visible, (v) => {
  if (!v) return
  const s = props.script
  name.value = s?.name ?? ''; description.value = s?.description ?? ''
  target.value = (s?.script.meta.target as typeof target.value) ?? 'web'
  startUrl.value = s?.script.meta.start_url ?? ''
  launchTarget.value = s?.script.meta.launch_target ?? ''
  variables.value = (s?.script.variables ?? []).map((x) => ({ ...x }))
  steps.value = (s?.script.steps ?? []).map((st) => ({
    id: st.id, action: st.action as AiAction, params: Object.fromEntries(
      Object.entries(st.params ?? {}).map(([k, val]) => [k, String(val)])),
  }))
})

function addStep() { steps.value.push({ id: `st_${Date.now()}`, action: 'ai_tap', params: {} }) }
function removeStep(i: number) { steps.value.splice(i, 1) }
function move(i: number, d: -1 | 1) {
  const j = i + d
  if (j < 0 || j >= steps.value.length) return
  ;[steps.value[i], steps.value[j]] = [steps.value[j], steps.value[i]]
}
function addVariable() { variables.value.push({ name: '', default: '', desc: '' }) }

// 每个动作的参数输入项(渲染用);必填约束见 REQUIRED
const PARAM_FIELDS: Record<string, { key: string; label: string; kind?: 'direction' | 'script_id' | 'mode'; hint?: string }[]> = {
  ai_tap: [{ key: 'target', label: '目标', hint: '自然语言描述目标元素' }],
  ai_input: [{ key: 'target', label: '目标', hint: '选填' }, { key: 'text', label: '文本' }],
  ai_scroll: [{ key: 'direction', label: '方向', kind: 'direction' }, { key: 'target', label: '目标', hint: '选填' }],
  ai_wait: [{ key: 'assertion', label: '等待条件' }, { key: 'timeout_ms', label: '超时ms' }],
  ai_assert: [{ key: 'assertion', label: '断言描述' }],
  ai_extract: [{ key: 'target', label: '目标', hint: '自然语言描述目标元素' }, { key: 'name', label: '存入变量' }],
  run_sub: [{ key: 'script_id', label: '子脚本', kind: 'script_id' }],
  goto: [{ key: 'url', label: 'URL' }],
  fill: [{ key: 'text', label: '文本' }],
  press: [{ key: 'key', label: '键名' }],
  select_option: [{ key: 'value', label: '选项值' }],
  wait: [{ key: 'ms', label: '毫秒' }],
  set_var: [{ key: 'name', label: '变量名' }, { key: 'value', label: '值' }],
  scroll: [{ key: 'dx', label: '横向Δpx' }, { key: 'dy', label: '纵向Δpx' }],
  assert_visible: [{ key: 'target', label: '目标', hint: '选填' }],
  assert_exists: [{ key: 'target', label: '目标', hint: '选填' }],
  assert_text: [{ key: 'text', label: '期望文本' }, { key: 'mode', label: '模式', kind: 'mode' }],
}
// 每个动作的必填 params(与后端 PARAM_REQUIRED 对齐;target 对 ai_input 可选)
const REQUIRED: Record<string, string[]> = {
  ai_tap: ['target'], ai_input: ['text'], ai_scroll: ['direction'], ai_wait: ['assertion'],
  ai_assert: ['assertion'], ai_extract: ['target', 'name'], run_sub: ['script_id'],
  goto: ['url'], fill: ['text'], press: ['key'], select_option: ['value'], wait: ['ms'],
  set_var: ['name', 'value'], scroll: ['dx', 'dy'], assert_text: ['text'],
}
const errors = computed(() => {
  const errs: string[] = []
  steps.value.forEach((st, i) => {
    for (const k of REQUIRED[st.action] ?? []) {
      if ((st.params[k] ?? '') === '') errs.push(`步骤${i + 1}(${st.action})缺 ${k}`)
    }
    if (st.action === 'ai_scroll' && !['up', 'down', 'left', 'right'].includes(st.params.direction ?? '')) {
      errs.push(`步骤${i + 1}: direction 必须是 up/down/left/right`)
    }
    if (st.action === 'run_sub' && String(st.params.script_id) === String(props.script?.id)) {
      errs.push(`步骤${i + 1}: 不能引用脚本自身`)
    }
  })
  return errs
})
const subOptions = computed(() => props.crossScripts.filter((s) => s.id !== props.script?.id))

// 后端对数值参数要求整型(run_sub.script_id 正整数 / wait.ms / scroll.dx,dy / ai_wait.timeout_ms),
// 行模型统一存字符串,保存时把能安全转整的键转回 number
const INT_KEYS = ['ms', 'dx', 'dy', 'timeout_ms']
function coerceParams(st: { action: string; params: Record<string, string> }): Record<string, unknown> {
  const out: Record<string, unknown> = { ...st.params }
  if (st.action === 'run_sub' && out.script_id) out.script_id = Number(out.script_id)
  for (const k of INT_KEYS) {
    const v = out[k]
    if (typeof v === 'string' && /^-?\d+$/.test(v.trim())) out[k] = Number(v.trim())
  }
  return out
}

function save() {
  if (errors.value.length || !name.value.trim()) return
  // meta 组装:start_url 仅 web 且填写时写入;launch_target(android 包名/鸿蒙 Bundle 名)填了才写
  const meta = { target: target.value } as UiScriptDoc['meta']
  if (target.value === 'web' && startUrl.value) meta.start_url = startUrl.value
  if (launchTarget.value) meta.launch_target = launchTarget.value
  emit('save', {
    name: name.value.trim(), description: description.value || null,
    script: {
      version: 2, meta, variables: variables.value,
      steps: steps.value.map((st) => ({ id: st.id, action: st.action, params: coerceParams(st) })),
    },
  })
}
defineExpose({ errors })
</script>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card {
  padding: 10px 12px 12px;
  background: var(--pro-card-bg);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-base);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.info-form {
  max-width: 640px;
}
.field-tip,
.steps-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--pro-muted);
}
.steps-tip {
  margin-top: 8px;
}
.muted {
  color: var(--pro-muted);
  font-size: 12px;
}
.params {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}
.param {
  align-items: center;
  display: flex;
  gap: 6px;
  min-width: 0;
}
.param .lbl {
  flex: none;
  min-width: 34px;
  font-size: 12px;
  color: var(--pro-muted);
}
.err-card {
  border-color: var(--el-color-danger-light-5, var(--pro-line));
}
.err-list {
  margin: 0;
  padding-left: 18px;
}
.err {
  color: var(--el-color-danger);
  font-size: 12px;
  line-height: 1.8;
}
</style>

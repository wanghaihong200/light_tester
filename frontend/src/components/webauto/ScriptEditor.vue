<template>
  <el-dialog
    :model-value="true"
    title="编辑脚本"
    fullscreen
    :close-on-click-modal="false"
    @close="emit('closed')"
  >
    <div class="editor">
      <!-- 脚本信息区 -->
      <section class="card">
        <div class="card-head">脚本信息</div>
        <el-form label-width="88px" class="info-form">
          <el-form-item label="脚本名">
            <el-input v-model="name" placeholder="请输入脚本名" maxlength="200" />
          </el-form-item>
          <el-form-item label="起始 URL">
            <el-input v-model="doc.meta.start_url" placeholder="https://example.com/login" />
          </el-form-item>
          <el-form-item label="登录态">
            <el-select v-model="authSel" placeholder="不使用">
              <el-option label="不使用" value="" />
              <el-option v-for="a in authStates" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="description" placeholder="选填" maxlength="500" />
          </el-form-item>
        </el-form>
      </section>

      <!-- 变量区 -->
      <section class="card">
        <div class="card-head">
          <span>变量({{ doc.variables.length }})</span>
          <el-button size="small" @click="addVariable">添加变量</el-button>
        </div>
        <el-table :data="doc.variables" border size="small">
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
              <el-button size="small" text type="danger" @click="removeVariable($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 步骤区 -->
      <section class="card">
        <div class="card-head">
          <span>步骤({{ doc.steps.length }})</span>
          <el-dropdown trigger="click" @command="addStep">
            <el-button type="primary" size="small">添加步骤 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="a in ACTIONS" :key="a" :command="a">{{ a }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <el-table :data="doc.steps" border size="small" class="steps-table">
          <el-table-column type="index" label="#" width="52" />
          <el-table-column label="动作" width="150">
            <template #default="{ row }">
              <el-select v-model="row.action" size="small" @change="onActionChange(row)">
                <el-option v-for="a in ACTIONS" :key="a" :value="a" :label="a" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="定位" min-width="190">
            <template #default="{ row }">
              <el-popover v-if="needsLocator(row.action)" placement="left" :width="340" trigger="click">
                <template #reference>
                  <el-button size="small" text type="primary">{{ locatorText(row.locator) }}</el-button>
                </template>
                <div v-if="row.locator" class="loc-form">
                  <div class="loc-row">
                    <span class="lbl">策略</span>
                    <el-select v-model="row.locator.strategy" size="small">
                      <el-option v-for="s in STRATEGIES" :key="s" :value="s" :label="s" />
                    </el-select>
                  </div>
                  <template v-if="row.locator.strategy === 'role'">
                    <div class="loc-row">
                      <span class="lbl">role</span>
                      <el-input v-model="row.locator.role" size="small" placeholder="如 button" />
                    </div>
                    <div class="loc-row">
                      <span class="lbl">name</span>
                      <el-input v-model="row.locator.name" size="small" placeholder="可访问名称" />
                    </div>
                  </template>
                  <div class="loc-row">
                    <span class="lbl">值</span>
                    <el-input v-model="row.locator.value" size="small" :placeholder="locatorHint(row.locator.strategy)" />
                  </div>
                </div>
              </el-popover>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="参数" min-width="280">
            <template #default="{ row }">
              <div v-if="PARAM_FIELDS[row.action]" class="params">
                <label v-for="f in PARAM_FIELDS[row.action]" :key="f.key" class="param">
                  <span class="lbl">{{ f.label }}</span>
                  <el-select v-if="f.key === 'mode'" v-model="paramsOf(row)[f.key]" size="small">
                    <el-option value="equals" label="equals" />
                    <el-option value="contains" label="contains" />
                  </el-select>
                  <el-input-number
                    v-else-if="f.type === 'number'"
                    v-model="paramsOf(row)[f.key] as number"
                    size="small"
                    :min="0"
                    :step="100"
                    controls-position="right"
                  />
                  <el-input v-else v-model="paramsOf(row)[f.key] as string" size="small" />
                </label>
              </div>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ $index }">
              <el-button size="small" text :disabled="$index === 0" @click="moveStep($index, -1)">上移</el-button>
              <el-button size="small" text :disabled="$index === doc.steps.length - 1" @click="moveStep($index, 1)">下移</el-button>
              <el-button size="small" text type="primary" @click="insertAfter($index)">插入</el-button>
              <el-button size="small" text type="danger" @click="removeStep($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <template #footer>
      <el-button @click="emit('closed')">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 步骤编辑器:打开时把 scriptRow.script 深拷贝成本地 doc,编辑全程只动本地,保存才提交。
// 结构化输入为主(action 下拉 / 定位弹层 / 按 PARAM_FIELDS 生成的参数项),不做 JSON 手写域。
// 后端 validate_script 才是权威校验,400 detail 原样透出即可。
import { ElMessage } from 'element-plus'
import { onMounted, ref, toRaw } from 'vue'
import { createUiScript, listUiAuthStates, updateUiScript } from '../../api/uiAutomation'
import type { UiAuthState, UiLocator, UiScript, UiScriptDoc, UiStep } from '../../types'

const props = defineProps<{ projectId: number; scriptRow: UiScript | null }>()
const emit = defineEmits<{ (e: 'saved'): void; (e: 'closed'): void }>()

const ACTIONS = ['goto', 'click', 'fill', 'press', 'select_option', 'wait', 'set_var', 'scroll',
  'assert_visible', 'assert_text', 'assert_exists'] as const
const STRATEGIES = ['test_id', 'role', 'placeholder', 'label', 'text', 'css'] as const
const NEED_LOCATOR = ['click', 'fill', 'press', 'select_option', 'assert_visible', 'assert_text', 'assert_exists']
// 每个 action 的必填参数键,参数编辑器按它生成输入项
const PARAM_FIELDS: Record<string, { key: string; label: string; type?: 'number' }[]> = {
  goto: [{ key: 'url', label: 'URL' }],
  fill: [{ key: 'text', label: '文本' }],
  press: [{ key: 'key', label: '键名' }],
  select_option: [{ key: 'value', label: '选项值' }],
  wait: [{ key: 'ms', label: '毫秒', type: 'number' }],
  scroll: [{ key: 'dx', label: '横向Δpx', type: 'number' }, { key: 'dy', label: '纵向Δpx', type: 'number' }],
  set_var: [{ key: 'name', label: '变量名' }, { key: 'value', label: '值' }],
  assert_text: [{ key: 'text', label: '期望文本' }, { key: 'mode', label: '模式(equals/contains)' }],
}
const LOCATOR_HINT: Record<string, string> = {
  test_id: '元素 data-testid', role: '可选,一般用 role/name', placeholder: 'placeholder 文本',
  label: 'label 文本', text: '元素文本', css: 'CSS 选择器,如 #go',
}

const name = ref(props.scriptRow?.name ?? '')
const description = ref(props.scriptRow?.description ?? '')
// props 经 reactive 代理,直接 structuredClone 会报 DataCloneError,先 toRaw 落回原始对象
const doc = ref<UiScriptDoc>(cloneDoc(props.scriptRow))
const saving = ref(false)

// 执行默认登录态:录制时写入 meta.auth_state_id,此处可变更/清除(拍板:执行不询问,编辑页为变更入口)
const authStates = ref<UiAuthState[]>([])
const authSel = ref<number | ''>(doc.value.meta?.auth_state_id ?? '')
onMounted(async () => {
  try {
    authStates.value = await listUiAuthStates(props.projectId)
  } catch {
    authStates.value = [] // 拉不到不阻塞编辑,仅无可选项
  }
  // 录制时选的登录态已被删除:回退「不使用」,保存即清除该 meta 键
  if (authSel.value !== '' && !authStates.value.some((a) => a.id === authSel.value)) {
    authSel.value = ''
  }
})

function cloneDoc(row: UiScript | null): UiScriptDoc {
  const src = row?.script ?? { version: 1, meta: { start_url: '' }, variables: [], steps: [] }
  return structuredClone(toRaw(src) as UiScriptDoc)
}

function blankStep(action: string): UiStep {
  const st: UiStep = { id: `st_${Date.now()}_${Math.floor(Math.random() * 1000)}`, action }
  if (NEED_LOCATOR.includes(action)) st.locator = { strategy: 'css', value: '' }
  const fields = PARAM_FIELDS[action]
  if (fields) st.params = Object.fromEntries(fields.map((f) => [f.key, f.type === 'number' ? 0 : '']))
  return st
}
function addStep(action: string) { doc.value.steps.push(blankStep(action)) }
function removeStep(i: number) { doc.value.steps.splice(i, 1) }
function moveStep(i: number, delta: number) {
  const j = i + delta
  if (j < 0 || j >= doc.value.steps.length) return
  const arr = doc.value.steps
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}
function insertAfter(i: number) {
  doc.value.steps.splice(i + 1, 0, blankStep('click'))
}
// 换动作:按新 action 重置 locator/params 默认结构(保留原 id,渲染稳定)
function onActionChange(row: UiStep) {
  const fresh = blankStep(row.action)
  fresh.id = row.id
  Object.assign(row, fresh)
}
// 存量数据 params 可能为 null,绑定前兜底,避免参数列渲染报错
function paramsOf(row: UiStep): Record<string, unknown> {
  if (!row.params) row.params = {}
  return row.params
}
function needsLocator(action: string) { return NEED_LOCATOR.includes(action) }

function addVariable() { doc.value.variables.push({ name: '', default: '', desc: '' }) }
function removeVariable(i: number) { doc.value.variables.splice(i, 1) }

function locatorText(loc?: UiLocator): string {
  if (!loc || !(loc.value || loc.role)) return '设置定位'
  if (loc.strategy === 'role') return `role: ${loc.role ?? ''}${loc.name ? `[name=${loc.name}]` : ''}`
  return `${loc.strategy}: ${loc.value ?? ''}`
}
function locatorHint(strategy: string) { return LOCATOR_HINT[strategy] ?? '' }

async function save() {
  if (saving.value) return
  if (!name.value.trim()) { ElMessage.warning('请填写脚本名'); return }
  saving.value = true
  try {
    // 登录态归一化:「不使用」清除 meta 键;选了则写入(后端 validate_script 对 meta 透传)
    if (doc.value.meta) {
      if (authSel.value === '') delete doc.value.meta.auth_state_id
      else doc.value.meta.auth_state_id = authSel.value
    }
    const body = {
      name: name.value.trim(),
      description: description.value.trim() || null,
      script: doc.value,
    }
    if (props.scriptRow) await updateUiScript(props.scriptRow.id, body)
    else await createUiScript(props.projectId, body)
    ElMessage.success('已保存')
    emit('saved')
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

defineExpose({ doc, addStep })
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
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.param .lbl,
.loc-row .lbl {
  flex: none;
  min-width: 34px;
  font-size: 12px;
  color: var(--pro-muted);
}
.loc-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.loc-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.loc-row .el-select,
.loc-row .el-input {
  flex: 1;
}
</style>

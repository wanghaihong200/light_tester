<script setup lang="ts">
// 计划13 T10:Mock 规则新建/编辑对话框(create/edit 双模,双 emit 照 InstanceDialog)
// 计划15 T10:规则挂组——props 改挂所属规则组,方法/路径只读展示由组决定;新建带 group_id、编辑走 Partial
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createMockRule, updateMockRule } from '../../api/mock'
import type { MockCondition, MockMatchMode, MockConditionScope, MockRule, MockRuleGroup } from '../../types'

const props = defineProps<{ group: MockRuleGroup; rule?: MockRule | null }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved', r: MockRule): void }>()

// 条件 scope 三选/match 二选
const SCOPES: { value: MockConditionScope; label: string }[] = [
  { value: 'query', label: '查询参数' },
  { value: 'header', label: '请求头' },
  { value: 'body', label: '请求体' },
]
const MATCH_MODES: MockMatchMode[] = ['eq', 'regex']

// body 作用域的 key 是 JSONPath(matching.py 按其定位 JSON 节点)——占位符按作用域区分,否则无人知道填法
function keyPlaceholder(c: MockCondition): string {
  return c.scope === 'body' ? 'JSONPath 表达式,如 $.user.id' : '参数名'
}

const enabled = ref(true)
const conditions = ref<MockCondition[]>([])
const responseStatus = ref(200)
const headersText = ref('')
const responseBody = ref('')
const enableTemplate = ref(false)
const delayMs = ref(0)
const timeoutEnabled = ref(false)
const timeoutSeconds = ref(30)
const busy = ref(false)

// headers Record ↔ textarea 双向:展示按插入序 `Key: Value` 每行一条(冒号只在首个处分隔)
function headersToText(h: Record<string, string> | undefined): string {
  return Object.entries(h ?? {}).map(([k, v]) => `${k}: ${v}`).join('\n')
}

function parseHeaders(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const t = line.trim()
    if (!t) continue
    const i = t.indexOf(':')
    if (i <= 0) continue // 无冒号/空键行跳过(轻容错,键名合法性交后端 400)
    const k = t.slice(0, i).trim()
    if (k) out[k] = t.slice(i + 1).trim()
  }
  return out
}

watch(() => props.rule, (r) => {
  enabled.value = r?.enabled ?? true
  conditions.value = (r?.conditions ?? []).map((c) => ({ ...c }))
  responseStatus.value = r?.response_status ?? 200
  headersText.value = headersToText(r?.response_headers)
  responseBody.value = r?.response_body ?? ''
  enableTemplate.value = r?.enable_template ?? false
  delayMs.value = r?.delay_ms ?? 0
  timeoutEnabled.value = r?.timeout_enabled ?? false
  timeoutSeconds.value = r?.timeout_seconds ?? 30
}, { immediate: true })

function addCondition() {
  conditions.value.push({ scope: 'query', key: '', match: 'eq', value: '' })
}
function removeCondition(i: number) {
  conditions.value.splice(i, 1)
}

async function save() {
  busy.value = true
  try {
    const body = {
      conditions: conditions.value,
      enabled: enabled.value,
      response_status: responseStatus.value,
      response_headers: parseHeaders(headersText.value),
      response_body: responseBody.value.trim() || null,
      enable_template: enableTemplate.value,
      delay_ms: delayMs.value,
      timeout_enabled: timeoutEnabled.value,
      timeout_seconds: timeoutSeconds.value,
    }
    // 新建需挂组带 group_id(instance_id 取自所属组);编辑走 Partial 不带
    const saved = props.rule
      ? await updateMockRule(props.rule.id, body)
      : await createMockRule(props.group.instance_id, { ...body, group_id: props.group.id })
    ElMessage.success('已保存')
    emit('saved', saved)
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="true" :title="rule ? '编辑规则' : '新建规则'" width="680px" @close="emit('close')">
    <el-form label-width="110px">
      <!-- 方法/路径由所属规则组决定,此处只读提示(计划15 T10) -->
      <el-form-item label="规则组">
        <span class="group-route-ro" data-test="group-route-ro">
          {{ group.method }} {{ group.path_template }}(方法与路径由所属规则组决定)
        </span>
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="enabled" />
      </el-form-item>
      <el-form-item label="匹配条件">
        <div class="conditions">
          <div v-for="(c, i) in conditions" :key="i" class="cond-row" data-test="cond-row">
            <el-select v-model="c.scope" class="cond-scope">
              <el-option v-for="s in SCOPES" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
            <el-select v-model="c.match" class="cond-match">
              <el-option v-for="m in MATCH_MODES" :key="m" :label="m" :value="m" />
            </el-select>
            <el-input v-model="c.key" :placeholder="keyPlaceholder(c)" class="cond-key" />
            <el-input v-model="c.value" placeholder="匹配值" class="cond-value" />
            <el-button link type="danger" data-test="cond-remove" @click="removeCondition(i)">删除</el-button>
          </div>
          <div>
            <el-button size="small" data-test="cond-add" @click="addCondition">+ 添加条件</el-button>
            <span class="tip">请求体的参数名填 JSONPath(如 $.data.list[0].id),eq/regex 作用于定位到的值</span>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="响应状态码">
        <el-input-number v-model="responseStatus" :min="100" :max="599" controls-position="right" class="status-input" />
      </el-form-item>
      <el-form-item label="响应头">
        <el-input
          v-model="headersText" type="textarea" :rows="3"
          placeholder="每行一条:Key: Value" data-test="headers-textarea"
        />
      </el-form-item>
      <el-form-item label="响应体">
        <el-input
          v-model="responseBody" type="textarea" :rows="4"
          placeholder="返回内容(JSON/文本);启用模板渲染后支持占位符"
        />
      </el-form-item>
      <el-form-item label="模板渲染">
        <el-switch v-model="enableTemplate" />
        <!-- 模板字面量含 {{ }},v-pre 阻止 Vue 插值,原样展示 -->
        <span v-pre class="tip">支持 {{ path.id }}、{{ jpath('$.x') }}、{{ uuid4() }}</span>
      </el-form-item>
      <el-form-item label="延迟(ms)">
        <el-input-number v-model="delayMs" :min="0" controls-position="right" class="delay-input" />
      </el-form-item>
      <el-form-item label="超时">
        <el-switch v-model="timeoutEnabled" />
        <template v-if="timeoutEnabled">
          <el-input-number v-model="timeoutSeconds" :min="1" :max="3600" controls-position="right" class="timeout-input" />
          <span class="tip">秒(1-3600)</span>
        </template>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="busy" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.group-route-ro {
  color: var(--el-text-color-primary);
  font-family: Consolas, Menlo, monospace;
  font-size: 13px;
}
.conditions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.cond-row {
  align-items: center;
  display: flex;
  gap: 6px;
}
.cond-scope {
  width: 96px;
}
.cond-match {
  width: 84px;
}
.cond-key {
  flex: 1;
}
.cond-value {
  flex: 1;
}
.tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 10px;
}
.timeout-input {
  margin-left: 10px;
  width: 120px;
}
</style>

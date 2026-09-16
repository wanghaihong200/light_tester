<!-- frontend/src/components/cicd/PlanDialog.vue -->
<template>
  <el-dialog :model-value="modelValue" :title="plan ? '编辑执行计划' : '新建执行计划'" width="720px"
             @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <el-form label-width="88px">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" maxlength="200" placeholder="如:接口冒烟回归" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="类型" required>
        <el-radio-group v-model="form.kind" :disabled="!!plan" @change="onKindChange">
          <el-radio value="ui">UI(Web自动化脚本)</el-radio>
          <el-radio value="api">接口(测试方法)</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="分支" required>
        <el-select v-model="form.branch" placeholder="先选分支" style="width: 260px">
          <el-option v-for="b in branches" :key="b" :label="b" :value="b" />
        </el-select>
        <span v-if="branchError" class="branch-error">{{ branchError }}</span>
      </el-form-item>
    </el-form>

    <div class="cases-area" :class="{ 'is-disabled': !form.branch }">
      <template v-if="form.kind === 'api'">
        <div class="cases-toolbar">
          <span>接口用例(仓是事实源,先扫描再勾选)</span>
          <el-button class="scan-btn" size="small" :disabled="!form.branch || scanning" :loading="scanning"
                     @click="doScan">扫描 {{ form.branch }}</el-button>
        </div>
        <el-table :data="apiCases" max-height="320" size="small" @selection-change="onApiSelChange">
          <el-table-column type="selection" width="40" :selectable="(_r: InterfaceCase) => true" />
          <el-table-column prop="class_name" label="测试类" min-width="220" show-overflow-tooltip />
          <el-table-column prop="method" label="方法" min-width="140" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <template v-else>
        <div class="cases-toolbar"><span>Web自动化脚本(平台库,导出后随仓执行)</span></div>
        <el-table :data="uiScripts" max-height="320" size="small" @selection-change="onUiSelChange">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="name" label="脚本" min-width="200" />
          <el-table-column prop="driver_target" label="端" width="90" />
        </el-table>
      </template>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!form.branch" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createPlan, listInterfaceCases, scanInterfaceCases, updatePlan } from '../../api/cicd'
import type { ExecutionPlan, InterfaceCase, PlanKind } from '../../api/cicd'
import { listBranches } from '../../api/repo'
import { listUiScripts } from '../../api/uiAutomation'

// driver_target 可选:api/ui-scripts 的 UiScript 类型不携带该字段(平台库行),仅测试/展示语境提供
interface UiScriptRow { id: number; name: string; driver_target?: string }
interface CaseRow { class_name: string; method: string }

const props = defineProps<{ projectId: number; plan: ExecutionPlan | null; modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'saved'): void }>()

const form = ref<{ name: string; description: string | null; kind: PlanKind; branch: string }>({
  name: props.plan?.name ?? '', description: props.plan?.description ?? null,
  kind: props.plan?.kind ?? 'ui', branch: props.plan?.branch ?? '',
})
const branches = ref<string[]>([])
const branchError = ref('')
const uiScripts = ref<UiScriptRow[]>([])
const apiCases = ref<InterfaceCase[]>([])
const scanning = ref(false)
const uiSel = ref<UiScriptRow[]>([])
const apiSel = ref<InterfaceCase[]>([])

const repoKind = computed(() => (form.value.kind === 'ui' ? 'web' : 'api') as 'web' | 'api')

async function loadBranches(): Promise<void> {
  branchError.value = ''
  branches.value = []
  try {
    branches.value = (await listBranches(props.projectId, repoKind.value)).branches
  } catch (e) {
    branchError.value = '读取分支失败:请先在「自动化工程」配置对应仓'
  }
}

function onKindChange(): void {
  form.value.branch = ''
  uiSel.value = []
  apiSel.value = []
  void loadBranches()
}

async function doScan(): Promise<void> {
  if (!form.value.branch) return
  scanning.value = true
  try {
    const stat = await scanInterfaceCases(props.projectId, form.value.branch)
    ElMessage.success(`扫描完成:新增 ${stat.added},失效 ${stat.stale},存活 ${stat.active}`)
    apiCases.value = await listInterfaceCases(props.projectId, form.value.branch)
  } finally {
    scanning.value = false
  }
}

function onUiSelChange(rows: UiScriptRow[]): void { uiSel.value = rows }
function onApiSelChange(rows: InterfaceCase[]): void { apiSel.value = rows }

// 供测试与表格编程式勾选:按 class_name+method 匹配 api 行
function toggleCase(row: CaseRow, on: boolean): void {
  const hit = apiCases.value.find((c) => c.class_name === row.class_name && c.method === row.method)
  if (hit) apiSel.value = on ? [...apiSel.value.filter((c) => c.id !== hit.id), hit] : apiSel.value.filter((c) => c.id !== hit.id)
}

async function save(): Promise<void> {
  if (!form.value.name.trim()) { ElMessage.warning('请填写计划名称'); return }
  const selection = form.value.kind === 'ui'
    ? uiSel.value.map((s) => ({ script_id: s.id, name: s.name }))
    : apiSel.value.map((c) => ({ class_name: c.class_name, method: c.method }))
  if (!selection.length) { ElMessage.warning('请至少勾选一个用例'); return }
  const payload = { name: form.value.name.trim(), description: form.value.description,
                    kind: form.value.kind, branch: form.value.branch, selection }
  if (props.plan) await updatePlan(props.plan.id, payload)
  else await createPlan(props.projectId, payload)
  ElMessage.success('已保存')
  emit('saved')
  emit('update:modelValue', false)
}

onMounted(() => {
  if (props.plan && props.plan.kind === 'ui') {
    // 编辑回填:拉脚本列表仅用于展示(勾选态由 selection 决定,此处简化为全列表)
    void listUiScripts(props.projectId).then((all) => {
      uiScripts.value = all.filter((s: UiScriptRow) => s.driver_target === 'web')
    })
  }
  void loadBranches()
})

// 分支前置(ADR-0012):分支变化(用户选择或编程式赋值)即清空已勾用例;
// api 用例按分支语境维护,ui 则拉取脚本列表并过滤 Web 端。
// 用 watch 而非 el-select @change:编程式赋值不触发 @change,watch 两者通吃。
watch(() => form.value.branch, async (branch) => {
  uiSel.value = []
  apiSel.value = []
  if (!branch) return
  if (form.value.kind === 'ui') {
    const all = await listUiScripts(props.projectId)
    uiScripts.value = all.filter((s: UiScriptRow) => s.driver_target === 'web')
  } else {
    apiCases.value = await listInterfaceCases(props.projectId, branch)
  }
})

watch(() => props.plan, (p) => { if (p) form.value.branch = p.branch })

defineExpose({ form, toggleCase, save })
</script>

<style scoped>
.cases-area.is-disabled { cursor: not-allowed; opacity: 0.45; pointer-events: none; }
.cases-toolbar { align-items: center; display: flex; justify-content: space-between; margin: 4px 0 8px; }
.branch-error { color: var(--el-color-danger); font-size: 12px; margin-left: 8px; }
</style>

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
          <el-radio value="ui">UI(Web用例)</el-radio>
          <el-radio value="api">接口(测试方法)</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="工程/分支" required>
        <div class="repo-branch-row">
          <el-select v-model="repoUrl" class="repo-select" placeholder="自动化工程"
                     :title="repoUrl ? '' : '该项目未配置此类型自动化仓'" @change="onRepoChange">
            <el-option v-for="r in kindRepos" :key="r.repo_url"
                       :label="repoDisplayName(r.repo_url)" :value="r.repo_url" />
          </el-select>
          <el-select v-model="form.branch" class="branch-select" placeholder="再选分支" :disabled="!repoUrl">
            <el-option v-for="b in branches" :key="b" :label="b" :value="b" />
          </el-select>
        </div>
        <span v-if="repoError" class="branch-error">{{ repoError }}</span>
        <span v-else-if="branchError" class="branch-error">{{ branchError }}</span>
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
        <div class="cases-toolbar">
          <span>Web用例(仓是事实源,先扫描再勾选)</span>
          <el-button class="scan-btn" size="small" :disabled="!form.branch || scanning" :loading="scanning"
                     @click="doScan">扫描 {{ form.branch }}</el-button>
        </div>
        <el-table :data="uiCases" max-height="320" size="small" @selection-change="onUiSelChange"
                  empty-text="该分支尚未扫描到用例,请点击「扫描」解析当前分支代码">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="class_name" label="文件" min-width="170" show-overflow-tooltip />
          <el-table-column prop="method" label="函数" min-width="150" show-overflow-tooltip />
          <el-table-column label="标题" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.title || row.method }}</template>
          </el-table-column>
          <el-table-column label="标记" min-width="110">
            <template #default="{ row }">
              <el-tag v-for="m in row.markers || []" :key="m" size="small" class="marker-tag">{{ m }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
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
import { createPlan, listInterfaceCases, listUiCases, scanInterfaceCases, scanUiCases, updatePlan } from '../../api/cicd'
import type { ExecutionPlan, InterfaceCase, PlanKind } from '../../api/cicd'
import { listAutomationRepos, listBranches, repoDisplayName } from '../../api/repo'

interface CaseRow { class_name: string; method: string }

const props = defineProps<{ projectId: number; plan: ExecutionPlan | null; modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'saved'): void }>()

const form = ref<{ name: string; description: string | null; kind: PlanKind; branch: string }>({
  name: props.plan?.name ?? '', description: props.plan?.description ?? null,
  kind: props.plan?.kind ?? 'ui', branch: props.plan?.branch ?? '',
})
const branches = ref<string[]>([])
const branchError = ref('')
// 自动化工程显式化:计划绑仓由 kind 推导(每项目×kind 唯一仓),此处仅展示与联动,不改变后端口径
const allRepos = ref<Awaited<ReturnType<typeof listAutomationRepos>>>([])
const repoUrl = ref('')
const repoError = ref('')
const apiCases = ref<InterfaceCase[]>([])
const uiCases = ref<InterfaceCase[]>([])
const scanning = ref(false)
const uiSel = ref<InterfaceCase[]>([])
const apiSel = ref<InterfaceCase[]>([])

const repoKind = computed(() => (form.value.kind === 'ui' ? 'web' : 'api') as 'web' | 'api')
const kindRepos = computed(() => allRepos.value.filter((r) => r.kind === repoKind.value))

async function loadRepos(): Promise<void> {
  repoError.value = ''
  try {
    allRepos.value = await listAutomationRepos(props.projectId)
  } catch (e) {
    allRepos.value = []
    repoError.value = '读取自动化工程失败'
    return
  }
  applyRepoDefaults()
  if (repoUrl.value) await loadBranches()
  else branches.value = []
}

// 唯一仓自动选中;多仓(未来放开约束)保留现选、无则清空
function applyRepoDefaults(): void {
  const list = kindRepos.value
  if (list.some((r) => r.repo_url === repoUrl.value)) return
  repoUrl.value = list.length === 1 ? list[0].repo_url : ''
  if (!list.length) repoError.value = '该项目未配置此类型自动化仓,请先在「自动化工程」配置'
}

async function loadBranches(): Promise<void> {
  branchError.value = ''
  branches.value = []
  try {
    branches.value = (await listBranches(props.projectId, repoKind.value)).branches
  } catch (e) {
    branchError.value = '读取分支失败:请先在「自动化工程」配置对应仓'
  }
}

// 换仓 → 分支语境作废,重拉分支(分支变化经既有 watch 清空已勾用例)
function onRepoChange(): void {
  form.value.branch = ''
  void loadBranches()
}

function onKindChange(): void {
  repoUrl.value = ''
  repoError.value = ''
  form.value.branch = ''
  uiSel.value = []
  apiSel.value = []
  applyRepoDefaults()
  if (repoUrl.value) void loadBranches()
  else branches.value = []
}

async function doScan(): Promise<void> {
  if (!form.value.branch) return
  scanning.value = true
  try {
    const isUi = form.value.kind === 'ui'
    const stat = await (isUi ? scanUiCases : scanInterfaceCases)(props.projectId, form.value.branch)
    ElMessage.success(`扫描完成:新增 ${stat.added},失效 ${stat.stale},存活 ${stat.active}`)
    const rows = await (isUi ? listUiCases : listInterfaceCases)(props.projectId, form.value.branch)
    if (isUi) uiCases.value = rows
    else apiCases.value = rows
  } finally {
    scanning.value = false
  }
}

function onUiSelChange(rows: InterfaceCase[]): void { uiSel.value = rows }
function onApiSelChange(rows: InterfaceCase[]): void { apiSel.value = rows }

// 供测试与表格编程式勾选:按 class_name+method 匹配 api 行
function toggleCase(row: CaseRow, on: boolean): void {
  const hit = apiCases.value.find((c) => c.class_name === row.class_name && c.method === row.method)
  if (hit) apiSel.value = on ? [...apiSel.value.filter((c) => c.id !== hit.id), hit] : apiSel.value.filter((c) => c.id !== hit.id)
}

async function save(): Promise<void> {
  if (!form.value.name.trim()) { ElMessage.warning('请填写计划名称'); return }
  const selection = form.value.kind === 'ui'
    ? uiSel.value.map((c) => ({ file_path: c.class_name, function: c.method }))
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
  void loadRepos()
})

// 分支前置(ADR-0012):分支变化(用户选择或编程式赋值)即清空已勾用例;
// api/ui 各按分支拉注册表(ADR-0013:ui 用 web 仓 pytest 用例注册表,与 api 对称,空注册表=空表格兜底)。
// 用 watch 而非 el-select @change:编程式赋值不触发 @change;immediate 覆盖编辑回填首帧
// (form.branch 初始化即带值,非 immediate 不会再触发)。
watch(() => form.value.branch, async (branch) => {
  uiSel.value = []
  apiSel.value = []
  if (!branch) return
  if (form.value.kind === 'ui') {
    uiCases.value = await listUiCases(props.projectId, branch)
  } else {
    apiCases.value = await listInterfaceCases(props.projectId, branch)
  }
}, { immediate: true })

watch(() => props.plan, (p) => { if (p) form.value.branch = p.branch })

defineExpose({ form, toggleCase, save, uiSel })
</script>

<style scoped>
.repo-branch-row { display: flex; gap: 12px; }
.repo-select, .branch-select { width: 240px; }
.cases-area.is-disabled { cursor: not-allowed; opacity: 0.45; pointer-events: none; }
.cases-toolbar { align-items: center; display: flex; justify-content: space-between; margin: 4px 0 8px; }
.branch-error { color: var(--el-color-danger); font-size: 12px; margin-left: 8px; }
.marker-tag { margin-right: 4px; }
</style>

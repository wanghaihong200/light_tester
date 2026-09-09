<script setup lang="ts">
// 计划13 T9/T10/T11:HTTP Mock 面板(左实例列表 + 右详情;规则 T10、命中记录 T11 均已填充)
// projectId 按 brief 无 prop、经 useRoute().params.id 自取;列表 5s 轮询(仅 starting/running 时)
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteMockInstance, deleteMockRule, listMockInstances, listMockRules,
  reorderMockRules, startMockInstance, stopMockInstance, updateMockRule,
} from '../../api/mock'
import type { MockInstance, MockInstanceStatus, MockRule } from '../../types'
import InstanceDialog from './InstanceDialog.vue'
import HitsPanel from './HitsPanel.vue'
import RuleDialog from './RuleDialog.vue'

defineOptions({ inheritAttrs: false })

type TagType = 'info' | 'warning' | 'success' | 'danger'
const STATUS_TAG: Record<MockInstanceStatus, TagType> = {
  stopped: 'info', starting: 'warning', running: 'success', error: 'danger',
}
const STATUS_TEXT: Record<MockInstanceStatus, string> = {
  stopped: '已停止', starting: '启动中', running: '运行中', error: '异常',
}

const route = useRoute()
const projectId = computed(() => Number(route.params.id))

const instances = ref<MockInstance[]>([])
const loading = ref(false)
const selected = ref<MockInstance | null>(null)
// 三态对齐 AppAutoPane.editing:undefined=关,null=新建,对象=编辑既有实例
const dialogInstance = ref<MockInstance | null | undefined>(undefined)

const baseUrl = (row: MockInstance) => `http://${location.hostname}:${row.port}`

async function copyUrl(row: MockInstance) {
  const url = baseUrl(row)
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success(`已复制 ${url}`)
  } catch {
    ElMessage.warning(`复制失败,请手动复制:${url}`)
  }
}

async function reload() {
  loading.value = true
  try {
    instances.value = await listMockInstances(projectId.value)
    if (disposed) return // 卸载后在途 resolve:不回贴选中、不触发轮询求值
    // 轮询刷新后按 id 回贴选中行,详情区跟随最新状态
    if (selected.value) {
      selected.value = instances.value.find((i) => i.id === selected.value!.id) ?? null
    }
    syncPolling()
  } catch (e) {
    ElMessage.error(`加载实例失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(reload)

// 5s 轮询:仅当存在 starting/running 实例时开启;全静止或卸载即清定时器。
// disposed 守卫:卸载时刻在途的 reload resolve 后不得再 setInterval(否则定时器永久泄漏)
const POLL_MS = 5000
let timer: ReturnType<typeof setInterval> | null = null
let disposed = false

function syncPolling() {
  if (disposed) return
  const active = instances.value.some((i) => i.status === 'starting' || i.status === 'running')
  if (active && timer === null) timer = setInterval(reload, POLL_MS)
  else if (!active && timer !== null) {
    clearInterval(timer)
    timer = null
  }
}
onBeforeUnmount(() => {
  disposed = true
  if (timer !== null) clearInterval(timer)
  timer = null
})

function onSelect(row: MockInstance | null) { selected.value = row }
function openCreate() { dialogInstance.value = null }
function openEdit(row: MockInstance) { dialogInstance.value = row }
function onSaved() { dialogInstance.value = undefined; reload() }

async function onStart(row: MockInstance) {
  try {
    await startMockInstance(row.id)
    await reload()
  } catch (e) {
    ElMessage.error(`启动失败:${(e as Error).message}`)
  }
}

async function onStop(row: MockInstance) {
  try {
    await stopMockInstance(row.id)
    await reload()
  } catch (e) {
    ElMessage.error(`停止失败:${(e as Error).message}`)
  }
}

async function onDelete(row: MockInstance) {
  try {
    await ElMessageBox.confirm(`删除实例「${row.name}」?规则与命中记录将一并清除。`, '删除实例', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteMockInstance(row.id)
    if (selected.value?.id === row.id) selected.value = null
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}

// el-table 作用域插槽 row 是 any,经这两个小函数收敛映射类型(any 入参合法,索引收进函数体内)
function tagTypeOf(s: MockInstanceStatus): TagType { return STATUS_TAG[s] ?? 'info' }
function statusTextOf(s: MockInstanceStatus): string { return STATUS_TEXT[s] ?? s }

// ── 规则页签(T10):随选中实例拉取;选中 id 不变时轮询刷新不重拉(避免 5s 打一次规则接口)──
const rules = ref<MockRule[]>([])
const rulesLoading = ref(false)
const dialogRule = ref<MockRule | null | undefined>(undefined) // undefined=关,null=新建,对象=编辑既有

watch(() => selected.value?.id, () => { reloadRules() })

async function reloadRules() {
  if (!selected.value) {
    rules.value = []
    return
  }
  rulesLoading.value = true
  try {
    rules.value = await listMockRules(selected.value.id)
  } catch (e) {
    ElMessage.error(`加载规则失败:${(e as Error).message}`)
  } finally {
    rulesLoading.value = false
  }
}

// 排序:交换后以新序全量提交 rule_ids,后端返回重排后的完整列表直接回贴
async function moveRule(index: number, delta: -1 | 1) {
  const target = selected.value
  const next = rules.value.slice()
  const j = index + delta
  if (!target || j < 0 || j >= next.length) return
  ;[next[index], next[j]] = [next[j], next[index]]
  try {
    rules.value = await reorderMockRules(target.id, next.map((r) => r.id))
  } catch (e) {
    ElMessage.error(`排序失败:${(e as Error).message}`)
  }
}

// 开关走受控形态:不监听 update:modelValue,等 API 成功回贴后才翻(失败自动留在原态)
async function onToggleRule(row: MockRule, val: string | number | boolean) {
  try {
    const saved = await updateMockRule(row.id, { enabled: Boolean(val) })
    const i = rules.value.findIndex((r) => r.id === row.id)
    if (i >= 0) rules.value[i] = saved
  } catch (e) {
    ElMessage.error(`更新规则失败:${(e as Error).message}`)
  }
}

async function onDeleteRule(row: MockRule) {
  try {
    await ElMessageBox.confirm(`删除规则「${row.method} ${row.path_template}」?`, '删除规则', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteMockRule(row.id)
    ElMessage.success('已删除')
    await reloadRules()
  } catch (e) {
    ElMessage.error(`删除规则失败:${(e as Error).message}`)
  }
}

function openRuleCreate() { dialogRule.value = null }
function openRuleEdit(row: MockRule) { dialogRule.value = row }
function onRuleSaved() { dialogRule.value = undefined; reloadRules() }
</script>

<template>
  <div class="mock-pane">
    <div class="layout">
      <section class="pane-left">
        <div class="toolbar">
          <span class="pane-title">Mock 实例</span>
          <el-button type="primary" size="small" @click="openCreate">新建实例</el-button>
        </div>
        <!-- row-key 必须:无 key 时 EP 的 setData 按对象引用判 currentRow 存活,reload 换新引用
             会把 currentRow 置 null 并 emit current-change(null),选中详情随 5s 轮询自毁 -->
        <el-table
          v-loading="loading" :data="instances" row-key="id" border highlight-current-row
          @current-change="onSelect"
        >
          <el-table-column prop="name" label="名称" min-width="110" />
          <el-table-column prop="port" label="端口" width="76" />
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <el-tag :type="tagTypeOf(row.status)" size="small">{{ statusTextOf(row.status) }}</el-tag>
              <div v-if="row.status === 'error' && row.error_message" class="err-msg">{{ row.error_message }}</div>
            </template>
          </el-table-column>
          <el-table-column label="base_url" min-width="180">
            <template #default="{ row }">
              <span class="base-url">{{ baseUrl(row) }}</span>
              <el-button link size="small" @click="copyUrl(row)">复制</el-button>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'running' || row.status === 'starting'"
                size="small" type="warning" @click="onStop(row)"
              >停止</el-button>
              <el-button v-else size="small" type="success" @click="onStart(row)">启动</el-button>
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="pane-right">
        <template v-if="selected">
          <div class="detail-head">
            <span class="detail-name">{{ selected.name }}</span>
            <el-tag :type="tagTypeOf(selected.status)" size="small">{{ statusTextOf(selected.status) }}</el-tag>
            <span class="detail-url">{{ baseUrl(selected) }}</span>
          </div>
          <el-tabs model-value="rules">
            <el-tab-pane label="规则" name="rules">
              <div class="rules-tab">
                <div class="rules-toolbar">
                  <span class="rules-hint">按顺序匹配,命中即返回</span>
                  <el-button type="primary" size="small" data-test="new-rule" @click="openRuleCreate">新建规则</el-button>
                </div>
                <el-table
                  v-loading="rulesLoading" :data="rules" row-key="id" border
                  data-test="rules-table" class="rules-table"
                >
                  <el-table-column label="排序" width="90" align="center">
                    <template #default="{ $index }">
                      <el-button
                        link size="small" data-test="rule-up" :disabled="$index === 0"
                        @click="moveRule($index, -1)"
                      >↑</el-button>
                      <el-button
                        link size="small" data-test="rule-down" :disabled="$index === rules.length - 1"
                        @click="moveRule($index, 1)"
                      >↓</el-button>
                    </template>
                  </el-table-column>
                  <el-table-column label="method / path" min-width="220">
                    <template #default="{ row }">
                      <span class="rule-route" data-test="rule-route">{{ row.method }} {{ row.path_template }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="条件数" width="72" align="center">
                    <template #default="{ row }">{{ row.conditions.length }}</template>
                  </el-table-column>
                  <el-table-column prop="response_status" label="状态码" width="72" align="center" />
                  <el-table-column label="启用" width="68" align="center">
                    <template #default="{ row }">
                      <el-switch :model-value="row.enabled" @change="onToggleRule(row, $event)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="延迟" width="80" align="center">
                    <template #default="{ row }">{{ row.delay_ms > 0 ? `${row.delay_ms}ms` : '-' }}</template>
                  </el-table-column>
                  <el-table-column label="超时" width="72" align="center">
                    <template #default="{ row }">
                      <el-tag v-if="row.timeout_enabled" type="warning" size="small">{{ row.timeout_seconds }}s</el-tag>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="120">
                    <template #default="{ row }">
                      <el-button link size="small" @click="openRuleEdit(row)">编辑</el-button>
                      <el-button link size="small" type="danger" @click="onDeleteRule(row)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-empty v-if="!rulesLoading && rules.length === 0" description="暂无规则,点击右上角新建" />
              </div>
            </el-tab-pane>
            <el-tab-pane label="命中记录" name="hits">
              <HitsPanel :instance-id="selected.id" />
            </el-tab-pane>
          </el-tabs>
        </template>
        <el-empty v-else description="选择左侧实例查看规则与命中" />
      </section>
    </div>

    <InstanceDialog
      v-if="dialogInstance !== undefined" :instance="dialogInstance"
      @close="dialogInstance = undefined" @saved="onSaved"
    />
    <RuleDialog
      v-if="dialogRule !== undefined" :instance-id="selected?.id ?? 0" :rule="dialogRule"
      @close="dialogRule = undefined" @saved="onRuleSaved"
    />
  </div>
</template>

<style scoped>
.mock-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.layout {
  display: flex;
  flex: 1;
  gap: 16px;
  min-height: 0;
}
.pane-left {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.toolbar {
  align-items: center;
  display: flex;
  gap: 8px;
}
.pane-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.pane-title + .el-button {
  margin-left: auto;
}
.err-msg {
  color: var(--el-color-danger);
  font-size: 12px;
  line-height: 1.4;
  margin-top: 4px;
  word-break: break-all;
}
.base-url {
  color: var(--el-text-color-regular);
  font-size: 12px;
  margin-right: 6px;
  word-break: break-all;
}
.pane-right {
  border-left: 1px solid var(--el-border-color);
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  padding-left: 16px;
}
.detail-head {
  align-items: center;
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.detail-name {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.detail-url {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.tab-slot {
  min-height: 120px;
}
.rules-tab {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rules-toolbar {
  align-items: center;
  display: flex;
  gap: 8px;
}
.rules-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-right: auto;
}
.rule-route {
  font-family: var(--el-font-family-mono, ui-monospace, Consolas, monospace);
  font-size: 12px;
  word-break: break-all;
}
</style>

<script setup lang="ts">
// 计划15 T10:规则与命中记录页——组卡片列表(组间/组内两级排序)+ 组管理 + 组内规则表
// instanceId 自路由取参;头部返回实例列表;组卡片默认全展开
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteMockRule, deleteMockRuleGroup, getMockInstance, listMockRuleGroups,
  reorderMockGroupRules, reorderMockGroups, updateMockRule, updateMockRuleGroup,
} from '../../api/mock'
import type { MockInstance, MockRule, MockRuleGroup } from '../../types'
import GroupDialog from './GroupDialog.vue'
import RuleDialog from './RuleDialog.vue'

const route = useRoute()
const router = useRouter()
const instanceId = computed(() => Number(route.params.instanceId))
const projectId = computed(() => Number(route.params.id))

const instance = ref<MockInstance | null>(null)
const groups = ref<MockRuleGroup[]>([])
const expanded = ref<number[]>([]) // el-collapse v-model:load 后置全组 id,默认全展开

// 三态对齐 MockPane.dialogInstance:undefined=关,null=新建,对象=编辑既有
const dialogGroup = ref<MockRuleGroup | null | undefined>(undefined)
const dialogRule = ref<MockRule | null | undefined>(undefined)
const dialogRuleGroup = ref<MockRuleGroup | null>(null) // 新建/编辑规则的所属组(RuleDialog 只读展示)

const baseUrl = computed(() =>
  instance.value ? `http://${location.hostname}:${instance.value.port}` : '')

onMounted(async () => {
  try {
    instance.value = await getMockInstance(instanceId.value)
    await reload()
  } catch (e) {
    ElMessage.error(`加载规则组失败:${(e as Error).message}`)
  }
})

async function reload() {
  groups.value = await listMockRuleGroups(instanceId.value)
  expanded.value = groups.value.map((g) => g.id)
}

// ── 组级操作 ──
// 排序:交换后以新序全量提交 group_ids,后端返回重排后的完整列表直接回贴
async function moveGroup(index: number, delta: -1 | 1) {
  const next = groups.value.slice()
  const j = index + delta
  if (j < 0 || j >= next.length) return
  ;[next[index], next[j]] = [next[j], next[index]]
  try {
    groups.value = await reorderMockGroups(instanceId.value, next.map((g) => g.id))
  } catch (e) {
    ElMessage.error(`排序失败:${(e as Error).message}`)
  }
}

// 开关受控:不 v-model,API 成功回贴才翻面(失败自动留在原态)
async function onToggleGroup(g: MockRuleGroup, val: string | number | boolean) {
  try {
    const saved = await updateMockRuleGroup(g.id, { enabled: Boolean(val) })
    groups.value = groups.value.map((x) => (x.id === g.id ? { ...saved, rules: g.rules } : x))
  } catch (e) {
    ElMessage.error(`更新规则组失败:${(e as Error).message}`)
  }
}

async function onDeleteGroup(g: MockRuleGroup) {
  try {
    await ElMessageBox.confirm(
      `删除规则组「${g.method} ${g.path_template}」?组内 ${g.rules.length} 条规则将一并删除。`,
      '删除规则组', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await deleteMockRuleGroup(g.id)
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error(`删除规则组失败:${(e as Error).message}`)
  }
}

// 折叠/展开只由组头「倒三角」控制(2026-09-13 验收反馈):标题内容区 @click.stop 拦掉
// el-collapse 的整行点击切换,这里手工增删 expanded 里的组 id
function isOpen(g: MockRuleGroup) { return expanded.value.includes(g.id) }
function toggleExpand(g: MockRuleGroup) {
  expanded.value = isOpen(g)
    ? expanded.value.filter((id) => id !== g.id)
    : [...expanded.value, g.id]
}

// ── 组内规则操作 ──
async function moveRule(g: MockRuleGroup, index: number, delta: -1 | 1) {
  const next = g.rules.slice()
  const j = index + delta
  if (j < 0 || j >= next.length) return
  ;[next[index], next[j]] = [next[j], next[index]]
  try {
    await reorderMockGroupRules(g.id, next.map((r) => r.id))
    await reload()
  } catch (e) {
    ElMessage.error(`排序失败:${(e as Error).message}`)
  }
}

// 同 MockPane 旧实现:开关受控,成功后回贴该行
async function onToggleRule(g: MockRuleGroup, row: MockRule, val: string | number | boolean) {
  try {
    const saved = await updateMockRule(row.id, { enabled: Boolean(val) })
    const gi = groups.value.findIndex((x) => x.id === g.id)
    if (gi >= 0) {
      const ri = groups.value[gi]!.rules.findIndex((r) => r.id === row.id)
      if (ri >= 0) groups.value[gi]!.rules[ri] = saved
    }
  } catch (e) {
    ElMessage.error(`更新规则失败:${(e as Error).message}`)
  }
}

async function onDeleteRule(g: MockRuleGroup, row: MockRule) {
  try {
    await ElMessageBox.confirm(
      `删除「${g.method} ${g.path_template}」组内的规则(条件 ${row.conditions.length} 条 → 响应 ${row.response_status})?`,
      '删除规则', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await deleteMockRule(row.id)
    ElMessage.success('已删除')
    await reload() // 空组保留:只删规则,组卡片仍在
  } catch (e) {
    ElMessage.error(`删除规则失败:${(e as Error).message}`)
  }
}

// ── 对话框与跳转 ──
function openGroupCreate() { dialogGroup.value = null }
function openGroupEdit(g: MockRuleGroup) { dialogGroup.value = g }
function openRuleCreate(g: MockRuleGroup) { dialogRuleGroup.value = g; dialogRule.value = null }
function openRuleEdit(g: MockRuleGroup, row: MockRule) { dialogRuleGroup.value = g; dialogRule.value = row }
function openHits(g: MockRuleGroup) {
  // 命名路由须带链上全部参数:/projects/:id 是父级,缺 id 抛 Missing required param「id」
  router.push({ name: 'project-mock-http-hits', params: { id: projectId.value }, query: { group: String(g.id) } })
}
// 保存成功回调:关框后刷新;刷新失败不静默(对齐本组件其余调用点的错误透出,计划15 T11 顺手项)
async function onGroupSaved() {
  dialogGroup.value = undefined
  try {
    await reload()
  } catch (e) {
    ElMessage.error(`刷新规则组失败:${(e as Error).message}`)
  }
}

async function onRuleSaved() {
  dialogRule.value = undefined
  try {
    await reload()
  } catch (e) {
    ElMessage.error(`刷新规则组失败:${(e as Error).message}`)
  }
}
</script>

<template>
  <div class="rgp">
    <div class="rgp-head">
      <el-button link @click="router.push({ name: 'project-mock-http', params: { id: projectId } })">← 返回实例列表</el-button>
      <span class="rgp-title">{{ instance?.name }} · 规则与命中记录</span>
      <el-tag v-if="instance" size="small" class="rgp-url">{{ baseUrl }}</el-tag>
      <el-button type="primary" size="small" data-test="new-group" class="rgp-new" @click="openGroupCreate">
        新建规则组
      </el-button>
    </div>

    <!-- 组卡片:头部单行=倒三角(独占折叠控制)+组路由 mono+透传标记+组启停+描述+工具区;
         标题内容区 @click.stop 拦掉 el-collapse 整行点击,折叠只听倒三角的(2026-09-13 验收反馈) -->
    <el-collapse v-model="expanded" class="rgp-groups">
      <el-collapse-item v-for="(g, gi) in groups" :key="g.id" :name="g.id" :data-test="`group-card-${g.id}`">
        <template #title>
          <div class="g-head" @click.stop>
            <button class="g-arrow" data-test="group-toggle" :title="isOpen(g) ? '收起' : '展开'"
              @click="toggleExpand(g)">{{ isOpen(g) ? '▾' : '▸' }}</button>
            <span class="g-route" data-test="group-route">{{ g.method }} {{ g.path_template }}</span>
            <el-tag v-if="g.passthrough_enabled" size="small" type="warning" class="g-pt">透传</el-tag>
            <el-switch
              :model-value="g.enabled" class="g-switch" :data-test="`group-switch-${g.id}`"
              @change="onToggleGroup(g, $event)"
            />
            <span v-if="g.description" class="g-desc" data-test="group-desc">{{ g.description }}</span>
            <span class="g-tools">
              <el-button link size="small" data-test="group-hits" @click="openHits(g)">命中记录详情</el-button>
              <el-button link size="small" @click="openGroupEdit(g)">编辑组</el-button>
              <el-button link size="small" :disabled="gi === 0" @click="moveGroup(gi, -1)">↑</el-button>
              <el-button link size="small" :disabled="gi === groups.length - 1" @click="moveGroup(gi, 1)">↓</el-button>
              <el-button link size="small" type="danger" @click="onDeleteGroup(g)">删除组</el-button>
              <el-button link size="small" type="primary" @click="openRuleCreate(g)">新建规则</el-button>
            </span>
          </div>
        </template>
        <!-- 组内规则表:method/path 由组决定,列只余 排序/条件数/状态码/启用/延迟/超时/操作 -->
        <el-table :data="g.rules" row-key="id" border size="small" class="g-rules" :data-test="`rules-of-${g.id}`">
          <el-table-column label="排序" width="90" align="center">
            <template #default="{ $index }">
              <el-button link size="small" data-test="rule-up" :disabled="$index === 0" @click="moveRule(g, $index, -1)">↑</el-button>
              <el-button link size="small" data-test="rule-down" :disabled="$index === g.rules.length - 1" @click="moveRule(g, $index, 1)">↓</el-button>
            </template>
          </el-table-column>
          <el-table-column label="条件数" width="76" align="center">
            <template #default="{ row }">{{ row.conditions.length }}</template>
          </el-table-column>
          <el-table-column prop="response_status" label="状态码" width="72" align="center" />
          <el-table-column label="启用" width="68" align="center">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" @change="onToggleRule(g, row, $event)" />
            </template>
          </el-table-column>
          <el-table-column label="延迟" width="84" align="center">
            <template #default="{ row }">{{ row.delay_ms > 0 ? `${row.delay_ms}ms` : '-' }}</template>
          </el-table-column>
          <el-table-column label="超时" width="72" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.timeout_enabled" type="warning" size="small">{{ row.timeout_seconds }}s</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="110">
            <template #default="{ row }">
              <el-button link size="small" @click="openRuleEdit(g, row)">编辑</el-button>
              <el-button link size="small" type="danger" @click="onDeleteRule(g, row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="g.rules.length === 0" description="组内暂无规则,可新建规则或删除本组" :image-size="48" />
      </el-collapse-item>
    </el-collapse>
    <el-empty v-if="groups.length === 0" description="暂无规则组,点击右上角新建" />

    <GroupDialog
      v-if="dialogGroup !== undefined" :instance-id="instanceId" :group="dialogGroup"
      @close="dialogGroup = undefined" @saved="onGroupSaved"
    />
    <RuleDialog
      v-if="dialogRule !== undefined" :group="dialogRuleGroup!" :rule="dialogRule"
      @close="dialogRule = undefined" @saved="onRuleSaved"
    />
  </div>
</template>

<style scoped>
.rgp {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
}
.rgp-head {
  align-items: center;
  display: flex;
  gap: 10px;
}
.rgp-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.rgp-url {
  word-break: break-all;
}
.rgp-new {
  margin-left: auto;
}
/* EP 自带的整行点击切换+右侧箭头关闭:折叠只由组头左侧倒三角控制(2026-09-13 验收反馈) */
.rgp-groups :deep(.el-collapse-item__arrow) {
  display: none;
}
/* 组头单行:倒三角+路由+透传标记+启停+描述+工具区,整行不换行(2026-09-13 验收反馈) */
.g-head {
  align-items: center;
  display: flex;
  min-width: 0;
  width: 100%;
}
/* 倒三角是折叠/展开的唯一入口;按钮化以获得清晰的可点击感 */
.g-arrow {
  background: none;
  border: none;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  flex: none;
  font-size: 13px;
  padding: 0 8px 0 0;
}
.g-arrow:hover {
  color: var(--el-color-primary);
}
/* 组路由用等宽字体,与后端模板路由直观对应 */
.g-route {
  color: var(--el-text-color-primary);
  flex: none;
  font-family: Consolas, Menlo, monospace;
  font-size: 13px;
}
.g-pt {
  flex: none;
  margin-left: 8px;
}
/* 启停开关与组路由之间拉开一档距离 */
.g-switch {
  flex: none;
  margin-left: 20px;
}
.g-desc {
  color: var(--el-text-color-secondary);
  flex: none;
  font-size: 12px;
  margin-left: 12px;
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.g-tools {
  align-items: center;
  display: flex;
  margin-left: auto;
  white-space: nowrap;
}
</style>

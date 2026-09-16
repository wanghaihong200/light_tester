<template>
  <div class="plans-pane">
    <div class="toolbar">
      <h2>执行计划</h2>
      <div class="actions">
        <el-button class="trigger-btn" type="primary" :disabled="!selected.length" @click="showTrigger = true">
          执行所选({{ selected.length }})
        </el-button>
        <el-button type="primary" plain @click="editing = null; showPlan = true">新建计划</el-button>
      </div>
    </div>
    <el-table :data="plans" row-key="id" @selection-change="(rows: ExecutionPlan[]) => (selected = rows)">
      <el-table-column type="selection" width="44" />
      <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.kind === 'ui' ? 'primary' : 'success'">
            {{ row.kind === 'ui' ? 'UI' : '接口' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="branch" label="分支" width="160" show-overflow-tooltip />
      <el-table-column label="用例数" width="90">
        <template #default="{ row }">{{ row.selection.length }}</template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="180" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button link type="primary" @click="editing = row; showPlan = true">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <PlanDialog v-if="showPlan" v-model="showPlan" :project-id="projectId" :plan="editing" @saved="load" />
    <TriggerDialog v-if="showTrigger" v-model="showTrigger" :project-id="projectId"
                   :plan-ids="selected.map((r) => r.id)" @triggered="onTriggered" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deletePlan, listPlans } from '../../api/cicd'
import type { ExecutionPlan } from '../../api/cicd'
import PlanDialog from './PlanDialog.vue'
import TriggerDialog from './TriggerDialog.vue'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'triggered'): void }>()

const plans = ref<ExecutionPlan[]>([])
const selected = ref<ExecutionPlan[]>([])
const showPlan = ref(false)
const showTrigger = ref(false)
const editing = ref<ExecutionPlan | null>(null)

async function load(): Promise<void> {
  plans.value = await listPlans(props.projectId)
}

async function remove(row: ExecutionPlan): Promise<void> {
  await ElMessageBox.confirm(`删除执行计划「${row.name}」?历史执行记录不受影响。`, '删除', { type: 'warning' })
  await deletePlan(row.id)
  ElMessage.success('已删除')
  await load()
}

function onTriggered(): void {
  selected.value = []
  emit('triggered')
}

onMounted(load)
</script>

<style scoped>
.plans-pane { padding: 16px 20px; }
.toolbar { align-items: center; display: flex; justify-content: space-between; margin-bottom: 12px; }
.toolbar h2 { font-size: 18px; margin: 0; }
.actions { display: flex; gap: 8px; }
</style>

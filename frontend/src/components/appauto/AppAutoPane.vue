<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteAppScript, listAppRuns, listAppScripts,
} from '../../api/appAutomation'
import type { AppRun, AppScript } from '../../types'
import AppScriptEditor from './AppScriptEditor.vue'
import ImportDialog from './ImportDialog.vue'
// 执行/批量/详情/对比由 Task 16 接入本 Pane

const props = defineProps<{ projectId: number }>()

const scripts = ref<AppScript[]>([])
const runs = ref<AppRun[]>([])
const importVisible = ref(false)
// undefined=关闭;null=新建;对象=编辑既有用例
const editing = ref<AppScript | null | undefined>(undefined)

async function loadAll() {
  scripts.value = await listAppScripts(props.projectId)
  runs.value = await listAppRuns(props.projectId, {})
}

onMounted(loadAll)

// 删除目标在弹确认框前置位,使 doDelete 成为 onDelete(确认框)与测试直调共用的删除入口,
// 二者共用 deleteAppScript(brief 实现注意②;brief 原稿 doDelete 空函数体无法满足其自身测试断言)
let deleteTarget: AppScript | null = null

async function doDelete() {
  if (!deleteTarget) return
  try {
    await deleteAppScript(deleteTarget.id)
    ElMessage.success('已删除')
    await loadAll()
  } finally {
    deleteTarget = null
  }
}

async function onDelete(s: AppScript) {
  deleteTarget = s
  try {
    await ElMessageBox.confirm(`删除脚本「${s.name}」?执行历史将保留。`, '删除', { type: 'warning' })
  } catch {
    deleteTarget = null // 用户取消(或确认框被环境拒绝)不删
    return
  }
  await doDelete()
}

defineExpose({ onDelete, doDelete })

const STATUS_TEXT: Record<string, string> = {
  pending: '排队', running: '执行中', passed: '通过', failed: '失败', cancelled: '已取消',
}
</script>

<template>
  <div class="app-auto-pane">
    <div class="toolbar">
      <el-button type="primary" @click="importVisible = true">导入用例</el-button>
      <el-button @click="editing = null">新建空白用例</el-button>
    </div>

    <el-table :data="scripts">
      <el-table-column prop="name" label="脚本" />
      <el-table-column prop="app_package" label="被测应用" />
      <el-table-column label="步骤数">
        <template #default="{ row }">{{ row.case_json?.operationLog?.steps?.length ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button link type="primary" @click="editing = row">编辑</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <h4>执行历史</h4>
    <el-table :data="runs">
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column prop="script_name" label="脚本" />
      <el-table-column prop="device_serial" label="设备" />
      <el-table-column label="平台状态">
        <template #default="{ row }">{{ STATUS_TEXT[row.status] ?? row.status }}</template>
      </el-table-column>
      <el-table-column prop="run_state" label="端上终态" />
    </el-table>

    <ImportDialog v-model:visible="importVisible" :project-id="projectId" @imported="loadAll" />
    <AppScriptEditor v-if="editing !== undefined" :project-id="projectId" :script="editing"
                     @close="editing = undefined" @saved="(() => { editing = undefined; loadAll() })" />
  </div>
</template>

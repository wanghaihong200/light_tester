<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteAppScript, exportAppScript, listAppRuns, listAppScripts,
} from '../../api/appAutomation'
import type { AppRun, AppScript } from '../../types'
import AppRunDialog from './AppRunDialog.vue'
import AppScriptEditor from './AppScriptEditor.vue'
import ComparisonDialog from './ComparisonDialog.vue'
import ImportDialog from './ImportDialog.vue'
import RunDetailDrawer from './RunDetailDrawer.vue'

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

// 执行/批量目标(null=弹窗关);runFor=详情抽屉的 run;batchFor=对比矩阵的批量号
const runTarget = ref<{ script: AppScript; multi: boolean } | null>(null)
const runFor = ref<AppRun | null>(null)
const batchFor = ref<string | null>(null)
function openRun(s: AppScript, multi: boolean) { runTarget.value = { script: s, multi } }

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

// 导出 Appium pytest 产物并推送到项目 APP 自动化仓(终审 I3):prompt 输入分支名(默认 main),
// commit message 走后端默认;成功提示列文件清单(对齐计划 11 导出惯例)。
// 400 detail 形态:字符串(无仓) / {errors:[…]}(拒导清单) / {error:…}(NothingToCommit),
// client.ts 把 dict detail 退化成 '[object Object]' 话术,须从 e.body?.detail 还原结构再展示。
function extractExportErrors(e: unknown): string[] {
  const err = e as { body?: { detail?: unknown }; message?: string } | null
  const detail = err?.body?.detail
  if (detail && typeof detail === 'object' && Array.isArray((detail as { errors?: unknown }).errors)) {
    return (detail as { errors: unknown[] }).errors.map(String)
  }
  if (detail && typeof detail === 'object' && (detail as { error?: unknown }).error) {
    return [String((detail as { error: unknown }).error)]
  }
  if (typeof detail === 'string' && detail) return [detail]
  if (err?.message && err.message !== '[object Object]') return [err.message]
  return ['导出失败,请检查用例内容或查看后端日志']
}

async function onExport(s: AppScript) {
  let branch = 'main'
  try {
    const { value } = await ElMessageBox.prompt(
      '将用例翻译为 Appium pytest 并推送到项目的 APP 自动化仓,输入目标分支:',
      `导出「${s.name}」`, { inputValue: 'main', inputPattern: /\S+/, inputErrorMessage: '分支名不能为空' })
    branch = (value || '').trim() || 'main'
  } catch {
    return // 用户取消
  }
  try {
    const r = await exportAppScript(s.id, { branch })
    const list = (r.files ?? []).join('、')
    ElMessage.success({ message: `已推送 ${r.branch}@${r.commit_short}${list ? ` · ${list}` : ''}`, duration: 6000 })
  } catch (e) {
    const errs = extractExportErrors(e)
    if (errs.length > 1) ElMessageBox.alert(errs.map((x) => `· ${x}`).join('\n'), '存在不可导出的步骤')
    else ElMessage.error(errs[0])
  }
}

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
          <el-button link type="primary" @click="openRun(row, false)">执行</el-button>
          <el-button link type="primary" @click="openRun(row, true)">批量</el-button>
          <el-button link type="primary" @click="editing = row">编辑</el-button>
          <el-button link type="success" plain @click="onExport(row)">导出</el-button>
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
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button link type="primary" @click="runFor = row">详情</el-button>
          <el-button v-if="row.batch_id" link type="primary" @click="batchFor = row.batch_id">对比</el-button>
        </template>
      </el-table-column>
    </el-table>

    <ImportDialog v-model:visible="importVisible" :project-id="projectId" @imported="loadAll" />
    <AppScriptEditor v-if="editing !== undefined" :project-id="projectId" :script="editing"
                     @close="editing = undefined" @saved="(() => { editing = undefined; loadAll() })" />
    <AppRunDialog v-if="runTarget" :project-id="projectId" :scripts="[runTarget.script]"
                  :multi="runTarget.multi" :visible="!!runTarget"
                  @update:visible="!$event && (runTarget = null)" @started="loadAll" />
    <RunDetailDrawer :visible="!!runFor" :run="runFor"
                     @update:visible="!$event && (runFor = null)" @changed="loadAll" />
    <ComparisonDialog v-if="batchFor" :project-id="projectId" :batch-id="batchFor" @close="batchFor = null" />
  </div>
</template>

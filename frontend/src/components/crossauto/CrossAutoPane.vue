<template>
  <div class="cross-auto">
    <div class="toolbar">
      <el-radio-group v-model="target">
        <el-radio-button value="web">Web</el-radio-button>
        <el-radio-button value="android">Android</el-radio-button>
        <el-radio-button value="harmony">鸿蒙</el-radio-button>
      </el-radio-group>
      <el-button type="primary" class="new-btn" @click="openCreate">新建脚本</el-button>
    </div>

    <el-table v-loading="loading" :data="scripts" size="small" border>
      <el-table-column prop="name" label="脚本" min-width="160" />
      <el-table-column label="步骤数" width="90">
        <template #default="{ row }">{{ row.script?.steps?.length ?? 0 }}</template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="180" />
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="success" @click="openRun(row)">运行</el-button>
          <el-popconfirm title="确认删除该脚本?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <AppSnapshotsPane v-if="target === 'android'" :project-id="props.projectId" />

    <h4 class="runs-title">执行历史</h4>
    <el-table :data="runs" size="small" border>
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column prop="script_name" label="脚本" min-width="140" />
      <el-table-column prop="status" label="状态" width="100" />
      <el-table-column label="通过/总步" width="100">
        <template #default="{ row }">{{ row.steps_passed }}/{{ row.steps_total }}</template>
      </el-table-column>
      <el-table-column prop="started_at" label="开始时间" min-width="170" />
    </el-table>

    <CrossScriptEditor
      v-model:visible="editorVisible"
      :project-id="props.projectId"
      :script="editing"
      :cross-scripts="scripts"
      @save="onSave"
    />
    <CrossRunDialog v-model:visible="runVisible" :project-id="props.projectId" :script="running" />
  </div>
</template>

<script setup lang="ts">
// 多端 UI 自动化面板(计划 10):三端 radio 切换,按端过滤脚本与执行历史;
// Android 端额外渲染应用快照管理;脚本编辑/运行弹层复用 uiAutomation 的 CRUD 与 SSE。
import { ElMessage } from 'element-plus'
import { onMounted, ref, watch } from 'vue'
import type { UiRun, UiScript } from '../../types'
import { createUiScript, deleteUiScript, updateUiScript } from '../../api/uiAutomation'
import { listCrossScripts, listRunsByTarget } from '../../api/crossAutomation'
import CrossScriptEditor from './CrossScriptEditor.vue'
import CrossRunDialog from './CrossRunDialog.vue'
import AppSnapshotsPane from './AppSnapshotsPane.vue'

const props = defineProps<{ projectId: number }>()
const target = ref<'web' | 'android' | 'harmony'>('web')
const scripts = ref<UiScript[]>([])
const runs = ref<UiRun[]>([])
const loading = ref(false)
const editing = ref<UiScript | null>(null)
const running = ref<UiScript | null>(null)
const editorVisible = ref(false)
const runVisible = ref(false)

async function reload() {
  loading.value = true
  try {
    const all = await listCrossScripts(props.projectId)
    scripts.value = all.filter((s) => (s.script.meta.target ?? 'web') === target.value)
    runs.value = await listRunsByTarget(props.projectId, target.value)
  } catch (e) {
    ElMessage.error(`加载多端脚本失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(reload)
watch(target, reload)

function openCreate() { editing.value = null; editorVisible.value = true }
function openEdit(s: UiScript) { editing.value = s; editorVisible.value = true }
function openRun(s: UiScript) { running.value = s; runVisible.value = true }
async function remove(s: UiScript) {
  try {
    await deleteUiScript(s.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
  await reload()
}
async function onSave(payload: { name: string; description: string | null; script: UiScript['script'] }) {
  try {
    if (editing.value) await updateUiScript(editing.value.id, payload)
    else await createUiScript(props.projectId, payload)
    ElMessage.success('已保存')
  } catch (e) {
    // 后端 validate_script 的 400 detail 原样透出,编辑框保持打开可改
    ElMessage.error(`保存失败:${(e as Error).message}`)
    return
  }
  await onSaved()
}
async function onSaved() { editorVisible.value = false; await reload() }
</script>

<style scoped>
.cross-auto {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 4px 0;
}
.toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.new-btn {
  margin-left: auto;
}
.runs-title {
  color: var(--el-text-color-primary);
  font-size: 13px;
  margin: 6px 0 0;
}
</style>

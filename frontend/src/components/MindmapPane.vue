<template>
  <div class="mindmap-pane">
    <div class="toolbar">
      <el-button type="primary" @click="openAdd('module', selected ?? { nodeType: 'root' })">+ 模块</el-button>
      <el-button @click="load" :loading="loading">刷新</el-button>
      <el-button @click="exportXmind">导出 .xmind</el-button>
      <el-button @click="exportExcel">导出 Excel</el-button>
      <span class="hint">选中节点后在侧边编辑;空项目请先建根模块</span>
    </div>
    <div class="canvas-area">
      <MindmapEditor :data="mindmapData" @node-active="onNodeActive" />
    </div>
    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="360px" :close-on-click-modal="true" @closed="selected = null">
      <div v-if="selected && canAdd.length" class="add-actions">
        <el-button v-if="canAdd.includes('module')" size="small" @click="openAdd('module')">+ 子模块</el-button>
        <el-button v-if="canAdd.includes('feature')" size="small" @click="openAdd('feature')">+ 功能点</el-button>
        <el-button v-if="canAdd.includes('case')" size="small" @click="openAdd('case')">+ 用例</el-button>
        <el-divider style="margin: 8px 0" />
      </div>
      <ModuleForm
        v-if="selected?.nodeType === 'module'"
        :key="selected.refId"
        :project-id="projectId"
        :module-id="selected.refId!"
        :initial-name="selectedMeta.name"
        :initial-parent-id="selectedMeta.parentId"
        @saved="onSaved"
        @deleted="onDeleted"
      />
      <FeaturePointForm
        v-else-if="selected?.nodeType === 'feature'"
        :key="selected.refId"
        :feature-point-id="selected.refId!"
        :initial-name="selectedMeta.name"
        @saved="onSaved"
        @deleted="onDeleted"
      />
      <CaseForm
        v-else-if="selected?.nodeType === 'case'"
        :key="selected.refId"
        :case-id="selected.refId!"
        @saved="onSaved"
        @deleted="onDeleted"
      />
    </el-drawer>
    <el-dialog v-model="addVisible" :title="addTitle" width="440px" @closed="resetAddForm">
      <template v-if="addType === 'case'">
        <el-form label-width="64px">
          <el-form-item label="标题" required>
            <el-input v-model="addForm.title" maxlength="500" placeholder="用例标题" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-radio-group v-model="addForm.priority">
              <el-radio-button value="P0">P0</el-radio-button>
              <el-radio-button value="P1">P1</el-radio-button>
              <el-radio-button value="P2">P2</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <el-alert type="info" :closable="false" title="创建后请点选该用例补充步骤等字段" />
      </template>
      <el-input v-else v-model="addForm.name" maxlength="200" :placeholder="addType === 'module' ? '模块名称' : '功能点名称'" />
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="submitAdd">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { canAddChild, findNodeMeta, toMindmapData, type MindmapNode, type NodeType } from '../adapters/tree'
import { createCase } from '../api/cases'
import { downloadFile } from '../api/client'
import { createFeaturePoint, createModule, fetchTree } from '../api/tree'
import type { Priority } from '../types'
import MindmapEditor from './MindmapEditor.vue'
import ModuleForm from './ModuleForm.vue'
import FeaturePointForm from './FeaturePointForm.vue'
import CaseForm from './CaseForm.vue'

const props = defineProps<{ projectId: number; projectName: string }>()

const mindmapData = ref<MindmapNode | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const modules = await fetchTree(props.projectId)
    mindmapData.value = toMindmapData(props.projectName, modules)
  } catch (e) {
    ElMessage.error(`加载用例树失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const selected = ref<{ nodeType: NodeType; refId?: number } | null>(null)
const selectedMeta = ref<{ name: string; parentId: number | null }>({ name: '', parentId: null })
const drawerVisible = ref(false)

const drawerTitle = computed(() =>
  selected.value?.nodeType === 'module' ? '编辑模块' : selected.value?.nodeType === 'feature' ? '编辑功能点' : selected.value?.nodeType === 'case' ? '编辑用例' : '编辑',
)

function onNodeActive(payload: { nodeType: NodeType; refId?: number }) {
  if (payload.nodeType === 'root') return
  selected.value = payload
  // 从当前树数据里找到该节点名称与父模块(只用于表单初值)
  const found = findNodeMeta(mindmapData.value, payload.refId!)
  selectedMeta.value = found
  drawerVisible.value = true
}


function onSaved() {
  void load() // 保存后整树刷新,选中高亮丢失属 MVP 已接受行为
}
function onDeleted() {
  drawerVisible.value = false
  void load()
}

const addVisible = ref(false)
const adding = ref(false)
const addType = ref<'module' | 'feature' | 'case'>('module')
const addForm = ref<{ name: string; title: string; priority: Priority }>({ name: '', title: '', priority: 'P1' })
// 新增目标:显式传入(工具栏)或取当前选中(抽屉内按钮);与 selected 解耦,抽屉关闭后仍可从工具栏建根模块
const addTarget = ref<{ nodeType: NodeType; refId?: number } | null>(null)

const canAdd = computed(() => (selected.value ? canAddChild(selected.value.nodeType) : []))

const addTitle = computed(
  () => ({ module: '新增模块', feature: '新增功能点', case: '新增用例' })[addType.value],
)

function openAdd(type: 'module' | 'feature' | 'case', target?: { nodeType: NodeType; refId?: number }) {
  addTarget.value = target ?? selected.value
  if (!addTarget.value) {
    ElMessage.warning('请先选中一个节点')
    return
  }
  addType.value = type
  addVisible.value = true
}

function resetAddForm() {
  addForm.value = { name: '', title: '', priority: 'P1' }
}

async function submitAdd() {
  const sel = addTarget.value
  if (!sel) return
  adding.value = true
  try {
    if (addType.value === 'case') {
      if (!addForm.value.title.trim()) {
        ElMessage.warning('用例标题不能为空')
        return
      }
      await createCase(sel.refId!, { title: addForm.value.title.trim(), priority: addForm.value.priority, steps: [] })
    } else if (addType.value === 'feature') {
      if (!addForm.value.name.trim()) {
        ElMessage.warning('功能点名称不能为空')
        return
      }
      await createFeaturePoint(sel.refId!, addForm.value.name.trim())
    } else {
      if (!addForm.value.name.trim()) {
        ElMessage.warning('模块名称不能为空')
        return
      }
      // 目标为 root → 顶层模块;为 module → 其子模块
      await createModule(props.projectId, { name: addForm.value.name.trim(), parentId: sel.nodeType === 'module' ? sel.refId : null })
    }
    addVisible.value = false
    ElMessage.success('已创建')
    await load()
  } catch (e) {
    ElMessage.error(`创建失败:${(e as Error).message}`)
  } finally {
    adding.value = false
  }
}

// 后端 401 门禁后 window.open 直链带不了 Authorization:经 http 客户端 fetch→blob 触发下载(文件名取响应头 filename*)
async function exportXmind() {
  try {
    await downloadFile(`/projects/${props.projectId}/export/xmind`, `${props.projectId}.xmind`)
  } catch (e) {
    ElMessage.error(`导出失败:${(e as Error).message}`)
  }
}

async function exportExcel() {
  try {
    await downloadFile(`/projects/${props.projectId}/export/excel`, `${props.projectId}.xlsx`)
  } catch (e) {
    ElMessage.error(`导出失败:${(e as Error).message}`)
  }
}
</script>

<style scoped>
.mindmap-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.toolbar {
  padding-bottom: 8px;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.canvas-area {
  flex: 1;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
}
</style>

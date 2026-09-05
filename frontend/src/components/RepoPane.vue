<template>
  <div class="repo-pane">
    <div v-if="!project.git_repo_url" class="hint">请先在项目列表编辑 git_repo_url</div>
    <template v-else>
      <div class="topbar">
        <el-select
          v-model="currentBranch"
          class="branch-select"
          filterable
          placeholder="分支"
          size="default"
          :loading="syncing"
          @change="onBranchChange"
        >
          <el-option v-for="b in branches" :key="b" :label="b" :value="b" />
          <template #empty>同步后可选分支</template>
        </el-select>
        <el-button :loading="syncing" @click="doSync()">同步工程</el-button>
        <span v-if="syncResult" class="sync-info">{{ syncResult.cloned ? '已克隆' : '已更新' }} · {{ syncResult.branch }}@{{ syncResult.commit_short }}</span>
      </div>
      <div class="body">
        <div class="tree">
          <div v-if="treeData.length" class="tree-tools">
            <el-button size="small" text type="primary" @click="setExpandAll(true)">全部展开</el-button>
            <el-button size="small" text type="primary" @click="setExpandAll(false)">全部收起</el-button>
          </div>
          <el-tree
            v-if="treeData.length"
            ref="treeRef"
            :data="treeData"
            :props="{ label: 'name', children: 'children' }"
            node-key="path"
            @node-click="onNodeClick"
          >
            <template #default="{ data }">
              <span :class="isChangedUnder(data) ? 'node-changed' : 'node-clean'" :title="data.path">{{ data.name }}</span>
            </template>
          </el-tree>
          <div v-else class="placeholder">点击「同步工程」拉取仓库</div>
        </div>
        <div class="editor">
          <div class="file-path">{{ currentPath || '(选择文件)' }}</div>
          <div ref="editorRef" class="monaco-host" />
        </div>
      </div>
      <div class="footer">
        <el-button @click="pushVisible = true">变更文件 {{ changeCount }}</el-button>
      </div>
      <PushDialog v-model:visible="pushVisible" :project-id="projectId" :changes="changes" @pushed="onPushed" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { listBranches, listChanges, listFiles, readFile, syncRepo } from '../api/repo'
import type { ChangeFile, FileNode, Project } from '../types'
import PushDialog from './PushDialog.vue'

const props = defineProps<{ projectId: number; project: Project }>()
const syncing = ref(false)
const syncResult = ref<{ cloned: boolean; updated: boolean; branch: string; commit_short: string } | null>(null)
const tree = ref<FileNode | { needs_sync: true } | null>(null)
const currentPath = ref('')
const editorRef = ref<HTMLElement | null>(null)
const pushVisible = ref(false)
const changeCount = ref(0)
const changes = ref<ChangeFile[]>([])
const branches = ref<string[]>([])
const currentBranch = ref('')
const treeRef = ref<any>(null)
let editor: any = null
let monacoMod: any = null

const treeData = computed(() => (tree.value && 'children' in tree.value ? [tree.value] : []))
const changedPaths = computed(() => new Set(changes.value.map((c) => c.path)))

async function loadFiles() {
  tree.value = await listFiles(props.projectId)
}
async function loadChanges() {
  const r = await listChanges(props.projectId)
  changes.value = r.files
  changeCount.value = r.files.filter((f) => f.status !== 'deleted').length
}
async function loadBranches() {
  try {
    branches.value = (await listBranches(props.projectId)).branches
  } catch {
    branches.value = [] // 未同步时后端 409,静默
  }
}

async function doSync(branch?: string) {
  syncing.value = true
  try {
    syncResult.value = await syncRepo(props.projectId, branch)
    currentBranch.value = syncResult.value.branch
    ElMessage.success(`${syncResult.value.cloned ? '已克隆' : '已更新'} · ${syncResult.value.branch}`)
    await loadFiles()
    await loadChanges()
    await loadBranches()
  } catch (e) {
    ElMessage.error(`同步失败:${(e as Error).message}`)
  } finally {
    syncing.value = false
  }
}
function onBranchChange(b: string) {
  doSync(b)
}

/** 节点颜色:文件按 path 精确匹配变更集合;目录看子树是否含变更(根=仓库级,path='.' 归一为空)。 */
function isChangedUnder(node: FileNode): boolean {
  if (!node.is_dir) return changedPaths.value.has(node.path)
  const base = node.path === '.' ? '' : node.path
  const prefix = base ? base + '/' : ''
  for (const p of changedPaths.value) {
    if (p.startsWith(prefix)) return true
  }
  return false
}

function setExpandAll(open: boolean) {
  const store = treeRef.value?.store
  if (!store) return
  for (const key of Object.keys(store.nodesMap || {})) {
    store.nodesMap[key].expanded = open
  }
}

async function onNodeClick(node: FileNode) {
  if (node.is_dir) return
  currentPath.value = node.path
  const r = await readFile(props.projectId, node.path)
  if (!monacoMod) monacoMod = await import('monaco-editor')
  if (!editor) {
    editor = monacoMod.editor.create(editorRef.value!, { readOnly: true, automaticLayout: true })
  }
  const lang = r.language === 'plaintext' ? 'plaintext' : r.language
  monacoMod.editor.setModelLanguage(editor.getModel()!, lang)
  editor.setValue(r.content)
}
function onPushed() {
  pushVisible.value = false
  loadChanges()
  loadFiles()
}
onMounted(() => { loadFiles(); loadChanges(); loadBranches() })
onBeforeUnmount(() => { editor?.dispose() })
watch(() => props.projectId, () => { loadFiles(); loadChanges(); loadBranches() })
</script>

<style scoped>
.repo-pane { display: flex; flex-direction: column; height: 100%; }
.hint { padding: 16px; color: #909399; }
.topbar { padding: 8px 0; display: flex; align-items: center; gap: 12px; }
.branch-select { width: 160px; }
.sync-info { color: #67c23a; }
.body { flex: 1; display: flex; gap: 8px; min-height: 0; }
.tree { width: 260px; overflow: auto; border-right: 1px solid #ebeef5; padding: 4px; }
.tree-tools { display: flex; gap: 4px; padding: 2px 0 6px; border-bottom: 1px dashed #ebeef5; margin-bottom: 4px; }
.node-changed { color: #f56c6c; font-weight: 600; }
.node-clean { color: #67c23a; }
.editor { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.file-path { padding: 4px 8px; background: #f5f7fa; font-size: 12px; color: #606266; }
.monaco-host { flex: 1; }
.placeholder { color: #c0c4cc; padding: 12px; }
.footer { padding: 8px 0; border-top: 1px solid #ebeef5; }
</style>

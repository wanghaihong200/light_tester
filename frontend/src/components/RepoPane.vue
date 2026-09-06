<template>
  <div class="repo-pane">
    <div v-if="!project.git_repo_url" class="hint">请先在项目列表编辑 git_repo_url</div>
    <template v-else>
      <div class="repobar">
        <el-radio-group v-model="kind" size="small">
          <el-radio-button value="api">接口工程</el-radio-button>
          <el-radio-button value="web">Web工程</el-radio-button>
          <el-radio-button value="app" disabled>APP工程<span class="app-sub">计划 12 提供</span></el-radio-button>
        </el-radio-group>
        <el-form class="repo-form" inline @submit.prevent>
          <el-form-item label="仓地址">
            <el-input v-model="cfgUrl" class="cfg-input" placeholder="http(s)://…/repo.git" />
          </el-form-item>
          <el-form-item label="令牌">
            <el-input
              v-model="cfgToken"
              class="cfg-input"
              type="password"
              show-password
              placeholder="留空则清除已存令牌"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="saveConfig">保存仓配置</el-button>
          </el-form-item>
        </el-form>
        <span v-if="!repoOf(kind)" class="cfg-hint">未配置,保存后可用</span>
      </div>
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
          <div v-else-if="needsConfig" class="placeholder cfg-empty">该分类仓未配置,请先保存仓配置</div>
          <div v-else class="placeholder">点击「同步工程」拉取仓库</div>
        </div>
        <div class="editor">
          <div class="file-path">{{ currentPath || '(选择文件)' }}</div>
          <div ref="editorRef" class="monaco-host" />
        </div>
      </div>
      <div class="footer">
        <el-button v-if="kind === 'api'" @click="pushVisible = true">变更文件 {{ changeCount }}</el-button>
        <span v-else class="footer-hint">Web 仓推送请走 Web 自动化页的「导出」流程</span>
      </div>
      <PushDialog v-model:visible="pushVisible" :project-id="projectId" :changes="changes" @pushed="onPushed" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { listAutomationRepos, listBranches, listChanges, listFiles, putAutomationRepo, readFile, syncRepo } from '../api/repo'
import type { AutomationRepoRow, RepoKind } from '../api/repo'
import type { ChangeFile, FileNode, Project } from '../types'
import PushDialog from './PushDialog.vue'

const props = defineProps<{ projectId: number; project: Project }>()

// ── plan11:接口/Web 双仓。所有 repo 调用都携带当前 kind;kind='api' 时行为与改造前一致 ──
const kind = ref<RepoKind>('api')
const repos = ref<AutomationRepoRow[]>([])
const cfgUrl = ref('')
const cfgToken = ref('')
const saving = ref(false)

const syncing = ref(false)
const syncResult = ref<{ cloned: boolean; updated: boolean; branch: string; commit_short: string } | null>(null)
const tree = ref<FileNode | { needs_sync: true } | { needs_config: true } | null>(null)
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
const needsConfig = computed(() => !!tree.value && 'needs_config' in tree.value)
const changedPaths = computed(() => new Set(changes.value.map((c) => c.path)))

function repoOf(k: RepoKind) {
  return repos.value.find((r) => r.kind === k)
}

async function loadConfig() {
  try {
    repos.value = (await listAutomationRepos(props.projectId)) ?? []
  } catch {
    repos.value = [] // 配置读取失败不阻塞浏览,表单按未配置处理
  }
  syncCfgForm()
}

/** 表单回显当前 kind 的仓地址;令牌不回显(避免明文驻留),留空提交即清除 */
function syncCfgForm() {
  cfgUrl.value = repoOf(kind.value)?.repo_url ?? ''
  cfgToken.value = ''
}

let loadSeq = 0
async function loadTree() {
  const seq = ++loadSeq
  try {
    const r = await listFiles(props.projectId, kind.value)
    if (seq === loadSeq) tree.value = r // 丢弃过期 kind 的慢响应,防串仓回写
  } catch {
    if (seq === loadSeq) tree.value = null
  }
}
async function loadChanges() {
  try {
    const r = await listChanges(props.projectId, kind.value)
    changes.value = r.files
    changeCount.value = r.files.filter((f) => f.status !== 'deleted').length
  } catch {
    changes.value = [] // 该分类仓未配置/未同步时后端报错,静默为无变更
  }
}
async function loadBranches() {
  try {
    branches.value = (await listBranches(props.projectId, kind.value)).branches
  } catch {
    branches.value = [] // 未同步时后端 409,静默
  }
}

async function saveConfig() {
  const url = cfgUrl.value.trim()
  if (!url) {
    ElMessage.warning('请填写仓地址')
    return
  }
  saving.value = true
  try {
    await putAutomationRepo(props.projectId, kind.value, { repo_url: url, repo_token: cfgToken.value || null })
    ElMessage.success('仓配置已保存')
    await loadConfig()
    await Promise.all([loadTree(), loadChanges(), loadBranches()])
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

async function doSync(branch?: string) {
  syncing.value = true
  try {
    syncResult.value = await syncRepo(props.projectId, branch, kind.value)
    currentBranch.value = syncResult.value.branch
    ElMessage.success(`${syncResult.value.cloned ? '已克隆' : '已更新'} · ${syncResult.value.branch}`)
    await loadTree()
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

watch(kind, () => {
  // 切换分类:清空上一仓的浏览状态,再按新 kind 重拉
  tree.value = null
  currentPath.value = ''
  currentBranch.value = ''
  branches.value = []
  changes.value = []
  changeCount.value = 0
  syncResult.value = null
  syncCfgForm()
  loadTree()
  loadChanges()
  loadBranches()
})

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
  const r = await readFile(props.projectId, node.path, kind.value)
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
  loadTree()
}
onMounted(() => { loadConfig(); loadTree(); loadChanges(); loadBranches() })
onBeforeUnmount(() => { editor?.dispose() })
watch(() => props.projectId, () => { loadConfig(); loadTree(); loadChanges(); loadBranches() })
</script>

<style scoped>
.repo-pane { display: flex; flex-direction: column; height: 100%; }
.hint { padding: 16px; color: #909399; }
.repobar { padding: 8px 0; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.app-sub { font-size: 12px; color: #c0c4cc; margin-left: 4px; }
.repo-form { display: flex; align-items: center; gap: 8px; }
.repo-form :deep(.el-form-item) { margin: 0; }
.cfg-input { width: 260px; }
.cfg-hint { color: #e6a23c; font-size: 12px; }
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
.cfg-empty { color: #e6a23c; }
.footer { padding: 8px 0; border-top: 1px solid #ebeef5; }
.footer-hint { color: #909399; font-size: 12px; }
</style>

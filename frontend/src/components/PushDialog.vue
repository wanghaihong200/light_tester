<template>
  <el-dialog :model-value="visible" @update:model-value="$emit('update:visible', $event)" title="推送变更到分支" width="560px">
    <el-form label-width="100px">
      <el-form-item label="变更文件">
        <el-checkbox-group v-model="selected">
          <div v-for="f in changes" :key="f.path" :class="{ disabled: f.status === 'deleted' }">
            <el-checkbox :label="f.path" :disabled="f.status === 'deleted'">
              {{ f.path }} <el-tag size="small" :type="f.status === 'added' ? 'success' : 'warning'">{{ statusText(f.status) }}</el-tag>
            </el-checkbox>
          </div>
        </el-checkbox-group>
        <div v-if="!changes.length" class="empty">无变更</div>
      </el-form-item>
      <el-form-item label="目标分支">
        <el-select v-model="branch" filterable allow-create placeholder="选择或输入分支名">
          <el-option v-for="b in branches" :key="b" :label="b" :value="b" />
        </el-select>
      </el-form-item>
      <el-form-item label="commit 信息">
        <el-input v-model="commitMessage" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="pushing" :disabled="!canPush" @click="onPush">推送</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { listBranches, pushFiles } from '../api/repo'
import type { RepoKind } from '../api/repo'
import type { ChangeFile } from '../types'

// plan12 补遗:kind 缺省 'api' 保持既有调用方零破坏(api 仓直推行为不变)
const props = withDefaults(
  defineProps<{ visible: boolean; projectId: number; changes: ChangeFile[]; kind?: RepoKind }>(),
  { kind: 'api' },
)
const emit = defineEmits<{ 'update:visible': [boolean]; pushed: [] }>()

const branches = ref<string[]>([])
const selected = ref<string[]>([])
const pushing = ref(false)

// 分支记忆按 kind 隔离;api 读新 key 未命中时回退读改造前旧 key(只读迁移,不回写旧 key)
function branchStorageKey(): string {
  return `push_branch_${props.projectId}_${props.kind}`
}
function readRememberedBranch(): string {
  return (
    localStorage.getItem(branchStorageKey())
    || (props.kind === 'api' ? localStorage.getItem(`push_branch_${props.projectId}`) : null)
    || 'dev'
  )
}
const branch = ref(readRememberedBranch())
// PushDialog 在 RepoPane 内常挂载,kind 切换不重建实例,需重读记忆
watch(() => props.kind, () => { branch.value = readRememberedBranch(); commitMessage.value = defaultCommitMessage() })

function defaultCommitMessage() {
  return `${props.kind === 'api' ? 'AI 生成接口测试' : '自动化测试推送'} ${new Date().toISOString().slice(0, 16).replace('T', ' ')}`
}
const commitMessage = ref(defaultCommitMessage())

const canPush = computed(() => selected.value.length > 0 && branch.value.trim())
watch(() => props.visible, async (v) => {
  if (v) {
    try { branches.value = (await listBranches(props.projectId, props.kind)).branches } catch {}
    selected.value = props.changes.filter((f) => f.status !== 'deleted').map((f) => f.path)
  }
}, { immediate: true })
function statusText(s: string) { return s === 'added' ? '新增' : s === 'modified' ? '修改' : '删除' }
async function onPush() {
  pushing.value = true
  try {
    const r = await pushFiles(props.projectId, selected.value, branch.value.trim(), commitMessage.value, props.kind)
    localStorage.setItem(branchStorageKey(), branch.value.trim())
    ElMessage.success(`已推送到 ${r.branch}@${r.commit_short}`)
    emit('pushed')
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'object' ? detail?.error : detail
    ElMessage.error(`推送失败:${msg || (e as Error).message}`)
  } finally {
    pushing.value = false
  }
}
</script>

<style scoped>
.disabled { opacity: 0.5; }
.empty { color: #c0c4cc; }
</style>

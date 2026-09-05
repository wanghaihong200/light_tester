<template>
  <el-dialog
    :model-value="true"
    title="登录态管理"
    width="720"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <div class="auth">
      <div class="collect-bar">
        <el-input
          v-model="newName"
          class="name-input"
          placeholder="登录态名称,如:管理员"
          maxlength="200"
          :disabled="collectingId != null"
          @keyup.enter="onCollect"
        />
        <el-button
          v-if="collectingId == null"
          type="primary"
          :loading="collecting"
          @click="onCollect"
        >采集新登录态</el-button>
        <template v-else>
          <el-button type="success" :loading="saving" @click="onSave">保存登录态</el-button>
          <el-button @click="onCancel">取消采集</el-button>
        </template>
      </div>
      <div v-if="collectingId != null" class="collect-tip">
        在弹出的浏览器里完成登录后回来点保存
      </div>

      <el-table v-loading="loading" :data="states" border class="auth-table">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="200" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
// 登录态管理:采集状态机挂在 collectingId 上(= 后端 collect 会话 id)。
// 采集中的浏览器会话是后端交互槽位资源,对话框关闭若仍在采集必须 cancel,防泄漏;
// save 的 409(会话已结束)/ 404(会话不存在)都意味着本次采集作废,复位按钮并提示重新采集。
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { ApiError } from '../../api/client'
import {
  cancelAuthCollect, collectAuthState, deleteUiAuthState, listUiAuthStates, saveAuthState,
} from '../../api/uiAutomation'
import type { UiAuthState } from '../../types'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'closed'): void }>()

const states = ref<UiAuthState[]>([])
const loading = ref(false)
const newName = ref('')
const collectingId = ref<number | null>(null)
const collecting = ref(false)
const saving = ref(false)

async function reload() {
  loading.value = true
  try {
    states.value = await listUiAuthStates(props.projectId)
  } catch (e) {
    ElMessage.error(`加载登录态失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(reload)

async function onCollect() {
  if (collecting.value || collectingId.value != null) return
  const name = newName.value.trim()
  if (!name) { ElMessage.warning('请输入登录态名称'); return }
  collecting.value = true
  try {
    const { collect_id } = await collectAuthState(props.projectId, name)
    collectingId.value = collect_id
  } catch (e) {
    ElMessage.error(`发起采集失败:${(e as Error).message}`)
  } finally {
    collecting.value = false
  }
}

async function onSave() {
  if (saving.value || collectingId.value == null) return
  saving.value = true
  try {
    const row = await saveAuthState(collectingId.value)
    collectingId.value = null
    newName.value = ''
    ElMessage.success(`登录态「${row.name}」已保存`)
    await reload()
  } catch (e) {
    // 只有会话确已不在(409 已结束 / 404 不存在)才丢弃 cid 复位;
    // 其余错误(500/网络)后端槽位与浏览器窗口还占着,保留 cid 让用户可重试保存或取消采集
    const status = e instanceof ApiError ? e.status : 0
    if (status === 409 || status === 404) collectingId.value = null
    const msg = status === 409 ? '采集会话已结束,请重新采集'
      : status === 404 ? '采集会话不存在,请重新采集'
      : `保存登录态失败:${(e as Error).message}`
    ElMessage.error(msg)
  } finally {
    saving.value = false
  }
}

async function onCancel() {
  const cid = collectingId.value
  if (cid == null) return
  collectingId.value = null
  await cancelAuthCollect(cid).catch(() => {}) // 会话可能已被后端回收,失败不提示
}

async function onDelete(row: UiAuthState) {
  try {
    await ElMessageBox.confirm(`确认删除登录态「${row.name}」?已保存的登录状态文件会一并清除。`, '删除登录态', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteUiAuthState(row.id)
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}

async function onClose() {
  const cid = collectingId.value
  collectingId.value = null
  if (cid != null) await cancelAuthCollect(cid).catch(() => {})
  emit('closed')
}

function formatTime(iso: string): string {
  return iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '-'
}
</script>

<style scoped>
.auth {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.collect-bar {
  display: flex;
  gap: 8px;
}
.name-input {
  max-width: 320px;
}
.collect-tip {
  padding: 6px 10px;
  font-size: 13px;
  color: var(--el-color-primary);
  background: var(--el-fill-color-light);
  border-radius: var(--border-radius-base);
}
</style>

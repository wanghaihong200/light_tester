<template>
  <section class="snap-pane">
    <div class="pane-head">
      <span>应用数据快照(Android)</span>
      <span class="head-tip">快照保存应用的登录态,执行 Android 脚本时自动恢复</span>
    </div>

    <div class="collect-bar">
      <el-input
        v-model="name"
        class="name-input"
        placeholder="快照名称,如:首页已登录"
        maxlength="200"
        :disabled="collecting"
        @keyup.enter="onCollect"
      />
      <el-input
        v-model="appPackage"
        class="pkg-input"
        placeholder="应用包名,如 com.example.app"
        maxlength="200"
        :disabled="collecting"
        @keyup.enter="onCollect"
      />
      <el-button type="primary" :loading="collecting" @click="onCollect">采集快照</el-button>
    </div>

    <el-table v-loading="loading" :data="states" border size="small">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="包名" min-width="170">
        <template #default="{ row }">
          <span v-if="row.app_package">{{ row.app_package }}</span>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="采集时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
// Android 应用数据快照管理(计划 10):采集走 adb(后端拉取当前应用数据并落盘),
// 409 表示 adb 不可用/无设备,detail 由 http 层抽出后用 ElMessage 原样透出。
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { collectAndroidSnapshot, listAuthStates } from '../../api/crossAutomation'
import { deleteUiAuthState } from '../../api/uiAutomation'
import type { UiAuthState } from '../../types'

const props = defineProps<{ projectId: number }>()

const states = ref<UiAuthState[]>([])
const loading = ref(false)
const name = ref('')
const appPackage = ref('')
const collecting = ref(false)

async function reload() {
  loading.value = true
  try {
    states.value = await listAuthStates(props.projectId, 'android_snapshot')
  } catch (e) {
    ElMessage.error(`加载快照失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(reload)

async function onCollect() {
  if (collecting.value) return
  const n = name.value.trim()
  const pkg = appPackage.value.trim()
  if (!n) { ElMessage.warning('请输入快照名称'); return }
  if (!pkg) { ElMessage.warning('请输入应用包名,如 com.xxx.yyy'); return }
  collecting.value = true
  try {
    await collectAndroidSnapshot(props.projectId, { name: n, app_package: pkg })
    ElMessage.success('快照已采集')
    name.value = ''; appPackage.value = ''
    await reload()
  } catch (e) {
    // 409(adb 不可用/无设备)等错误的 detail 已在 http 层拼进 message,原样透出
    ElMessage.error(`采集失败:${(e as Error).message}`)
  } finally {
    collecting.value = false
  }
}

async function onDelete(row: UiAuthState) {
  try {
    await ElMessageBox.confirm(`确认删除快照「${row.name}」?已保存的应用数据文件会一并清除。`, '删除快照', {
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

function formatTime(iso: string): string {
  return iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '-'
}
</script>

<style scoped>
.snap-pane {
  background: var(--pro-card-bg);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-base);
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px 12px;
}
.pane-head {
  align-items: baseline;
  display: flex;
  font-size: 13px;
  font-weight: 600;
  gap: 10px;
}
.head-tip {
  font-size: 12px;
  font-weight: 400;
  color: var(--pro-muted);
}
.collect-bar {
  display: flex;
  gap: 8px;
}
.name-input {
  max-width: 220px;
}
.pkg-input {
  max-width: 260px;
}
.muted {
  color: var(--pro-muted);
  font-size: 12px;
}
</style>

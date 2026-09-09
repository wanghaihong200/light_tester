<script setup lang="ts">
// 计划13 T11:命中记录面板(过滤 + 3s 轮询 + 详情抽屉 + 清空)
// 轮询/列表失败静默(后台刷新不弹全局错防噪音);用户动作(详情/清空)失败仍提示
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { clearMockHits, getMockHit, listMockHits } from '../../api/mock'
import type { MockHitsFilter } from '../../api/mock'
import type { MockHit, MockHitDetail } from '../../types'

const props = defineProps<{ instanceId: number }>()

const POLL_MS = 3000
const FILTERS: { value: MockHitsFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'matched', label: '命中' },
  { value: 'unmatched', label: '未命中' },
]

const hits = ref<MockHit[]>([])
const loading = ref(true)
const filter = ref<MockHitsFilter>('all')

// 定时器生命周期:unmount / instanceId 变化 / filter 变化三处都经 stopPolling 清旧
let timer: ReturnType<typeof setInterval> | null = null
let disposed = false // 卸载守卫:在途 loadHits resolve 后不得复活定时器(T9 同款教训)

async function loadHits() {
  loading.value = true
  try {
    hits.value = await listMockHits(props.instanceId, filter.value)
  } catch {
    // 静默:轮询/列表失败不弹全局错,保留旧列表待下次轮询
  } finally {
    loading.value = false
  }
}

// 重拉并按新参重建定时器:先清旧再拉,成功落地后重启轮询
async function reload() {
  stopPolling()
  await loadHits()
  startPolling()
}

function startPolling() {
  // timer 判空:两次 reload 快速连续时,先 resolve 的一方不得顶掉后建定时器造成双轮询
  if (!disposed && timer === null) timer = setInterval(loadHits, POLL_MS)
}

function stopPolling() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(async () => {
  await loadHits()
  startPolling()
})

watch(() => props.instanceId, reload)
watch(filter, reload)

onBeforeUnmount(() => {
  disposed = true
  stopPolling()
})

// ── 行点击 → 详情抽屉 ──
const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<MockHitDetail | null>(null)
const headerRows = computed(() =>
  Object.entries(detail.value?.request_headers ?? {}).map(([k, v]) => ({ key: k, value: v })),
)

async function openDetail(row: MockHit) {
  drawerVisible.value = true
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await getMockHit(row.id)
  } catch (e) {
    ElMessage.error(`加载命中详情失败:${(e as Error).message}`)
    drawerVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

// ── 清空:confirm → clearMockHits → 重拉 ──
async function onClear() {
  try {
    await ElMessageBox.confirm(
      `清空实例 #${props.instanceId} 的全部命中记录?`, '清空命中记录',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await clearMockHits(props.instanceId)
    ElMessage.success('已清空')
    await reload()
  } catch (e) {
    ElMessage.error(`清空失败:${(e as Error).message}`)
  }
}

// 时间列:手工 padStart 拼 YYYY-MM-DD HH:mm:ss(不用 toLocaleString,格式跨环境稳定)
function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function fullPath(row: MockHit): string {
  return row.query ? `${row.path}?${row.query}` : row.path
}

// 命中 tag 文案:绿「命中→状态码」/ 红「未命中→状态码」(后端超时挂住时状态码可能为 null)
function hitTagText(row: MockHit): string {
  return `${row.matched ? '命中' : '未命中'}→${row.response_status ?? '-'}`
}
</script>

<template>
  <div class="hits-panel">
    <div class="hits-toolbar">
      <el-radio-group v-model="filter" size="small">
        <el-radio v-for="f in FILTERS" :key="f.value" :value="f.value">{{ f.label }}</el-radio>
      </el-radio-group>
      <el-button
        type="danger" size="small" data-test="clear-hits"
        :disabled="hits.length === 0" @click="onClear"
      >清空</el-button>
    </div>
    <el-table
      v-loading="loading" :data="hits" row-key="id" border
      data-test="hits-table" class="hits-table" @row-click="openDetail"
      :row-style="{ cursor: 'pointer' }"
    >
      <el-table-column label="时间" width="160">
        <template #default="{ row }">
          <span data-test="hit-time">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="method" label="方法" width="78" align="center" />
      <el-table-column label="路径" min-width="200">
        <template #default="{ row }">
          <span class="hit-path" data-test="hit-path">{{ fullPath(row) }}</span>
          <div v-if="row.error" class="hit-err">{{ row.error }}</div>
        </template>
      </el-table-column>
      <el-table-column label="命中" width="118" align="center">
        <template #default="{ row }">
          <el-tag :type="row.matched ? 'success' : 'danger'" size="small" data-test="hit-tag">
            {{ hitTagText(row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="76" align="center">
        <template #default="{ row }">{{ row.elapsed_ms }}ms</template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && hits.length === 0" description="暂无命中记录" />

    <el-drawer
      v-model="drawerVisible" :title="detail ? `命中 #${detail.id} 详情` : '命中详情'"
      size="46%" data-test="hit-drawer"
    >
      <div v-loading="detailLoading" class="hit-detail">
        <template v-if="detail">
          <el-alert v-if="detail.error" :title="detail.error" type="error" :closable="false" />
          <h4>请求</h4>
          <div class="kv-line">
            <span class="kv-k">时间</span><span>{{ formatTime(detail.created_at) }}</span>
            <span class="kv-k">方法</span><span>{{ detail.method }}</span>
          </div>
          <div class="kv-line">
            <span class="kv-k">路径</span><span class="hit-path">{{ fullPath(detail) }}</span>
          </div>
          <h4>请求头</h4>
          <el-table v-if="headerRows.length" :data="headerRows" border size="small">
            <el-table-column prop="key" label="Header" width="180" />
            <el-table-column prop="value" label="Value" />
          </el-table>
          <p v-else class="muted">无</p>
          <h4>请求体</h4>
          <pre v-if="detail.request_body" class="body-pre" data-test="hit-body">{{ detail.request_body }}</pre>
          <p v-else class="muted">无</p>
          <h4>响应</h4>
          <div class="kv-line">
            <span class="kv-k">状态码</span><span data-test="hit-status">{{ detail.response_status ?? '-' }}</span>
            <span class="kv-k">延迟</span><span>{{ detail.delay_ms }}ms</span>
            <span class="kv-k">耗时</span><span>{{ detail.elapsed_ms }}ms</span>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.hits-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hits-toolbar {
  align-items: center;
  display: flex;
  gap: 8px;
}
.hits-toolbar .el-button {
  margin-left: auto;
}
.hit-path {
  font-family: var(--el-font-family-mono, ui-monospace, Consolas, monospace);
  font-size: 12px;
  word-break: break-all;
}
.hit-err {
  color: var(--el-color-danger);
  font-size: 12px;
  line-height: 1.4;
  word-break: break-all;
}
.hit-detail {
  min-height: 120px;
}
.kv-line {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  margin: 4px 0;
}
.kv-k {
  color: var(--el-text-color-secondary);
}
.kv-k + span {
  color: var(--el-text-color-primary);
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 4px 0;
}
.body-pre {
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  margin: 4px 0;
  max-height: 320px;
  overflow: auto;
  padding: 8px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

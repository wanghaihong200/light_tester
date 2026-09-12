<script setup lang="ts">
// 计划15 T9:HTTP Mock 面板瘦身为纯实例列表;规则组/命中记录下钻独立路由(详情页 T10、命中页 T11 充实)
// projectId 按 brief 无 prop、经 useRoute().params.id 自取;列表 5s 轮询(仅 starting/running 时)
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteMockInstance, listMockInstances, startMockInstance, stopMockInstance,
} from '../../api/mock'
import type { MockInstance, MockInstanceStatus } from '../../types'
import InstanceDialog from './InstanceDialog.vue'

defineOptions({ inheritAttrs: false })

type TagType = 'info' | 'warning' | 'success' | 'danger'
const STATUS_TAG: Record<MockInstanceStatus, TagType> = {
  stopped: 'info', starting: 'warning', running: 'success', error: 'danger',
}
const STATUS_TEXT: Record<MockInstanceStatus, string> = {
  stopped: '已停止', starting: '启动中', running: '运行中', error: '异常',
}

const route = useRoute()
const router = useRouter()
const projectId = computed(() => Number(route.params.id))

const instances = ref<MockInstance[]>([])
const loading = ref(false)
// 三态对齐 AppAutoPane.editing:undefined=关,null=新建,对象=编辑既有实例
const dialogInstance = ref<MockInstance | null | undefined>(undefined)

const baseUrl = (row: MockInstance) => `http://${location.hostname}:${row.port}`

async function copyUrl(row: MockInstance) {
  const url = baseUrl(row)
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success(`已复制 ${url}`)
  } catch {
    ElMessage.warning(`复制失败,请手动复制:${url}`)
  }
}

async function reload() {
  loading.value = true
  try {
    instances.value = await listMockInstances(projectId.value)
    if (disposed) return // 卸载后在途 resolve:不再触发轮询求值
    syncPolling()
  } catch (e) {
    ElMessage.error(`加载实例失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(reload)

// 5s 轮询:仅当存在 starting/running 实例时开启;全静止或卸载即清定时器。
// disposed 守卫:卸载时刻在途的 reload resolve 后不得再 setInterval(否则定时器永久泄漏)
const POLL_MS = 5000
let timer: ReturnType<typeof setInterval> | null = null
let disposed = false

function syncPolling() {
  if (disposed) return
  const active = instances.value.some((i) => i.status === 'starting' || i.status === 'running')
  if (active && timer === null) timer = setInterval(reload, POLL_MS)
  else if (!active && timer !== null) {
    clearInterval(timer)
    timer = null
  }
}
onBeforeUnmount(() => {
  disposed = true
  if (timer !== null) clearInterval(timer)
  timer = null
})

// 「详情」下钻:规则组与命中记录在独立路由页(T10/T11),路由契约见 router/index.ts
// 命名路由须带链上全部参数:/projects/:id 是父级,缺 id 抛 Missing required param「id」
function openDetail(row: MockInstance) {
  router.push({ name: 'project-mock-http-detail', params: { id: projectId.value, instanceId: row.id } })
}

function openCreate() { dialogInstance.value = null }
function openEdit(row: MockInstance) { dialogInstance.value = row }
function onSaved() { dialogInstance.value = undefined; reload() }

async function onStart(row: MockInstance) {
  try {
    await startMockInstance(row.id)
    await reload()
  } catch (e) {
    ElMessage.error(`启动失败:${(e as Error).message}`)
  }
}

async function onStop(row: MockInstance) {
  try {
    await stopMockInstance(row.id)
    await reload()
  } catch (e) {
    ElMessage.error(`停止失败:${(e as Error).message}`)
  }
}

async function onDelete(row: MockInstance) {
  try {
    await ElMessageBox.confirm(`删除实例「${row.name}」?规则与命中记录将一并清除。`, '删除实例', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteMockInstance(row.id)
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}

// el-table 作用域插槽 row 是 any,经这两个小函数收敛映射类型(any 入参合法,索引收进函数体内)
function tagTypeOf(s: MockInstanceStatus): TagType { return STATUS_TAG[s] ?? 'info' }
function statusTextOf(s: MockInstanceStatus): string { return STATUS_TEXT[s] ?? s }
</script>

<template>
  <div class="mock-pane">
    <div class="layout">
      <section class="pane-left">
        <div class="toolbar">
          <span class="pane-title">Mock 实例</span>
          <el-button type="primary" size="small" @click="openCreate">新建实例</el-button>
        </div>
        <el-table v-loading="loading" :data="instances" border>
          <el-table-column prop="name" label="名称" min-width="110" />
          <el-table-column prop="port" label="端口" width="76" />
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <el-tag :type="tagTypeOf(row.status)" size="small">{{ statusTextOf(row.status) }}</el-tag>
              <div v-if="row.status === 'error' && row.error_message" class="err-msg">{{ row.error_message }}</div>
            </template>
          </el-table-column>
          <el-table-column label="base_url" min-width="180">
            <template #default="{ row }">
              <span class="base-url">{{ baseUrl(row) }}</span>
              <el-button link size="small" @click="copyUrl(row)">复制</el-button>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="250">
            <template #default="{ row }">
              <el-button
                size="small" type="primary" :data-test="`instance-detail-${row.port}`"
                @click="openDetail(row)"
              >详情</el-button>
              <el-button
                v-if="row.status === 'running' || row.status === 'starting'"
                size="small" type="warning" @click="onStop(row)"
              >停止</el-button>
              <el-button v-else size="small" type="success" @click="onStart(row)">启动</el-button>
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <InstanceDialog
      v-if="dialogInstance !== undefined" :instance="dialogInstance"
      @close="dialogInstance = undefined" @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.mock-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.layout {
  display: flex;
  flex: 1;
  min-height: 0;
}
.pane-left {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.toolbar {
  align-items: center;
  display: flex;
  gap: 8px;
}
.pane-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.pane-title + .el-button {
  margin-left: auto;
}
.err-msg {
  color: var(--el-color-danger);
  font-size: 12px;
  line-height: 1.4;
  margin-top: 4px;
  word-break: break-all;
}
.base-url {
  color: var(--el-text-color-regular);
  font-size: 12px;
  margin-right: 6px;
  word-break: break-all;
}
</style>

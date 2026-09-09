<script setup lang="ts">
// 计划14 Task10:性能记录手动导入向导(选设备 → 设备历史 → 确认导入)
// 数据流:listAppDevices(仅 state=device)→ listDevicePerfHistory → importPerfHistory;
// 重复导入后端 409(detail 文案含已导入记录 id),前端不判角色、error 直接透传
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAppDevices } from '../../api/appAutomation'
import { importPerfHistory, listDevicePerfHistory } from '../../api/perf'
import type { DeviceInfo, DevicePerfHistoryItem, PerfRecord } from '../../types'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'imported', r: PerfRecord): void }>()

// ── 三步向导状态 ─────────────────────────────────────
const step = ref(0) // 0 选设备 → 1 选历史 → 2 确认导入
const devices = ref<DeviceInfo[]>([])
const devicesLoading = ref(false)
const serial = ref('')
const history = ref<DevicePerfHistoryItem[]>([])
const historyLoading = ref(false)
const selected = ref<DevicePerfHistoryItem | null>(null)
const name = ref('')
const busy = ref(false)

onMounted(loadDevices)

// 开窗拉设备清单,只留在线(state=device),AppRunDialog/ImportDialog 同款过滤
async function loadDevices() {
  devicesLoading.value = true
  try {
    devices.value = (await listAppDevices()).filter((d) => d.state === 'device')
  } catch {
    devices.value = [] // 拉取失败按无在线设备展示(与既有对话框一致,重开窗可重试)
  } finally {
    devicesLoading.value = false
  }
}

// 点设备进历史步并拉取;重选设备时清选中防悬空引用
// 请求序号守卫(仿 PerfRecordPane reloadSeq):快速连点设备时,慢的旧响应不覆盖新设备历史
let pickSeq = 0

async function pickDevice(d: DeviceInfo) {
  const seq = ++pickSeq
  serial.value = d.serial
  step.value = 1
  selected.value = null
  history.value = []
  historyLoading.value = true
  try {
    const items = (await listDevicePerfHistory(d.serial, 200)).items // limit 200:防长采集历史漏单
    if (seq !== pickSeq) return // 等待期间已切设备:丢弃过期响应
    history.value = items
  } catch (e) {
    if (seq !== pickSeq) return
    history.value = []
    ElMessage.error(`加载设备历史失败:${(e as Error).message}`)
  } finally {
    if (seq === pickSeq) historyLoading.value = false
  }
}

function back() {
  step.value = Math.max(0, step.value - 1)
}

// 勾选可用历史即自动进确认步(多勾取最后一条;已导入行 selectable=false 勾不了)
function onSelectionChange(rows: DevicePerfHistoryItem[]) {
  if (!rows.length) {
    selected.value = null
    return
  }
  selected.value = rows[rows.length - 1]
  name.value = `设备导入 ${selected.value.id.slice(0, 20)}` // 截断 20 位对齐后端(backend routers/perf.py)
  step.value = 2
}

// 确认导入:成功按 data_complete 分流提示(截断历史 warning),emit imported 后关窗;
// 失败(含 409 重复)error 透传 detail,窗保持打开可上一步重选
async function confirmImport() {
  if (!selected.value || busy.value) return
  busy.value = true
  try {
    const body: { serial: string; history_id: string; name?: string } = {
      serial: serial.value,
      history_id: selected.value.id,
    }
    const trimmed = name.value.trim()
    if (trimmed) body.name = trimmed
    const record = await importPerfHistory(props.projectId, body)
    // 截断历史就地 warning;完整数据的成功提示由 PerfRecordPane 在 @imported 后统一弹(避免双 toast)
    if (record.data_complete === false) {
      ElMessage.warning('导入成功,但数据不完整(设备端已截断)')
    }
    emit('imported', record)
    emit('close')
  } catch (e) {
    ElMessage.error((e as Error).message) // ApiError.message 即后端 detail(含 409)
  } finally {
    busy.value = false
  }
}

// ── 展示格式化 ───────────────────────────────────────
// 历史的起止是 epoch ms(区别于记录的 ISO 字符串)
function fmtTs(ms: number | null): string {
  if (ms == null) return '—'
  const d = new Date(ms)
  const p = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 人类可读大小:B/KB/MB
function fmtSize(n: number | null): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <el-dialog :model-value="true" title="导入设备性能历史" width="720px" @close="emit('close')">
    <el-steps :active="step" align-center finish-status="success" class="steps">
      <el-step title="选择设备" />
      <el-step title="选择历史" />
      <el-step title="确认导入" />
    </el-steps>

    <!-- 步1:在线设备,点击即进历史步 -->
    <div v-if="step === 0" v-loading="devicesLoading" class="step-body">
      <div v-if="!devicesLoading && devices.length === 0" class="step-hint">未发现在线设备,请先连接设备</div>
      <div
        v-for="d in devices" :key="d.serial" class="device-option"
        data-test="device-option" @click="pickDevice(d)"
      >
        <span class="device-serial">{{ d.serial }}</span>
        <el-tag size="small" type="success">{{ d.state }}</el-tag>
      </div>
    </div>

    <!-- 步2/步3:该设备的历史表在确认步保持挂载(勾选可随时改),已导入行置灰;勾选即进确认步 -->
    <div v-else class="step-body">
      <div v-if="step === 1" class="step-hint">设备 <b>{{ serial }}</b> 的性能采集历史(勾选一条继续)</div>
      <el-table
        v-loading="historyLoading" :data="history" row-key="id" border max-height="360"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="42" :selectable="(row: DevicePerfHistoryItem) => !row.imported_record_id" />
        <el-table-column label="起止时间" min-width="230">
          <template #default="{ row }">{{ fmtTs(row.start_time) }} ~ {{ fmtTs(row.end_time) }}</template>
        </el-table-column>
        <el-table-column label="大小" width="90" align="center">
          <template #default="{ row }">{{ fmtSize(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column label="文件数" width="80" align="center">
          <template #default="{ row }">{{ row.file_count ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="采集项" min-width="120">
          <template #default="{ row }">{{ row.metrics.length ? row.metrics.join(',') : '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.imported_record_id" type="success" size="small">已导入</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 步3:可编辑名称 + 摘要,确认导入;勾选被清空只禁用按钮+提示,不必退步 -->
      <div v-if="step === 2" class="confirm-block">
        <el-form label-width="90px">
          <el-form-item label="记录名称">
            <div data-test="import-name" class="name-wrap">
              <el-input v-model="name" maxlength="100" />
            </div>
          </el-form-item>
        </el-form>
        <el-descriptions :column="1" border size="small" class="summary">
          <el-descriptions-item label="设备">{{ serial }}</el-descriptions-item>
          <el-descriptions-item label="历史 ID">{{ selected?.id }}</el-descriptions-item>
          <el-descriptions-item label="起止时间">{{ selected ? `${fmtTs(selected.start_time)} ~ ${fmtTs(selected.end_time)}` : '—' }}</el-descriptions-item>
          <el-descriptions-item label="文件数">{{ selected?.file_count ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ fmtSize(selected?.size_bytes ?? null) }}</el-descriptions-item>
          <el-descriptions-item label="采集项">{{ selected?.metrics.length ? selected.metrics.join(',') : '—' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="!selected" class="step-hint" data-test="confirm-hint">勾选已被清空,请在上方重新勾选历史后再导入</div>
        <div class="step-hint">同一历史重复导入会被后端拒绝(409);已导入的历史在列表中已置灰。</div>
      </div>
    </div>

    <template #footer>
      <el-button v-if="step > 0" :disabled="busy" @click="back">上一步</el-button>
      <el-button @click="emit('close')">取消</el-button>
      <el-button
        v-if="step === 2" type="primary" :loading="busy" :disabled="!selected || busy"
        data-test="confirm-import" @click="confirmImport"
      >确认导入</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.steps {
  margin-bottom: 14px;
}
.step-body {
  min-height: 120px;
}
.device-option {
  align-items: center;
  cursor: pointer;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  padding: 10px 12px;
}
.device-option:hover {
  background: var(--el-fill-color-light);
}
.device-serial {
  color: var(--el-text-color-primary);
  font-weight: 600;
}
.step-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.name-wrap {
  width: 100%;
}
.summary {
  margin-top: 4px;
}
.confirm-block {
  margin-top: 12px;
}
</style>

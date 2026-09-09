<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  importDeviceCase, importUploadCase, listAppDevices, listDeviceCases,
} from '../../api/appAutomation'
import type { DeviceCase } from '../../api/appAutomation'
import type { AppScript, DeviceInfo } from '../../types'

const props = defineProps<{ projectId: number; visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'imported', s: AppScript): void }>()

const tab = ref('device')
const devices = ref<DeviceInfo[]>([])
const serial = ref('')
const cases = ref<DeviceCase[]>([])
// 选中整个 DeviceCase(同名文件可能同时存在于推送/App导出两目录,单 file_name 区分不了来源)
const sel = ref<DeviceCase | null>(null)
const allowHighRisk = ref(false)
const busy = ref(false)
const syncing = ref(false)

const caseLabel = (c: DeviceCase) => `${c.file_name}(${c.source === 'export' ? 'App导出' : '推送'})`

watch(() => props.visible, async (v) => {
  if (!v) return
  try {
    devices.value = (await listAppDevices()).filter((d) => d.state === 'device')
  } catch { devices.value = [] }
  if (!serial.value) {
    if (devices.value.length) serial.value = devices.value[0].serial // watch(serial) 触发首次同步
  } else {
    await refreshCases() // 重开弹窗:serial 未变不触发 watch,这里显式自动同步
  }
})

// 设备用例同步:重新扫描设备两来源目录,整体替换列表并清空选中(防悬空选中旧文件名)。
// manual=true(手动按钮,Task 2 接入)失败弹错;自动(开窗/切设备)静默——"列表已清空"即错误表达。
async function refreshCases(manual = false) {
  if (!serial.value || syncing.value) return
  cases.value = []
  sel.value = null
  syncing.value = true
  try {
    cases.value = await listDeviceCases(props.projectId, serial.value)
    if (manual && !cases.value.length) ElMessage.info('未在设备上发现已导出的用例')
  } catch (e: any) {
    if (manual) ElMessage.error(e?.message ?? '同步失败') // 透出后端原因(设备离线等)
  } finally {
    syncing.value = false
  }
}

watch(serial, () => { refreshCases() })

async function onImportDevice() {
  if (!serial.value || !sel.value) return
  busy.value = true
  try {
    const s = await importDeviceCase(props.projectId, {
      serial: serial.value, file_name: sel.value.file_name, source: sel.value.source,
      allow_high_risk: allowHighRisk.value })
    ElMessage.success(`已导入「${s.name}」`)
    emit('imported', s)
    emit('update:visible', false)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '导入失败')
  } finally { busy.value = false }
}

async function onUpload(file: File) {
  busy.value = true
  try {
    const s = await importUploadCase(props.projectId, file, { allow_high_risk: allowHighRisk.value })
    ElMessage.success(`已导入「${s.name}」`)
    emit('imported', s)
    emit('update:visible', false)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '上传失败')
  } finally { busy.value = false }
}

// brief 原稿此处是模板内联表达式(对 FileList 误取 [0]),等价改写为脚本函数:取首个选中文件上传
async function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await onUpload(file)
}
</script>

<template>
  <el-dialog :model-value="visible" title="导入用例(手机 SoloPi 录制导出)" width="560px"
             @update:model-value="emit('update:visible', $event)">
    <el-tabs v-model="tab">
      <el-tab-pane label="设备拉取" name="device">
        <div style="display: flex; gap: 8px">
          <el-select v-model="serial" placeholder="选择设备" style="flex: 1">
            <el-option v-for="d in devices" :key="d.serial" :value="d.serial"
                       :label="`${d.serial}(${d.state})`" />
          </el-select>
          <el-button :loading="syncing" :disabled="!serial" @click="refreshCases(true)">同步</el-button>
        </div>
        <el-select v-model="sel" value-key="source" placeholder="选择设备上的用例文件"
                   style="width: 100%; margin-top: 8px">
          <el-option v-for="c in cases" :key="`${c.source}:${c.file_name}`" :value="c"
                     :label="caseLabel(c)" />
        </el-select>
        <div class="sync-hint">列表来自手机已导出的用例;SoloPi App 内录制需先在手机上点"导出用例",平台推送(harness-import)目录的用例同样可见。</div>
      </el-tab-pane>
      <el-tab-pane label="文件上传" name="upload">
        <input type="file" accept=".json,application/json" @change="onFileChange" />
      </el-tab-pane>
    </el-tabs>
    <el-checkbox v-model="allowHighRisk" style="margin-top: 8px">允许高危动作(CLEAR_DATA / KILL_PROCESS / JUMP_TO_PAGE)</el-checkbox>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="busy" :disabled="tab !== 'device' || !sel" @click="onImportDevice">
        导入所选
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.sync-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
</style>

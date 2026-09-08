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

const caseLabel = (c: DeviceCase) => `${c.file_name}(${c.source === 'export' ? 'App导出' : '推送'})`

watch(() => props.visible, async (v) => {
  if (!v) return
  try {
    devices.value = (await listAppDevices()).filter((d) => d.state === 'device')
  } catch { devices.value = [] }
  if (devices.value.length && !serial.value) serial.value = devices.value[0].serial
})

watch(serial, async (s) => {
  cases.value = []
  sel.value = null
  if (!s) return
  try {
    cases.value = await listDeviceCases(props.projectId, s)
  } catch { /* 设备离线等,列表留空 */ }
})

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
        <el-select v-model="serial" placeholder="选择设备" style="width: 100%">
          <el-option v-for="d in devices" :key="d.serial" :value="d.serial"
                     :label="`${d.serial}(${d.state})`" />
        </el-select>
        <el-select v-model="sel" value-key="source" placeholder="选择设备上的用例文件"
                   style="width: 100%; margin-top: 8px">
          <el-option v-for="c in cases" :key="`${c.source}:${c.file_name}`" :value="c"
                     :label="caseLabel(c)" />
        </el-select>
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

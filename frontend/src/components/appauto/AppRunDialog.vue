<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createAppRuns, listAppDevices, listPerfItems,
} from '../../api/appAutomation'
import type { AppRun, AppScript, CheckDef, DeviceInfo } from '../../types'

const props = defineProps<{ projectId: number; scripts: AppScript[]; multi: boolean; visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'close'): void; (e: 'started', runs: AppRun[]): void }>()

const scriptId = ref<number | undefined>(props.scripts[0]?.id)
const devices = ref<DeviceInfo[]>([])
const serials = ref<string[]>([])
const perfAvailable = ref<string[]>([])
const perfSelected = ref<string[]>([])
const startupTime = ref(false)
const allowHighRisk = ref(false)
const preChecks = ref<CheckDef[]>([])
const postChecks = ref<CheckDef[]>([])
const busy = ref(false)

// immediate:Pane 挂载本弹窗时 visible 已为 true(brief 测试即以 visible=true 直挂),
// 无 immediate 则首开不拉设备列表
watch(() => props.visible, async (v) => {
  if (!v) return
  try { devices.value = (await listAppDevices()).filter((d) => d.state === 'device') } catch { devices.value = [] }
}, { immediate: true })

// deep:单设备模式 v-model 写的是 serials[0](数组元素),非浅 watch 能感知的替换
watch(serials, async (list) => {
  perfAvailable.value = []
  const s = list[0]
  if (!s) return
  try { perfAvailable.value = (await listPerfItems(s)).items } catch { perfAvailable.value = [] }
}, { deep: true })

async function run() {
  if (!scriptId.value || serials.value.length === 0) {
    ElMessage.warning('选择脚本与至少一台设备')
    return
  }
  busy.value = true
  try {
    const runs = await createAppRuns(props.projectId, {
      script_id: scriptId.value,
      device_serials: serials.value,
      perf_items: perfSelected.value,
      pre_checks: preChecks.value,
      post_checks: postChecks.value,
      startup_time: startupTime.value,
      allow_high_risk: allowHighRisk.value,
    })
    ElMessage.success(`已发起 ${runs.length} 台设备执行`)
    emit('started', runs)
    emit('update:visible', false)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '发起失败')
  } finally { busy.value = false }
}

function addCheck(kind: 'pre' | 'post') {
  const target = kind === 'pre' ? preChecks : postChecks
  target.value.push({ type: 'text_contains', value: '' })
}

// 测试经 vm 驱动内部状态(仓内先例:AppScriptEditor defineExpose)
defineExpose({ devices, serials, scriptId, perfSelected, run })
</script>

<template>
  <el-dialog :model-value="visible" :title="multi ? '分发批量执行(一用例×多设备)' : '执行(单设备)'"
             width="640px" @update:model-value="emit('update:visible', $event)">
    <el-form label-width="90px">
      <el-form-item label="脚本">
        <select v-model.number="scriptId" data-test="script-select">
          <option v-for="s in scripts" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </el-form-item>
      <el-form-item label="设备">
        <el-checkbox-group v-if="multi" v-model="serials">
          <el-checkbox v-for="d in devices" :key="d.serial" :label="d.serial" :value="d.serial">{{ d.serial }}</el-checkbox>
        </el-checkbox-group>
        <el-select v-else v-model="serials[0]" placeholder="选择设备" style="width: 240px">
          <el-option v-for="d in devices" :key="d.serial" :value="d.serial" :label="d.serial" />
        </el-select>
      </el-form-item>
      <el-form-item label="性能项">
        <el-select v-model="perfSelected" multiple placeholder="可多选(来自 perf-list)" style="width: 100%">
          <el-option v-for="p in perfAvailable" :key="p" :value="p" :label="p" />
        </el-select>
      </el-form-item>
      <el-form-item label="启动耗时"><el-switch v-model="startupTime" /></el-form-item>
      <el-form-item label="高危确认"><el-checkbox v-model="allowHighRisk">允许高危动作</el-checkbox></el-form-item>
    </el-form>
    <details v-for="kind in (['pre', 'post'] as const)" :key="kind">
      <summary>{{ kind === 'pre' ? '前置' : '后置' }}检查点(inspect 自判)</summary>
      <div v-for="(c, i) in kind === 'pre' ? preChecks : postChecks" :key="i" class="check-row">
        <select v-model="c.type" @change="c.value = ''; c.text = ''; c.resource_id = ''">
          <option value="text_contains">文本包含</option>
          <option value="element_exists">控件存在</option>
        </select>
        <el-input v-if="c.type === 'text_contains'" v-model="c.value" placeholder="包含文本" style="width: 200px" />
        <template v-else>
          <el-input v-model="c.resource_id" placeholder="resourceId(可短名)" style="width: 160px" />
          <el-input v-model="c.text" placeholder="text" style="width: 100px" />
          <el-input v-model="c.description" placeholder="description" style="width: 100px" />
        </template>
        <el-button link type="danger"
                   @click="(kind === 'pre' ? preChecks : postChecks).splice(i, 1)">删</el-button>
      </div>
      <el-button link @click="addCheck(kind)">+ 加检查点</el-button>
    </details>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="busy" @click="run">发起执行</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.check-row { display: flex; gap: 6px; align-items: center; margin-top: 6px; }
</style>

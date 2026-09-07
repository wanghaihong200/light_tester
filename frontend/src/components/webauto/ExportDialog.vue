<template>
  <el-dialog
    :model-value="visible"
    title="导出 Playwright 脚本"
    width="560px"
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form label-width="90px">
      <el-form-item label="目标分支">
        <el-select v-model="branch" filterable allow-create placeholder="选择或输入分支名" style="width: 100%">
          <el-option v-for="b in branches" :key="b" :label="b" :value="b" />
        </el-select>
      </el-form-item>
      <el-form-item label="提交说明">
        <el-input v-model="commitMessage" placeholder="commit message" />
      </el-form-item>
    </el-form>
    <!-- 导出校验失败:后端逐条返回不可导出步骤,清单式展示便于回改脚本 -->
    <el-alert v-if="errors.length" type="error" :closable="false" class="export-errors">
      <div v-for="e in errors" :key="e">{{ e }}</div>
    </el-alert>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="busy" @click="onConfirm">导出并推送</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 脚本导出弹窗(plan11):把 Web 脚本生成 Playwright 用例并推送到项目的 web 自动化仓。
// 打开时以 kind=web 拉分支并预填;失败(400 校验清单/透传文案)留在框内展示,不关框可改参重试。
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'
import { listBranches } from '../../api/repo'
import { exportUiScript } from '../../api/uiAutomation'

const props = defineProps<{
  scriptId: number
  projectId: number
  scriptName?: string
  visible: boolean
}>()
const emit = defineEmits<{ 'update:visible': [boolean]; exported: [string] }>()

const branches = ref<string[]>([])
const branch = ref('')
const commitMessage = ref('')
const errors = ref<string[]>([])
const busy = ref(false)

// 每次打开重置状态并重新拉分支(分支可能在两次打开间变化);immediate 兼容挂载即打开的用法
watch(() => props.visible, async (v) => {
  if (!v) return
  errors.value = []
  branch.value = ''
  commitMessage.value = props.scriptName ? `Web自动化导出 ${props.scriptName}` : 'Web自动化导出'
  try {
    branches.value = (await listBranches(props.projectId, 'web')).branches
  } catch {
    branches.value = [] // 拉不到分支不阻塞导出:allow-create 允许手输分支名
  }
  branch.value = branches.value[0] ?? 'master'
}, { immediate: true })

// 后端 400 的 detail 可能是字符串(通用错误)或 {errors:[…]}(导出校验失败清单)。
// client.ts 对非 2xx 抛 ApiError(status, message, body):message = String(detail)
// (dict 形态是 '[object Object]',不能直接展示),结构化原因从 e.body?.detail 还原;
// data/detail 两路为兼容形状兜底,仍无结构时退回 message 文案
function extractExportErrors(e: unknown): string[] {
  const err = e as {
    body?: { detail?: unknown }; data?: { detail?: unknown }; detail?: unknown; message?: string
  } | null
  const detail = err?.body?.detail ?? err?.data?.detail ?? err?.detail
  if (detail && typeof detail === 'object' && Array.isArray((detail as { errors?: unknown }).errors)) {
    return (detail as { errors: unknown[] }).errors.map(String)
  }
  if (typeof detail === 'string' && detail) return [detail]
  if (err?.message && err.message !== '[object Object]') return [err.message]
  return ['导出失败,请检查脚本内容或查看后端日志']
}

// 成功提示带出导出文件清单:登录态文件(auth_states/)显式标注,避免"不知道登录态有没有附带"
// 的误判(2026-09-07 冒烟:提示只有 commit 短哈希,用户看不到登录态已随仓附带)。
function successText(r: { branch: string; commit_short: string; files?: string[] }): string {
  const list = (r.files ?? []).map((f) => (f.startsWith('auth_states/') ? `${f}(登录态)` : f)).join('、')
  return list ? `已推送 ${r.branch}@${r.commit_short} · ${list}` : `已推送 ${r.branch}@${r.commit_short}`
}

async function onConfirm() {
  busy.value = true
  errors.value = []
  try {
    const r = await exportUiScript(props.scriptId, {
      branch: branch.value,
      commit_message: commitMessage.value || undefined,
    })
    ElMessage.success({ message: successText(r), duration: 6000 })
    emit('exported', r.commit_short)
    emit('update:visible', false)
  } catch (e) {
    errors.value = extractExportErrors(e) // 留在框内展示错误,不打断用户改参重试
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.export-errors {
  margin-top: 8px;
}
.export-errors :deep(div) {
  line-height: 1.8;
}
</style>

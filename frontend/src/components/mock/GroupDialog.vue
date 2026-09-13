<script setup lang="ts">
// 计划15 T10:规则组新建/编辑对话框(create/edit 双模);表单/保存/错误处理照 InstanceDialog 既有模式
// 2026-09-13 验收调整:透传配置入组(组即"被 mock 的原始接口":组内规则全不中→转发该组上游)
// 轻校验只拦 method/path_template/透传地址;重路/坏模板段交后端 400 文案直接透出
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createMockRuleGroup, updateMockRuleGroup } from '../../api/mock'
import type { MockRuleGroup } from '../../types'

const props = defineProps<{ instanceId: number; group: MockRuleGroup | null }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved', g: MockRuleGroup): void }>()

// 与后端 HTTP_METHODS 对齐:七值
const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'] as const

const method = ref('GET')
const pathTemplate = ref('')
const description = ref('')
const passthroughEnabled = ref(false)
const upstreamBaseUrl = ref('')
const busy = ref(false)

watch(() => props.group, (g) => {
  method.value = g?.method ?? 'GET'
  pathTemplate.value = g?.path_template ?? ''
  description.value = g?.description ?? ''
  passthroughEnabled.value = g?.passthrough_enabled ?? false
  upstreamBaseUrl.value = g?.upstream_base_url ?? ''
}, { immediate: true })

async function save() {
  if (!method.value) {
    ElMessage.warning('请选择请求方法')
    return
  }
  if (!pathTemplate.value.trim()) {
    ElMessage.warning('请填写路径模板,如 /api/user/{id}')
    return
  }
  // 透传前端校验(与后端 _validate_passthrough 同语义):开关开必须非空 http(s) 地址
  if (passthroughEnabled.value && !upstreamBaseUrl.value.trim()) {
    ElMessage.warning('开启透传必须填写上游地址')
    return
  }
  const upstream = upstreamBaseUrl.value.trim()
  if (upstream && !upstream.startsWith('http://') && !upstream.startsWith('https://')) {
    ElMessage.warning('上游地址须以 http:// 或 https:// 开头')
    return
  }
  busy.value = true
  try {
    const body = {
      method: method.value,
      path_template: pathTemplate.value.trim(),
      description: description.value.trim() || null,
      passthrough_enabled: passthroughEnabled.value,
      upstream_base_url: upstream || null,
    }
    const saved = props.group
      ? await updateMockRuleGroup(props.group.id, body)
      : await createMockRuleGroup(props.instanceId, body)
    ElMessage.success('已保存')
    emit('saved', saved)
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`) // 400(重路/坏模板)文案直接透出
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="true" :title="group ? '编辑规则组' : '新建规则组'" width="520px" @close="emit('close')">
    <el-form label-width="110px">
      <el-form-item label="请求方法" required>
        <el-select v-model="method" class="method-select">
          <el-option v-for="m in METHODS" :key="m" :label="m" :value="m" />
        </el-select>
      </el-form-item>
      <el-form-item label="路径模板" required>
        <el-input v-model="pathTemplate" placeholder="/api/user/{id}" />
        <span class="hint">查询参数放条件,不写进路径</span>
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="description" type="textarea" :rows="2" placeholder="选填,显示在组头" />
      </el-form-item>
      <!-- 组级透传:组内规则全不中时原样转发该组上游,转发不通才回实例兜底 -->
      <el-form-item label="透传">
        <el-switch v-model="passthroughEnabled" data-test="group-passthrough-switch" />
        <span class="hint">开启后:组内规则全不中时,请求原样转发到本组对应的真实接口,转发不通才回兜底</span>
      </el-form-item>
      <el-form-item v-if="passthroughEnabled" label="上游地址">
        <el-input
          v-model="upstreamBaseUrl" data-test="group-upstream-url"
          placeholder="http://real-api:8080"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="busy" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.method-select {
  width: 160px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>

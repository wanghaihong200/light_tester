<script setup lang="ts">
// 计划13 T9:Mock 实例新建/编辑对话框(create/edit 双模)
// prop 契约照 brief:仅 instance?: MockInstance | null;projectId 同 MockPane 从路由取参
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createMockInstance, updateMockInstance } from '../../api/mock'
import type { MockInstance } from '../../types'

const props = defineProps<{ instance?: MockInstance | null }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved', s: MockInstance): void }>()

const route = useRoute()
const projectId = computed(() => Number(route.params.id))

const name = ref('')
const description = ref('')
const port = ref<number | null>(null)
const cors = ref(false)
const defaultStatus = ref(200)
const defaultBody = ref('')
const busy = ref(false)

// edit 模式且实例处于 running/starting 时端口锁定(与后端 409 对齐)
const portLocked = computed(() =>
  !!props.instance && (props.instance.status === 'running' || props.instance.status === 'starting'))

watch(() => props.instance, (s) => {
  name.value = s?.name ?? ''
  description.value = s?.description ?? ''
  port.value = s?.port ?? null
  cors.value = s?.cors_enabled ?? false
  defaultStatus.value = s?.default_status ?? 200
  defaultBody.value = s?.default_body ?? ''
}, { immediate: true })

async function save() {
  if (!name.value.trim()) {
    ElMessage.warning('请填写实例名称')
    return
  }
  busy.value = true
  try {
    const body = {
      name: name.value.trim(),
      description: description.value.trim() || null,
      port: port.value ?? null,
      cors_enabled: cors.value,
      default_status: defaultStatus.value,
      default_body: defaultBody.value.trim() || null,
    }
    const saved = props.instance
      ? await updateMockInstance(props.instance.id, body)
      : await createMockInstance(projectId.value, body)
    ElMessage.success('已保存')
    emit('saved', saved)
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="true" :title="instance ? '编辑实例' : '新建实例'" width="520px" @close="emit('close')">
    <el-form label-width="110px">
      <el-form-item label="名称" required>
        <el-input v-model="name" placeholder="实例名称" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="description" placeholder="选填" />
      </el-form-item>
      <el-form-item label="端口">
        <el-input-number
          v-model="port" :min="1" :max="65535" :disabled="portLocked"
          placeholder="留空自动分配" controls-position="right" class="port-input"
        />
        <span v-if="portLocked" class="port-lock-tip">运行中实例不可改端口</span>
      </el-form-item>
      <el-form-item label="允许跨域">
        <el-switch v-model="cors" />
      </el-form-item>
      <el-form-item label="默认响应码">
        <el-input-number v-model="defaultStatus" :min="100" :max="599" controls-position="right" />
      </el-form-item>
      <el-form-item label="默认响应体">
        <el-input v-model="defaultBody" type="textarea" :rows="4" placeholder="默认返回的响应体" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="busy" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.port-input {
  width: 100%;
}
.port-lock-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>

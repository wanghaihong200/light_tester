<template>
  <el-form label-width="80px">
    <el-form-item label="功能点名称" required>
      <el-input v-model="name" class="name-input" maxlength="200" />
    </el-form-item>
    <el-form-item>
      <el-button class="save-btn" type="primary" :loading="saving" @click="save">保存</el-button>
      <el-button class="delete-btn" type="danger" plain @click="remove">删除</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { ref } from 'vue'
import { deleteFeaturePoint, updateFeaturePoint } from '../api/tree'

const props = defineProps<{ featurePointId: number; initialName: string }>()
const emit = defineEmits<{ (e: 'saved'): void; (e: 'deleted'): void }>()

const name = ref(props.initialName)
const saving = ref(false)

async function save() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    ElMessage.warning('功能点名称不能为空')
    return
  }
  saving.value = true
  try {
    await updateFeaturePoint(props.featurePointId, trimmed)
    ElMessage.success('已保存')
    emit('saved')
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm('将删除该功能点及其下所有用例,确定?', '删除功能点', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteFeaturePoint(props.featurePointId)
    ElMessage.success('已删除')
    emit('deleted')
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}
</script>

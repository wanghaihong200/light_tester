<template>
  <el-form label-width="80px">
    <el-form-item label="模块名称" required>
      <el-input v-model="name" class="name-input" maxlength="200" />
    </el-form-item>
    <el-form-item label="父模块">
      <el-select v-model="parentId" clearable placeholder="顶层模块" data-testid="parent-select">
        <el-option v-for="m in parentCandidate" :key="m.id" :label="`${'　'.repeat(m.depth)}${m.name}`" :value="m.id" />
      </el-select>
    </el-form-item>
    <el-form-item>
      <el-button class="save-btn" type="primary" :loading="saving" @click="save">保存</el-button>
      <el-button class="delete-btn" type="danger" plain @click="remove">删除</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { flattenModules } from '../adapters/tree'
import { deleteModule, fetchTree, updateModule } from '../api/tree'
import type { ModuleNode } from '../types'

const props = defineProps<{
  projectId: number
  moduleId: number
  initialName: string
  initialParentId: number | null
}>()
const emit = defineEmits<{ (e: 'saved'): void; (e: 'deleted'): void }>()

const name = ref(props.initialName)
const parentId = ref<number | null>(props.initialParentId)
const saving = ref(false)
// 模块移动候选:排除自身子树,防自嵌套(后端亦有守卫)
const parentCandidate = ref<Array<{ id: number; name: string; depth: number }>>([])

onMounted(async () => {
  try {
    const tree: ModuleNode[] = await fetchTree(props.projectId)
    parentCandidate.value = flattenModules(tree, props.moduleId)
  } catch (e) {
    ElMessage.error(`加载父模块候选失败:${(e as Error).message}`)
  }
})

async function save() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    ElMessage.warning('模块名称不能为空')
    return
  }
  saving.value = true
  try {
    await updateModule(props.moduleId, { name: trimmed, parentId: parentId.value })
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
    await ElMessageBox.confirm('将级联删除该模块下所有子模块、功能点与用例,确定?', '删除模块', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteModule(props.moduleId)
    ElMessage.success('已删除')
    emit('deleted')
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}
</script>

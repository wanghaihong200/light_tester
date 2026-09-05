<template>
  <div v-loading="loading">
    <el-form label-width="80px">
      <el-form-item label="标题" required>
        <el-input v-model="form.title" class="title-input" maxlength="500" />
      </el-form-item>
      <el-form-item label="优先级">
        <el-radio-group v-model="form.priority">
          <el-radio-button value="P0">P0</el-radio-button>
          <el-radio-button value="P1">P1</el-radio-button>
          <el-radio-button value="P2">P2</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="执行结果">
        <el-radio-group v-model="execution">
          <el-radio-button :value="true">通过</el-radio-button>
          <el-radio-button :value="false">未通过</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="前置条件">
        <el-input v-model="form.precondition" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="步骤">
        <div v-for="(step, i) in form.steps" :key="i" class="step-row">
          <div class="step-index">{{ i + 1 }}</div>
          <div class="step-inputs">
            <el-input v-model="step.action" class="step-action" type="textarea" :rows="1" placeholder="操作" />
            <el-input v-model="step.expected" class="step-expected" type="textarea" :rows="1" placeholder="预期" />
          </div>
          <el-button type="danger" text @click="form.steps.splice(i, 1)">删除</el-button>
        </div>
        <el-button class="add-step-btn" @click="form.steps.push({ action: '', expected: '' })">+ 添加步骤</el-button>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item>
        <el-button class="save-btn" type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button class="delete-btn" type="danger" plain @click="remove">删除</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { deleteCase, getCase, patchExecution, updateCase } from '../api/cases'
import type { Priority } from '../types'

const props = defineProps<{ caseId: number }>()
const emit = defineEmits<{ (e: 'saved'): void; (e: 'deleted'): void }>()

const loading = ref(true)
const saving = ref(false)
const execution = ref<boolean | null>(null)
const form = reactive({
  title: '',
  priority: 'P1' as Priority,
  precondition: '',
  remark: '',
  steps: [] as Array<{ action: string; expected: string }>,
})

onMounted(async () => {
  try {
    const c = await getCase(props.caseId)
    form.title = c.title
    form.priority = c.priority
    form.precondition = c.precondition ?? ''
    form.remark = c.remark ?? ''
    form.steps = c.steps.map((s) => ({ action: s.action, expected: s.expected }))
    execution.value = c.executed_pass
  } catch (e) {
    ElMessage.error(`加载用例失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
})

async function save() {
  if (!form.title.trim()) {
    ElMessage.warning('用例标题不能为空')
    return
  }
  // 后端 StepIn 要求 action/expected 非空(min_length=1),空串会 422
  if (form.steps.some((s) => !s.action.trim() || !s.expected.trim())) {
    ElMessage.warning('步骤的操作与预期都不能为空,请补全或删除空白步骤')
    return
  }
  saving.value = true
  try {
    await updateCase(props.caseId, {
      title: form.title.trim(),
      priority: form.priority,
      precondition: form.precondition || null,
      remark: form.remark || null,
      steps: form.steps.map((s) => ({ action: s.action.trim(), expected: s.expected.trim() })),
    })
    try {
      await patchExecution(props.caseId, execution.value) // 执行结果独立接口(后端契约)
    } catch (e2) {
      ElMessage.error(`内容已保存,但执行结果保存失败:${(e2 as Error).message}`)
      emit('saved') // 内容已落库,父级刷新合理
      return
    }
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
    await ElMessageBox.confirm('确定删除该用例?', '删除用例', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteCase(props.caseId)
    ElMessage.success('已删除')
    emit('deleted')
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}
</script>

<style scoped>
.step-row {
  display: flex;
  gap: 8px;
  width: 100%;
  align-items: flex-start;
  margin-bottom: 8px;
}
.step-index {
  padding-top: 4px;
  color: #909399;
}
.step-inputs {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>

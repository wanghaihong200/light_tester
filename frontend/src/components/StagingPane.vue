<template>
  <div class="staging-pane">
    <p class="hint">暂存区仅有「要/不要」裁决权,入库后请在用例导图中编辑</p>
    <div class="content">
      <div class="left">
        <div class="tools">
          <el-checkbox :model-value="isAllSelected" @change="onSelectAll">全选</el-checkbox>
          <span class="count">已选 {{ selectedIds.length }}/{{ totalCount }}</span>
          <el-button :disabled="selectedIds.length === 0" @click="doAccept">入库所选</el-button>
          <el-button :disabled="selectedIds.length === 0" @click="doReject">拒绝所选</el-button>
        </div>
        <el-collapse>
          <el-collapse-item
            v-for="group in groups"
            :key="group.feature_point_name"
            :title="`${group.feature_point_name} (${group.cases.length})`"
          >
            <el-checkbox
              v-for="c in group.cases"
              :key="c.id"
              :model-value="selectedIds.includes(c.id)"
              @change="(val: boolean) => toggle(c.id, val)"
            >
              [{{ c.priority }}] {{ c.title }}
            </el-checkbox>
          </el-collapse-item>
        </el-collapse>
      </div>
      <div class="right">
        <MindmapEditor v-if="previewData" :data="previewData" />
        <p v-else class="preview-hint">勾选左侧用例查看预览</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { acceptStaging, listStaging, rejectStaged } from '../api/jobs'
import { stagedToMindmap, stagedTotal } from '../adapters/staging'
import MindmapEditor from './MindmapEditor.vue'
import type { StagingGroup } from '../types'

const props = defineProps<{ jobId: number }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'accepted'): void }>()

const groups = ref<StagingGroup[]>([])
const selectedIds = ref<number[]>([])

const totalCount = computed(() => stagedTotal(groups.value))
const isAllSelected = computed(() => selectedIds.value.length === totalCount.value && totalCount.value > 0)

const previewGroups = computed(() => {
  const set = new Set(selectedIds.value)
  return groups.value
    .map(g => ({ ...g, cases: g.cases.filter(c => set.has(c.id)) }))
    .filter(g => g.cases.length > 0)
})

const previewData = computed(() => {
  if (selectedIds.value.length === 0) return null
  return stagedToMindmap('预览', previewGroups.value)
})

function toggle(id: number, checked: boolean) {
  if (checked && !selectedIds.value.includes(id)) {
    selectedIds.value.push(id)
  } else if (!checked) {
    selectedIds.value = selectedIds.value.filter(x => x !== id)
  }
}

function onSelectAll(val: boolean) {
  if (val) {
    selectedIds.value = groups.value.flatMap(g => g.cases.map(c => c.id))
  } else {
    selectedIds.value = []
  }
}

async function load() {
  try {
    const res = await listStaging(props.jobId)
    groups.value = res.groups
    selectedIds.value = []
  } catch (e) {
    ElMessage.error(`加载暂存区失败:${(e as Error).message}`)
  }
}

onMounted(load)

async function doAccept() {
  const ids = [...selectedIds.value]
  try {
    const res = await acceptStaging(props.jobId, ids)
    ElMessage.success(`已入库 ${res.accepted} 条`)
    emit('accepted')
    await load()
    if (stagedTotal(groups.value) === 0) {
      ElMessage.info('暂存区已清空')
      emit('close')
    }
  } catch (e) {
    ElMessage.error(`入库失败:${(e as Error).message}`)
  }
}

async function doReject() {
  const ids = [...selectedIds.value]
  try {
    await ElMessageBox.confirm(`拒绝所选 ${ids.length} 条?删除后不可恢复`)
  } catch {
    return
  }
  for (const id of ids) {
    try {
      await rejectStaged(id)
    } catch (e) {
      ElMessage.error(`拒绝失败:${(e as Error).message}`)
      break
    }
  }
  await load()
  if (stagedTotal(groups.value) === 0) {
    ElMessage.info('暂存区已清空')
    emit('close')
  }
}
</script>

<style scoped>
.staging-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-bottom: 12px;
}
.content {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.left {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.tools {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.count {
  color: #909399;
  font-size: 13px;
}
.right {
  flex: 1;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
  min-height: 400px;
}
.preview-hint {
  text-align: center;
  color: #909399;
  padding: 60px 0;
}
</style>

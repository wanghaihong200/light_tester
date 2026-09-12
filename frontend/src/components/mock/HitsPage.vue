<script setup lang="ts">
// 计划15 T11:命中记录页——组筛选 + HitsPanel(实例命中面板复用)
// instanceId 自路由取参;query.group 预选组(仅当 id 在组列表中);头部返回规则组页
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getMockInstance, listMockRuleGroups } from '../../api/mock'
import type { MockInstance, MockRuleGroup } from '../../types'
import HitsPanel from './HitsPanel.vue'

const route = useRoute()
const router = useRouter()
const instanceId = computed(() => Number(route.params.instanceId))
const projectId = computed(() => Number(route.params.id))

const instance = ref<MockInstance | null>(null)
const groups = ref<MockRuleGroup[]>([])
const groupId = ref<number | null>(null)

onMounted(async () => {
  try {
    instance.value = await getMockInstance(instanceId.value)
    groups.value = await listMockRuleGroups(instanceId.value)
    // 直链带 query.group:仅当 id 在组列表中才预选,脏参回落「全部规则组」
    const q = Number(route.query.group)
    groupId.value = groups.value.some((g) => g.id === q) ? q : null
  } catch (e) {
    ElMessage.error(`加载命中记录失败:${(e as Error).message}`)
  }
})

const groupLabel = (g: MockRuleGroup) => `${g.method} ${g.path_template}`
</script>

<template>
  <div class="hits-page">
    <div class="hits-head">
      <!-- 命名路由须带链上全部参数:/projects/:id 是父级,缺 id 抛 Missing required param「id」 -->
      <el-button link @click="router.push({ name: 'project-mock-http-detail', params: { id: projectId, instanceId } })">
        ← 返回规则组
      </el-button>
      <span class="hits-title">{{ instance?.name }} · 命中记录</span>
      <el-select
        v-model="groupId" data-test="group-filter" class="group-filter" clearable
        placeholder="全部规则组" size="small"
      >
        <el-option v-for="g in groups" :key="g.id" :value="g.id" :label="groupLabel(g)" />
      </el-select>
    </div>
    <HitsPanel :instance-id="instanceId" :group-id="groupId" />
  </div>
</template>

<style scoped>
.hits-page {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
}
.hits-head {
  align-items: center;
  display: flex;
  gap: 10px;
}
.hits-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
/* 组筛选靠右,260px 对齐 brief */
.group-filter {
  margin-left: auto;
  width: 260px;
}
</style>

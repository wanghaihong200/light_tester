<template>
  <div class="project-view">
    <div class="panel-card">
      <div class="panel-head">
        <h3 class="panel-title">{{ project?.name ?? (loaded ? '项目不存在' : '加载中…') }}</h3>
        <span v-if="project?.description" class="panel-desc">{{ project.description }}</span>
        <!-- 成员按钮对所有人可见:viewer 也能读成员列表,变更操作由后端 owner 闸拦截 -->
        <el-button
          v-if="project"
          class="members-btn"
          size="small"
          data-test="members-btn"
          @click="membersVisible = true"
        >
          成员
        </el-button>
      </div>
      <!-- 功能段由嵌套路由渲染;project 未就绪不挂子段(子组件要求 id 非空)。
           props 按需下发:project-name 仅导图段需要,project 对象仅任务/工程段需要,
           其余段传 undefined,避免对象落入 $attrs 渲染成脏 DOM 属性 -->
      <!-- 定高 flex 链(教训⑦):替代原 el-tabs 的 .tabs 高度链,功能段容器要真实尺寸 -->
      <div class="panel-body">
        <router-view v-slot="{ Component }">
          <component
            :is="Component"
            v-if="project"
            :key="componentKey"
            :project-id="project.id"
            :project-name="route.name === 'project-cases' ? project.name : undefined"
            :project="needsProjectObject ? project : undefined"
            @staging-accepted="onStagingAccepted"
          />
        </router-view>
      </div>
    </div>
    <ProjectMembersDialog v-if="project" :visible="membersVisible" :project-id="project.id" @update:visible="membersVisible = $event" />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ProjectMembersDialog from '../components/ProjectMembersDialog.vue'
import { listProjects } from '../api/projects'
import type { Project } from '../types'

const route = useRoute()
const project = ref<Project | null>(null)
const loaded = ref(false)
const membersVisible = ref(false)

// 任务/工程段(JobsPane/RepoPane)的 props 契约要求完整 project 对象
const needsProjectObject = computed(
  () => route.name === 'project-ai-jobs' || route.name === 'project-ai-repo',
)

// 暂存转正后导图需重挂刷新。重挂键只在 cases 段携带计数:
// 转正发生在任务段,key 在切回 cases 时才求值,天然实现"延迟到激活时重挂";
// 其他段 key 恒定,绝不误重挂(任务段 SSE 连接不因重挂中断)
const remountCases = ref(0)
const componentKey = computed(() =>
  route.name === 'project-cases' ? `cases-${remountCases.value}` : String(route.name ?? ''),
)
function onStagingAccepted(): void {
  remountCases.value++
}

onMounted(async () => {
  try {
    const id = Number(route.params.id)
    const all = await listProjects()
    project.value = all.find((p) => p.id === id) ?? null
    if (!project.value) ElMessage.error('项目不存在')
  } catch (e) {
    ElMessage.error(`加载项目失败:${(e as Error).message}`)
  } finally {
    loaded.value = true
  }
})
</script>

<style scoped>
.project-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.panel-card {
  background: var(--pro-card-bg);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-large);
  box-shadow: var(--pro-card-shadow);
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: 8px 12px;
}
.panel-head {
  align-items: baseline;
  display: flex;
  gap: 12px;
}
.panel-title {
  color: var(--el-text-color-primary);
  font-size: 16px;
  margin: 0 0 4px;
}
.panel-desc {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.members-btn {
  margin-left: auto;
}
.panel-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
/* 功能段 Pane 根元素(height:100%/自身 flex 链)在定高容器内撑满剩余空间 */
.panel-body > :deep(*) {
  flex: 1;
  min-height: 0;
}
</style>

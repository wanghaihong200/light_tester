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
      <el-tabs v-model="tab" class="tabs">
        <el-tab-pane label="用例导图" name="mindmap">
          <MindmapPane v-if="project" :key="mindmapKey" :project-id="project.id" :project-name="project.name" />
        </el-tab-pane>
        <el-tab-pane label="文档库" name="documents">
          <DocumentsPane v-if="project" :project-id="project.id" />
        </el-tab-pane>
        <el-tab-pane label="生成任务" name="jobs">
          <JobsPane v-if="project" :project-id="project.id" :project="project" @staging-accepted="onStagingAccepted" />
        </el-tab-pane>
        <el-tab-pane label="自动化工程" name="repo">
          <RepoPane v-if="project && tab === 'repo'" :project-id="project.id" :project="project" />
        </el-tab-pane>
        <el-tab-pane label="Web自动化" name="webauto">
          <WebAutoPane v-if="project && tab === 'webauto'" :project-id="project.id" />
        </el-tab-pane>
      </el-tabs>
    </div>
    <ProjectMembersDialog v-if="project" :visible="membersVisible" :project-id="project.id" @update:visible="membersVisible = $event" />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import DocumentsPane from '../components/DocumentsPane.vue'
import JobsPane from '../components/JobsPane.vue'
import MindmapPane from '../components/MindmapPane.vue'
import ProjectMembersDialog from '../components/ProjectMembersDialog.vue'
import RepoPane from '../components/RepoPane.vue'
import WebAutoPane from '../components/webauto/WebAutoPane.vue'
import { listProjects } from '../api/projects'
import { useTabs } from '../composables/useTabs'
import type { Project } from '../types'

const route = useRoute()
const { openProject } = useTabs()
const project = ref<Project | null>(null)
const loaded = ref(false)
const tab = ref('mindmap')
const membersVisible = ref(false)
const mindmapKey = ref(0)
const mindmapDirty = ref(false)

// 转正后导图需重挂刷新;但导图 tab 隐藏时容器 display:none 尺寸为 0,
// simple-mind-map 构造会抛"容器元素el的宽高不能为0"——推迟到 tab 激活时再重挂
function onStagingAccepted() {
  if (tab.value === 'mindmap') {
    mindmapKey.value++
  } else {
    mindmapDirty.value = true
  }
}

watch(tab, (t) => {
  if (t === 'mindmap' && mindmapDirty.value) {
    mindmapDirty.value = false
    mindmapKey.value++
  }
})

onMounted(async () => {
  try {
    const id = Number(route.params.id)
    const all = await listProjects()
    project.value = all.find((p) => p.id === id) ?? null
    openProject(id, project.value?.name ?? '未知项目') // 页签名回填(已存在则改名)
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
  padding: 12px 16px;
}
.panel-head {
  align-items: baseline;
  display: flex;
  gap: 12px;
}
.panel-title {
  color: var(--el-text-color-primary);
  font-size: 16px;
  margin: 0 0 8px;
}
.panel-desc {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.members-btn {
  margin-left: auto;
}
.tabs {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.tabs :deep(.el-tabs__content) {
  flex: 1;
}
.tabs :deep(.el-tab-pane) {
  height: 100%;
}
</style>

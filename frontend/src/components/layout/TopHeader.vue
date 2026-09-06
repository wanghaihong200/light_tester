<template>
  <header class="top-header">
    <button class="collapse-btn" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="emit('toggle-collapse')">☰</button>
    <nav class="crumb">
      <span class="crumb-link" @click="emit('navigate', '/')">首页</span>
      <template v-if="currentProjectName">
        <span class="crumb-sep">/</span>
        <span class="crumb-current">{{ currentProjectName }}</span>
      </template>
    </nav>
    <!-- 正中项目切换器:始终显示;数据源 listProjects(权限语义继承,非成员项目后端 404 不可见);切换永远落默认功能页 -->
    <div class="project-switcher" data-test="project-switcher">
      <el-select
        v-model="selectedId"
        class="switcher-select"
        filterable
        placeholder="切换项目"
        @change="onSwitch"
      >
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
    </div>
    <!-- 右侧用户区:用户管理入口仅管理员可见 -->
    <div v-if="user" class="user-area">
      <a v-if="isAdmin" class="admin-link" href="#/users" data-test="admin-link">用户管理</a>
      <span class="user-name" data-test="user-name">{{ user.display_name }}</span>
      <el-button link size="small" data-test="logout" @click="logout">退出</el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { listProjects } from '../../api/projects'
import { useAuth } from '../../composables/useAuth'
import type { Project } from '../../types'

defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{ (e: 'navigate', path: string): void; (e: 'toggle-collapse'): void }>()

const route = useRoute()
const { user, isAdmin, fetchMe, logout } = useAuth()

// —— 面包屑名与下拉共用一份项目列表(拉取失败不阻塞布局,同 SideMenu 容错惯例) ——
const projects = ref<Project[]>([])
const selectedId = ref<number | null>(null)
const currentId = computed(() => (route.params.id ? Number(route.params.id) : null))
const currentProjectName = computed(() => projects.value.find((p) => p.id === currentId.value)?.name ?? '')

// 路由变化(含切换后落地)回写下拉选中值
watch(currentId, (id) => { selectedId.value = id }, { immediate: true })

function onSwitch(id: number): void {
  emit('navigate', `/projects/${id}`)
}

onMounted(async () => {
  try {
    projects.value = await listProjects()
  } catch {
    /* 忽略 */
  }
  try {
    await fetchMe()
  } catch {
    /* 忽略;未登录 401 已由 client 统一踢登录 */
  }
})
</script>

<style scoped>
.top-header {
  align-items: center;
  backdrop-filter: blur(18px);
  background: var(--pro-topbar-bg);
  border-bottom: 1px solid rgba(223, 229, 244, 0.84);
  display: flex;
  flex-shrink: 0;
  gap: 12px;
  height: 48px;
  padding: 0 16px;
  position: relative;
}
.collapse-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 4px 6px;
}
.crumb {
  align-items: center;
  color: var(--pro-muted);
  display: flex;
  font-size: 13px;
  gap: 8px;
}
.crumb-link {
  cursor: pointer;
}
.crumb-link:hover {
  color: var(--el-color-primary);
}
.crumb-current {
  color: var(--el-text-color-primary);
  font-weight: 600;
}
/* 正中绝对定位:不受左右两侧宽度差影响,「首页/项目」行的几何中点 */
.project-switcher {
  left: 50%;
  position: absolute;
  transform: translateX(-50%);
  width: 240px;
}
.user-area {
  align-items: center;
  display: flex;
  font-size: 13px;
  gap: 12px;
  margin-left: auto;
}
.admin-link {
  color: var(--pro-muted);
  cursor: pointer;
  text-decoration: none;
}
.admin-link:hover {
  color: var(--el-color-primary);
}
.user-name {
  color: var(--el-text-color-primary);
}
</style>

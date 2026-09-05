<template>
  <aside class="side-menu" :class="{ collapsed }">
    <div class="brand" @click="emit('navigate', '/')">
      <span class="brand-logo">轻</span>
      <span v-if="!collapsed" class="brand-name">轻测试</span>
    </div>
    <div class="menu-item" :class="{ active: activeKey === 'home' }" @click="emit('navigate', '/')">
      <span class="menu-icon">⌂</span>
      <span v-if="!collapsed" class="menu-name">首页</span>
    </div>
    <div v-if="!collapsed" class="menu-group">项目</div>
    <div
      v-for="p in projects"
      :key="p.id"
      class="menu-item"
      :class="{ active: activeKey === `project-${p.id}` }"
      :title="collapsed ? p.name : undefined"
      @click="emit('navigate', `/projects/${p.id}`)"
    >
      <span class="menu-icon">{{ p.name.slice(0, 1) }}</span>
      <span v-if="!collapsed" class="menu-name">{{ p.name }}</span>
    </div>
    <div class="menu-spacer" />
  </aside>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listProjects } from '../../api/projects'
import type { Project } from '../../types'

defineProps<{ activeKey: string; collapsed: boolean }>()
const emit = defineEmits<{ (e: 'navigate', path: string): void }>()

const projects = ref<Project[]>([])
// 拉取失败不阻塞布局:侧栏只是快捷入口,页面内仍有完整错误提示
onMounted(async () => {
  try {
    projects.value = await listProjects()
  } catch {
    /* 忽略 */
  }
})
</script>

<style scoped>
.side-menu {
  background: var(--pro-sidebar-bg);
  border-right: 1px solid var(--pro-sidebar-border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  padding: 12px 10px;
  transition: width 0.2s ease;
  width: 200px;
  flex-shrink: 0;
}
.side-menu.collapsed {
  width: 65px;
}
.brand {
  align-items: center;
  cursor: pointer;
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  padding: 4px 8px;
}
.brand-logo {
  align-items: center;
  background: var(--el-color-primary);
  border-radius: var(--border-radius-base);
  color: #fff;
  display: flex;
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 700;
  height: 30px;
  justify-content: center;
  width: 30px;
}
.brand-name {
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap;
}
.menu-group {
  color: var(--pro-muted);
  font-size: 11px;
  margin: 10px 8px 4px;
}
.menu-item {
  align-items: center;
  border-radius: var(--border-radius-base);
  color: var(--el-text-color-regular);
  cursor: pointer;
  display: flex;
  gap: 8px;
  margin-bottom: 2px;
  padding: 8px 10px;
  white-space: nowrap;
}
.menu-item:hover {
  background: var(--el-color-primary-light-9);
}
.menu-item.active {
  background: var(--el-color-primary);
  color: #fff;
}
.menu-icon {
  flex-shrink: 0;
  font-size: 13px;
  height: 16px;
  line-height: 16px;
  text-align: center;
  width: 16px;
}
.menu-spacer {
  flex: 1;
}
</style>

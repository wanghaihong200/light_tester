<template>
  <header class="top-header">
    <button class="collapse-btn" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="emit('toggle-collapse')">☰</button>
    <nav class="crumb">
      <span class="crumb-link" @click="emit('navigate', '/')">首页</span>
      <template v-if="projectName">
        <span class="crumb-sep">/</span>
        <span class="crumb-current">{{ projectName }}</span>
      </template>
    </nav>
    <!-- 右侧用户区:用户管理入口仅管理员可见(#/users 路由由用户管理任务落地) -->
    <div v-if="user" class="user-area">
      <a v-if="isAdmin" class="admin-link" href="#/users" data-test="admin-link">用户管理</a>
      <span class="user-name" data-test="user-name">{{ user.display_name }}</span>
      <el-button link size="small" data-test="logout" @click="logout">退出</el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuth } from '../../composables/useAuth'

defineProps<{ projectName?: string; collapsed: boolean }>()
const emit = defineEmits<{ (e: 'navigate', path: string): void; (e: 'toggle-collapse'): void }>()

const { user, isAdmin, fetchMe, logout } = useAuth()
// 拉取失败不阻塞布局(同 SideMenu 容错);未登录 401 已由 client 统一踢登录
onMounted(async () => {
  try {
    await fetchMe()
  } catch {
    /* 忽略 */
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

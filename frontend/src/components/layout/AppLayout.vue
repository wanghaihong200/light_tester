<template>
  <div class="app-layout">
    <SideMenu :active-key="activeKey" :collapsed="collapsed" @navigate="go" />
    <div class="app-main">
      <TopHeader
        :project-name="currentProjectName"
        :collapsed="collapsed"
        @navigate="go"
        @toggle-collapse="collapsed = !collapsed"
      />
      <TabBar :active-key="activeKey" @select="onTabSelect" @close="onTabClose" />
      <!-- 定高 flex 链:导图编辑器依赖容器有真实尺寸(教训⑦);滚动交给内容区自身 -->
      <main class="app-content">
        <!-- 按路径强制重挂:同一路由记录仅参数变化时 vue-router 会复用实例,onMounted 不重跑,导致数据与页签名 stale -->
        <router-view :key="route.path" />
      </main>
      <footer class="app-footer">轻测试 LightTester · Powered by Vue3 + FastAPI</footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTabs } from '../../composables/useTabs'
import SideMenu from './SideMenu.vue'
import TabBar from './TabBar.vue'
import TopHeader from './TopHeader.vue'

const route = useRoute()
const router = useRouter()
const { tabs, openProject, closeTab } = useTabs()
const collapsed = ref(false)

// 活跃页签由路由派生(单一事实源),不做手动同步
const activeKey = computed(() => {
  const m = route.path.match(/^\/projects\/(\d+)$/)
  return m ? `project-${m[1]}` : 'home'
})

const currentProjectName = computed(() => {
  const hit = tabs.value.find((t) => t.key === activeKey.value)
  return hit && hit.id !== undefined ? hit.name : ''
})

// 刷新/直达项目路由时页签可能不存在:先占位,ProjectView 加载后回填真名
watch(
  () => route.path,
  (path) => {
    const m = path.match(/^\/projects\/(\d+)$/)
    if (m && !tabs.value.some((t) => t.key === `project-${m[1]}`)) {
      openProject(Number(m[1]), '加载中…')
    }
  },
  { immediate: true },
)

function keyToPath(key: string): string {
  return key === 'home' ? '/' : `/projects/${key.slice('project-'.length)}`
}

function go(path: string): void {
  if (route.path !== path) void router.push(path)
}
function onTabSelect(key: string): void {
  go(keyToPath(key))
}
function onTabClose(key: string): void {
  const target = closeTab(key, activeKey.value)
  if (target) go(keyToPath(target))
}
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.app-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}
.app-content {
  background: transparent;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 16px 16px;
}
.app-footer {
  background: rgba(247, 249, 255, 0.88);
  border-top: 1px solid var(--pro-sidebar-border);
  color: var(--pro-muted);
  flex-shrink: 0;
  font-size: 12px;
  height: 32px;
  line-height: 32px;
  padding: 0 16px;
  text-align: center;
}
</style>

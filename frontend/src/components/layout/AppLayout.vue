<template>
  <div class="app-layout">
    <SideMenu :active-key="activeKey" :collapsed="collapsed" @navigate="go" />
    <div class="app-main">
      <TopHeader :collapsed="collapsed" @navigate="go" @toggle-collapse="collapsed = !collapsed" />
      <!-- 定高 flex 链:导图编辑器依赖容器有真实尺寸(教训⑦);滚动交给内容区自身 -->
      <main class="app-content">
        <!-- 重挂键按项目 id 派生:项目间直达(参数变化)强制重挂防 stale,
             项目内子路由切换(Task 3)仅换功能段,壳与已加载数据不复位 -->
        <router-view :key="viewKey" />
      </main>
      <footer class="app-footer">轻测试 LightTester · Powered by Vue3 + FastAPI</footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SideMenu from './SideMenu.vue'
import TopHeader from './TopHeader.vue'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

// 活跃键由路由派生(单一事实源):项目路由 project-<id>(Task 4 升级为含功能段),其余=home
const activeKey = computed(() => (route.params.id ? `project-${route.params.id}` : 'home'))
// 同 activeKey 语义:项目内切换保持实例,项目间/首页切换重挂
const viewKey = computed(() => (route.params.id ? `project-${route.params.id}` : route.path))

function go(path: string): void {
  if (route.fullPath !== path) void router.push(path)
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

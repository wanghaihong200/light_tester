import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    // 登录页在布局壳路由外(不套 SideMenu/TopHeader)
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/',
      component: () => import('../components/layout/AppLayout.vue'),
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('../views/HomeView.vue'),
        },
        {
          path: 'projects/:id',
          component: () => import('../views/ProjectView.vue'),
          children: [
            // 默认功能段:功能用例管理(切换项目永远落这里,ADR-0007)
            { path: '', redirect: (to) => ({ name: 'project-cases', params: to.params }) },
            { path: 'cases', name: 'project-cases', component: () => import('../components/MindmapPane.vue') },
            { path: 'knowledge', name: 'project-knowledge', component: () => import('../components/DocumentsPane.vue') },
            { path: 'ai/jobs', name: 'project-ai-jobs', component: () => import('../components/JobsPane.vue') },
            { path: 'ai/repo', name: 'project-ai-repo', component: () => import('../components/RepoPane.vue') },
            { path: 'ai/cross', name: 'project-ai-cross', component: () => import('../components/crossauto/CrossAutoPane.vue') },
            { path: 'ui/web', name: 'project-ui-web', component: () => import('../components/webauto/WebAutoPane.vue') },
            { path: 'ui/app', name: 'project-ui-app', component: () => import('../components/appauto/AppAutoPane.vue') },
            { path: 'mock/http', name: 'project-mock-http', component: () => import('../components/mock/MockPane.vue') },
            { path: 'perf/app', name: 'project-perf-app', component: () => import('../components/perf/PerfRecordPane.vue') },
          ],
        },
        {
          path: 'users',
          name: 'users',
          component: () => import('../views/UsersView.vue'),
          meta: { requiresAdmin: true },
        },
      ],
    },
  ],
})

// 未登录访问受保护路由 → 踢到 /login;登录页自身放行(防循环)
router.beforeEach((to) => {
  if (to.name === 'login') return true
  if (!localStorage.getItem('tt_token')) return { name: 'login' }
  // requiresAdmin 第一层:user 已加载且非 admin → 同步拦回首页。刷新直达时 fetchMe 尚未返回、
  // user 为空无法判定,此处不放异步守卫(避免 admin 被误踢),放行交由 UsersView 自检兜底
  const { user } = useAuth()
  if (to.meta.requiresAdmin && user.value && !user.value.is_admin) return { name: 'home' }
  return true
})

export default router

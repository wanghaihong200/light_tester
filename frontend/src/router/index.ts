import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    // 登录页在布局壳路由外(不套 SideMenu/TopHeader/TabBar)
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
          name: 'project-detail',
          component: () => import('../views/ProjectView.vue'),
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

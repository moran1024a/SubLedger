import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/ForbiddenView.vue'),
    meta: { public: true, title: '无权访问' },
  },
  {
    path: '/404',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { public: true, title: '页面不存在' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true, roles: ['user'] },
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/HomeView.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'plans',
        name: 'plans',
        component: () => import('@/views/plans/PlansListView.vue'),
        meta: { title: '账单规则' },
      },
      {
        path: 'plans/new',
        name: 'plan-new',
        component: () => import('@/views/plans/PlanFormView.vue'),
        meta: { title: '新建账单规则' },
      },
      {
        path: 'plans/:id',
        name: 'plan-detail',
        component: () => import('@/views/plans/PlanDetailView.vue'),
        meta: { title: '账单规则详情' },
      },
      {
        path: 'bills',
        name: 'bills',
        component: () => import('@/views/bills/BillsView.vue'),
        meta: { title: '账单记录' },
      },
      {
        path: 'settings/notifications',
        name: 'notifications',
        component: () => import('@/views/settings/NotificationsView.vue'),
        meta: { title: '通知设置' },
      },
      {
        path: 'logs',
        name: 'my-logs',
        component: () => import('@/views/logs/MyLogsView.vue'),
        meta: { title: '我的日志' },
      },
    ],
  },
  {
    path: '/settings/profile',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true, roles: ['user', 'admin'] },
    children: [
      {
        path: '',
        name: 'profile',
        component: () => import('@/views/settings/ProfileView.vue'),
        meta: { title: '个人设置' },
      },
    ],
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true, roles: ['admin'] },
    children: [
      {
        path: '',
        name: 'admin-home',
        component: () => import('@/views/admin/AdminHomeView.vue'),
        meta: { title: '管理首页' },
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/UsersView.vue'),
        meta: { title: '用户管理' },
      },
      {
        path: 'users/:id',
        name: 'admin-user-detail',
        component: () => import('@/views/admin/UserDetailView.vue'),
        meta: { title: '用户详情' },
      },
      {
        path: 'logs/system',
        name: 'admin-system-logs',
        component: () => import('@/views/admin/SystemLogsView.vue'),
        meta: { title: '系统日志' },
      },
      {
        path: 'logs/users',
        name: 'admin-user-logs',
        component: () => import('@/views/admin/UserLogsView.vue'),
        meta: { title: '用户日志' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/404' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (to, from, saved) => {
    // Wait for the out-in page transition to finish leaving before restoring a saved position.
    if (saved) return new Promise((resolve) => setTimeout(() => resolve(saved), 160))
    return to.path === from.path ? false : { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.initialized) {
    try {
      await auth.initialize()
    } catch {
      return true // App renders a retry screen until authentication can be checked.
    }
  }
  if (to.meta.public) {
    if (to.name === 'login' && auth.user) return auth.isAdmin ? '/admin' : '/'
    return true
  }
  if (!auth.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.path === '/' && auth.isAdmin) return '/admin'
  const roles = to.meta.roles as string[] | undefined
  if (roles && !roles.includes(auth.isAdmin ? 'admin' : 'user')) return { name: 'forbidden' }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title ?? 'SubLedger'} · 订阅本`
})

export default router

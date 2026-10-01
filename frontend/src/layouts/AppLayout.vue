<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/message/style/css'

import { ElButton, ElDrawer } from 'element-plus'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { confirmDiscardChanges } from '@/composables/useUnsavedChanges'

const auth = useAuthStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const loggingOut = ref(false)
const admin = computed(() => auth.isAdmin)
const menu = computed(() =>
  admin.value
    ? [
        { path: '/admin', label: '管理首页' },
        { path: '/admin/users', label: '用户管理' },
        { path: '/admin/logs/system', label: '系统日志' },
        { path: '/admin/logs/users', label: '用户日志' },
        { path: '/settings/profile', label: '个人设置' },
      ]
    : [
        { path: '/', label: '首页' },
        { path: '/plans', label: '账单规则' },
        { path: '/bills', label: '账单记录' },
        { path: '/settings/notifications', label: '通知设置' },
        { path: '/settings/profile', label: '个人设置' },
        { path: '/logs', label: '我的日志' },
      ],
)
function isMenuActive(path: string) {
  if (path === '/' || path === '/admin') return route.path === path
  return route.path === path || route.path.startsWith(`${path}/`)
}

async function logout() {
  if (loggingOut.value) return
  if (!confirmDiscardChanges()) return
  loggingOut.value = true
  try {
    await auth.logout()
  } catch {
    ElMessage.error('退出请求失败，本地登录状态已清除')
  } finally {
    auth.clear()
    await router.replace('/login')
    loggingOut.value = false
  }
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ collapsed: ui.sidebarCollapsed }">
      <div class="brand">
        {{ ui.sidebarCollapsed ? '订' : '订阅本'
        }}<small v-if="!ui.sidebarCollapsed">SubLedger</small>
      </div>
      <nav aria-label="主导航">
        <router-link
          v-for="item in menu"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isMenuActive(item.path) }"
          @click="ui.mobileMenuOpen = false"
          >{{ item.label }}</router-link
        >
      </nav>
      <button
        class="collapse-button"
        type="button"
        :aria-label="ui.sidebarCollapsed ? '展开导航' : '折叠导航'"
        @click="ui.sidebarCollapsed = !ui.sidebarCollapsed"
      >
        {{ ui.sidebarCollapsed ? '›' : '‹' }}
      </button>
    </aside>
    <el-drawer v-model="ui.mobileMenuOpen" title="导航" direction="ltr" size="280px">
      <nav aria-label="移动端主导航" class="mobile-nav">
        <router-link
          v-for="item in menu"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isMenuActive(item.path) }"
          @click="ui.mobileMenuOpen = false"
          >{{ item.label }}</router-link
        >
      </nav>
    </el-drawer>
    <section class="app-main">
      <header class="topbar">
        <button
          type="button"
          class="mobile-menu-button"
          aria-label="打开导航"
          @click="ui.mobileMenuOpen = true"
        >
          ☰
        </button>
        <div class="topbar-title">{{ route.meta.title || 'SubLedger' }}</div>
        <div class="topbar-user">
          <span>{{ auth.user?.username }}</span
          ><el-button text @click="router.push('/settings/profile')">个人设置</el-button
          ><el-button text :loading="loggingOut" @click="logout">退出</el-button>
        </div>
      </header>
      <main><router-view /></main>
    </section>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 220px;
  background: #182230;
  color: #dbe5ef;
  padding: 20px 12px;
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
}
.sidebar.collapsed {
  width: 72px;
}
.brand {
  font-size: 20px;
  font-weight: 700;
  padding: 4px 12px 24px;
  color: white;
  white-space: nowrap;
  overflow: hidden;
}
.brand small {
  display: block;
  margin-top: 2px;
  color: #9fb0c2;
  font-size: 11px;
  font-weight: 500;
}
.nav-item {
  display: block;
  padding: 11px 12px;
  border-radius: 6px;
  margin-bottom: 4px;
  color: #c8d3df;
}
.nav-item:hover,
.nav-item.active {
  background: #2d4b69;
  color: white;
}
.collapse-button {
  margin-top: auto;
  color: white;
  background: transparent;
  border: 1px solid #52677d;
  border-radius: 4px;
  padding: 5px;
  cursor: pointer;
}
.app-main {
  flex: 1;
  min-width: 0;
}
.topbar {
  height: 64px;
  background: white;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 16px;
}
.topbar-title {
  font-weight: 600;
  flex: 1;
}
.topbar-user {
  display: flex;
  align-items: center;
  gap: 12px;
}
.mobile-menu-button {
  display: none;
  border: 0;
  background: none;
  font-size: 20px;
}
.mobile-nav .nav-item {
  color: #374151;
}
@media (max-width: 700px) {
  .sidebar {
    display: none;
  }
  .mobile-menu-button {
    display: block;
  }
  .topbar {
    padding: 0 16px;
  }
  .topbar-user {
    gap: 4px;
  }
  .topbar-user span {
    display: none;
  }
}
</style>

<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/message/style/css'

import { ElButton, ElDrawer } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { confirmDiscardChanges } from '@/composables/useUnsavedChanges'
import NavIcon from '@/components/common/NavIcon.vue'

const auth = useAuthStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const loggingOut = ref(false)
const mobileMenuButton = ref<HTMLElement | null>(null)
const mobileNav = ref<HTMLElement | null>(null)
const mobileNavRendered = ref(false)
const mainArea = ref<HTMLElement | null>(null)
const admin = computed(() => auth.isAdmin)
const userInitial = computed(() => {
  const name = auth.user?.username?.trim() ?? ''
  return name ? [...name][0]!.toUpperCase() : '?'
})
const menu = computed(() =>
  admin.value
    ? [
        { path: '/admin', label: '管理首页', icon: 'home' },
        { path: '/admin/users', label: '用户管理', icon: 'users' },
        { path: '/admin/logs/system', label: '系统日志', icon: 'logs' },
        { path: '/admin/logs/users', label: '用户日志', icon: 'users' },
        { path: '/settings/profile', label: '个人设置', icon: 'settings' },
      ]
    : [
        { path: '/', label: '首页', icon: 'home' },
        { path: '/plans', label: '账单规则', icon: 'calendar' },
        { path: '/bills', label: '账单记录', icon: 'bills' },
        { path: '/settings/notifications', label: '通知设置', icon: 'bell' },
        { path: '/settings/profile', label: '个人设置', icon: 'settings' },
        { path: '/logs', label: '我的日志', icon: 'logs' },
      ],
)
function isMenuActive(path: string) {
  if (path === '/' || path === '/admin') return route.path === path
  return route.path === path || route.path.startsWith(`${path}/`)
}
// Set when the drawer closes because of navigation; focus then stays with the new page.
let closedByRoute = false
watch(
  () => route.path,
  () => {
    if (ui.mobileMenuOpen) closedByRoute = true
    ui.mobileMenuOpen = false
  },
)
// The drawer renders its content lazily, so the id is only referenced once it exists.
watch(
  () => ui.mobileMenuOpen,
  (open) => {
    if (open) mobileNavRendered.value = true
  },
)
function onMenuClick(path: string) {
  if (route.path === path) ui.mobileMenuOpen = false
}
function onMobileNavClosed() {
  if (!closedByRoute) mobileMenuButton.value?.focus()
  closedByRoute = false
}
function focusMobileNavigation() {
  const target =
    mobileNav.value?.querySelector<HTMLElement>('[aria-current="page"]') ??
    mobileNav.value?.querySelector<HTMLElement>('a')
  target?.focus()
}

// Only a real page change moves focus; query-only updates keep the current element.
let focusedPath = route.path
function onPageEntered() {
  if (focusedPath === route.path) return
  focusedPath = route.path
  mainArea.value?.querySelector<HTMLElement>('h1[tabindex="-1"]')?.focus({ preventScroll: true })
}

async function logout() {
  if (loggingOut.value) return
  loggingOut.value = true
  const version = auth.sessionVersion
  try {
    if (!(await confirmDiscardChanges())) return
    if (auth.sessionVersion !== version) return
    try {
      await auth.logout()
    } catch {
      // A failed logout keeps the server session, so the user stays signed in.
      if (auth.sessionVersion === version) ElMessage.error('退出失败，请重试')
      return
    }
    if (auth.sessionVersion === version + 1 && !auth.user) await router.replace('/login')
  } finally {
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
      <nav id="desktop-navigation" aria-label="主导航">
        <router-link
          v-for="item in menu"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isMenuActive(item.path) }"
          :aria-label="item.label"
          :aria-current="isMenuActive(item.path) ? 'page' : undefined"
          @click="onMenuClick(item.path)"
        >
          <NavIcon :name="item.icon" />
          <span class="nav-label" :class="{ 'sr-only': ui.sidebarCollapsed }">{{
            item.label
          }}</span>
          <span v-if="ui.sidebarCollapsed" class="nav-tooltip" role="tooltip">{{
            item.label
          }}</span>
        </router-link>
      </nav>
      <button
        class="collapse-button"
        type="button"
        :aria-label="ui.sidebarCollapsed ? '展开导航' : '折叠导航'"
        :aria-expanded="!ui.sidebarCollapsed"
        aria-controls="desktop-navigation"
        @click="ui.sidebarCollapsed = !ui.sidebarCollapsed"
      >
        <NavIcon name="chevron" :class="{ 'chevron-expanded': ui.sidebarCollapsed }" />
      </button>
    </aside>
    <el-drawer
      v-model="ui.mobileMenuOpen"
      title="导航"
      direction="ltr"
      size="min(280px, 100vw)"
      @opened="focusMobileNavigation"
      @closed="onMobileNavClosed"
    >
      <nav id="mobile-navigation" ref="mobileNav" aria-label="移动端主导航" class="mobile-nav">
        <router-link
          v-for="item in menu"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isMenuActive(item.path) }"
          :aria-current="isMenuActive(item.path) ? 'page' : undefined"
          @click="onMenuClick(item.path)"
          ><NavIcon :name="item.icon" /><span class="nav-label">{{ item.label }}</span></router-link
        >
      </nav>
    </el-drawer>
    <section class="app-main">
      <header class="topbar">
        <button
          type="button"
          ref="mobileMenuButton"
          class="mobile-menu-button"
          aria-label="打开导航"
          :aria-controls="mobileNavRendered ? 'mobile-navigation' : undefined"
          :aria-expanded="ui.mobileMenuOpen"
          @click="ui.mobileMenuOpen = true"
        >
          <NavIcon name="menu" />
        </button>
        <div class="topbar-title">{{ route.meta.title || 'SubLedger' }}</div>
        <div class="topbar-user">
          <button
            type="button"
            class="user-button"
            :aria-label="`${auth.user?.username ?? ''} 的个人设置`"
            @click="router.push('/settings/profile')"
          >
            <span class="user-avatar" aria-hidden="true">{{ userInitial }}</span>
            <span class="user-name">{{ auth.user?.username }}</span>
          </button>
          <el-button text :loading="loggingOut" @click="logout">退出</el-button>
        </div>
      </header>
      <main ref="mainArea">
        <router-view v-slot="{ Component }">
          <Transition name="page" mode="out-in" @after-enter="onPageEntered">
            <component :is="Component" :key="route.path" />
          </Transition>
        </router-view>
      </main>
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
  flex-shrink: 0;
  background: var(--sl-sidebar);
  color: var(--sl-sidebar-text);
  padding: var(--sl-space-5) var(--sl-space-3);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  align-self: flex-start;
  transition: width var(--sl-duration-base) var(--sl-ease);
}
.sidebar.collapsed {
  width: 72px;
}
.sidebar nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.sidebar.collapsed nav {
  overflow: visible;
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
  position: relative;
  display: flex;
  align-items: center;
  min-height: 44px;
  gap: var(--sl-space-3);
  padding: var(--sl-space-3);
  border-radius: var(--sl-radius);
  margin-bottom: var(--sl-space-1);
  color: var(--sl-sidebar-text);
  transition:
    background var(--sl-duration-fast) var(--sl-ease),
    color var(--sl-duration-fast) var(--sl-ease);
}
.nav-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 3px;
  background: var(--sl-sidebar-indicator);
  transform: scaleY(0);
  transition: transform 160ms var(--sl-ease-out);
}
.nav-item.active::before {
  transform: scaleY(1);
}
.nav-item:hover,
.nav-item:focus-visible,
.nav-item.active {
  background: var(--sl-sidebar-active);
  color: white;
}
.sidebar .nav-item:focus-visible,
.collapse-button:focus-visible {
  outline-color: var(--sl-sidebar-indicator);
}
.nav-label {
  min-width: 0;
  overflow-wrap: anywhere;
}
.collapsed .nav-item {
  justify-content: center;
  padding-inline: 0;
}
.nav-tooltip {
  position: absolute;
  left: calc(100% + var(--sl-space-2));
  top: 50%;
  transform: translateY(-50%);
  padding: var(--sl-space-2) var(--sl-space-3);
  border-radius: var(--sl-radius-sm);
  background: #16202e;
  color: white;
  white-space: nowrap;
  visibility: hidden;
  pointer-events: none;
  z-index: 10;
  box-shadow: var(--sl-shadow-2);
}
.nav-item:hover .nav-tooltip,
.nav-item:focus-visible .nav-tooltip {
  visibility: visible;
}
.collapse-button {
  flex-shrink: 0;
  margin-top: var(--sl-space-3);
  color: white;
  background: transparent;
  border: 1px solid #52677d;
  border-radius: var(--sl-radius-sm);
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sl-space-2);
  cursor: pointer;
}
.chevron-expanded {
  transform: rotate(180deg);
}
.app-main {
  flex: 1;
  min-width: 0;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  min-height: 64px;
  background: var(--sl-surface);
  border-bottom: 1px solid var(--sl-border);
  display: flex;
  align-items: center;
  padding: var(--sl-space-2) var(--sl-space-6);
  gap: var(--sl-space-4);
}
.topbar-title {
  font-weight: 600;
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.topbar-user {
  display: flex;
  align-items: center;
  gap: var(--sl-space-3);
  min-width: 0;
}
.user-button {
  display: flex;
  align-items: center;
  gap: var(--sl-space-2);
  min-width: 0;
  padding: 4px var(--sl-space-2) 4px 4px;
  border: 0;
  border-radius: 999px;
  background: none;
  color: var(--sl-text);
  cursor: pointer;
  transition: background var(--sl-duration-fast) var(--sl-ease);
}
.user-button:hover {
  background: var(--sl-surface-muted);
}
.user-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--sl-primary-soft);
  color: var(--sl-primary-text);
  font-weight: 600;
}
.user-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.topbar-user .el-button + .el-button {
  margin-left: 0;
}
.mobile-menu-button {
  display: none;
  border: 0;
  background: none;
  font-size: 20px;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  padding: 10px;
  border-radius: var(--sl-radius-sm);
  color: var(--sl-text);
  cursor: pointer;
}
.mobile-nav .nav-item {
  color: var(--sl-text);
}
.mobile-nav .nav-item::before {
  background: var(--sl-primary);
}
.mobile-nav .nav-item:hover,
.mobile-nav .nav-item:focus-visible,
.mobile-nav .nav-item.active {
  background: var(--sl-primary-soft);
  color: var(--sl-primary);
}
@media (max-width: 700px) {
  .sidebar {
    display: none;
  }
  .mobile-menu-button {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .topbar {
    padding: var(--sl-space-2) var(--sl-space-4);
    gap: var(--sl-space-2);
  }
  .topbar-user {
    gap: 4px;
  }
  .user-name {
    display: none;
  }
  .user-button {
    padding: 0;
  }
  .topbar-user :deep(.el-button) {
    padding-inline: var(--sl-space-2);
  }
}
</style>

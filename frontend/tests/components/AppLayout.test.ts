import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { reactive } from 'vue'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { confirmDiscardChanges } from '@/composables/useUnsavedChanges'
import { ElMessage } from 'element-plus'

const route = reactive({ path: '/admin/users', meta: { title: '用户管理' } })
const replace = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, push: vi.fn() }),
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { error: vi.fn() },
}))
vi.mock('@/composables/useUnsavedChanges', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/composables/useUnsavedChanges')>()),
  confirmDiscardChanges: vi.fn(),
}))

function mountLayout(attachTo?: HTMLElement) {
  return shallowMount(AppLayout, {
    attachTo,
    global: {
      stubs: {
        NavIcon: false,
        RouterLink: { props: ['to'], template: '<a :href="to" @click.prevent><slot /></a>' },
        RouterView: true,
        'el-drawer': { name: 'DrawerStub', template: '<div><slot /></div>' },
        'el-button': {
          props: ['loading'],
          template: '<button :disabled="loading"><slot /></button>',
        },
      },
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  route.path = '/admin/users'
  replace.mockResolvedValue(undefined)
  vi.mocked(confirmDiscardChanges).mockResolvedValue(true)
  setActivePinia(createPinia())
  useAuthStore().setUser({
    id: 0,
    username: 'admin',
    role: 'admin',
    is_active: true,
    timezone: 'UTC',
    currency_code: 'CNY',
    created_at: '',
    updated_at: '',
  })
})

describe('AppLayout', () => {
  it('renders the Chinese brand, route title, and exact admin menu state', () => {
    const wrapper = mountLayout()
    const vm = wrapper.vm as unknown as { isMenuActive: (path: string) => boolean }

    expect(wrapper.text()).toContain('订阅本')
    expect(wrapper.text()).toContain('用户管理')
    expect(wrapper.text()).toContain('个人设置')
    expect(vm.isMenuActive('/admin')).toBe(false)
    expect(vm.isMenuActive('/admin/users')).toBe(true)
    expect(wrapper.get('#desktop-navigation .active').attributes('aria-current')).toBe('page')
    expect(wrapper.get('#desktop-navigation a').attributes('aria-current')).toBeUndefined()
  })

  it('keeps icons, visible tooltip content, and accessible labels when collapsed', async () => {
    const wrapper = mountLayout()
    await wrapper.get('.collapse-button').trigger('click')

    expect(useUiStore().sidebarCollapsed).toBe(true)
    const links = wrapper.findAll('#desktop-navigation a')
    expect(links).toHaveLength(5)
    for (const link of links) {
      expect(link.get('svg').attributes('aria-hidden')).toBe('true')
      expect(link.get('.nav-label').classes()).toContain('sr-only')
      expect(link.get('[role="tooltip"]').text()).toBe(link.attributes('aria-label'))
    }
    expect(wrapper.get('.collapse-button').attributes('aria-expanded')).toBe('false')
  })

  it('focuses the active mobile link and closes after successful navigation', async () => {
    const wrapper = mountLayout(document.body)
    const button = wrapper.get('.mobile-menu-button')
    await button.trigger('click')
    expect(button.attributes('aria-expanded')).toBe('true')
    wrapper.findComponent({ name: 'DrawerStub' }).vm.$emit('opened')
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('#mobile-navigation .active').element)

    await wrapper.get('#mobile-navigation a[href="/admin/logs/system"]').trigger('click')
    expect(useUiStore().mobileMenuOpen).toBe(true)
    route.path = '/admin/logs/system'
    await flushPromises()
    expect(useUiStore().mobileMenuOpen).toBe(false)
    expect(wrapper.get('#mobile-navigation .active').attributes('href')).toBe('/admin/logs/system')
    wrapper.findComponent({ name: 'DrawerStub' }).vm.$emit('closed')
    expect(document.activeElement).toBe(button.element)
  })

  it('awaits the discard confirmation, prevents repeated requests, and preserves a cancelled session', async () => {
    const wrapper = mountLayout()
    const auth = useAuthStore()
    const logout = vi.spyOn(auth, 'logout').mockResolvedValue(undefined)
    const clear = vi.spyOn(auth, 'clear')
    let resolve!: (value: boolean) => void
    vi.mocked(confirmDiscardChanges).mockReturnValueOnce(
      new Promise((done) => {
        resolve = done
      }),
    )
    const vm = wrapper.vm as unknown as { logout: () => Promise<void>; loggingOut: boolean }
    const first = vm.logout()
    await vm.logout()

    expect(confirmDiscardChanges).toHaveBeenCalledOnce()
    expect(vm.loggingOut).toBe(true)
    expect(logout).not.toHaveBeenCalled()
    resolve(false)
    await first
    expect(vm.loggingOut).toBe(false)
    expect(clear).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
    expect(auth.user?.username).toBe('admin')
  })

  it('clears the session and navigates only after confirmation and logout', async () => {
    const wrapper = mountLayout()
    const auth = useAuthStore()
    const logout = vi.spyOn(auth, 'logout').mockImplementation(async () => {
      auth.clear()
    })
    const vm = wrapper.vm as unknown as { logout: () => Promise<void> }
    await vm.logout()

    expect(confirmDiscardChanges).toHaveBeenCalledOnce()
    expect(logout).toHaveBeenCalledOnce()
    expect(auth.user).toBeNull()
    expect(replace).toHaveBeenCalledWith('/login')
  })

  it('keeps the local session cleared when the logout request fails', async () => {
    const wrapper = mountLayout()
    const auth = useAuthStore()
    vi.spyOn(auth, 'logout').mockImplementation(async () => {
      auth.clear()
      throw new Error('network failure')
    })
    const vm = wrapper.vm as unknown as { logout: () => Promise<void>; loggingOut: boolean }
    await vm.logout()

    expect(auth.user).toBeNull()
    expect(replace).toHaveBeenCalledWith('/login')
    expect(vm.loggingOut).toBe(false)
    expect(ElMessage.error).toHaveBeenCalledWith('退出请求失败，本地登录状态已清除')
  })

  it('does not redirect or clear a new session after the old logout resolves', async () => {
    const wrapper = mountLayout()
    const auth = useAuthStore()
    const member = { ...auth.user!, id: 2, username: 'other', role: 'user' as const }
    let complete!: () => void
    vi.spyOn(auth, 'logout').mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      }),
    )
    const leaving = (wrapper.vm as unknown as { logout: () => Promise<void> }).logout()
    await flushPromises()
    auth.clear()
    auth.setUser(member)
    complete()
    await leaving
    expect(auth.user?.id).toBe(2)
    expect(replace).not.toHaveBeenCalled()
  })
})

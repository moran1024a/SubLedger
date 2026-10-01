import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const route = { path: '/admin/users', meta: { title: '用户管理' } }
const replace = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, push: vi.fn() }),
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { error: vi.fn() },
}))

beforeEach(() => {
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
    const wrapper = shallowMount(AppLayout, {
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a><slot /></a>' },
          RouterView: true,
          'el-drawer': { template: '<div><slot /></div>' },
          'el-button': { template: '<button><slot /></button>' },
        },
      },
    })
    const vm = wrapper.vm as unknown as { isMenuActive: (path: string) => boolean }

    expect(wrapper.text()).toContain('订阅本')
    expect(wrapper.text()).toContain('用户管理')
    expect(wrapper.text()).toContain('个人设置')
    expect(vm.isMenuActive('/admin')).toBe(false)
    expect(vm.isMenuActive('/admin/users')).toBe(true)
  })
})

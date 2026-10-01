import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import LoginView from '@/views/LoginView.vue'
import * as authApi from '@/api/auth'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query: {} }),
}))
vi.mock('@/api/auth', () => ({ login: vi.fn(), getCurrentUser: vi.fn(), logout: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn() } }))

beforeEach(() => {
  setActivePinia(createPinia())
  push.mockReset()
  vi.clearAllMocks()
})

describe('LoginView', () => {
  it('logs in using the returned current user and follows the role home', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      id: 0,
      username: 'admin',
      role: 'admin',
      is_active: true,
      timezone: 'UTC',
      currency_code: 'CNY',
      created_at: '',
      updated_at: '',
    })
    const wrapper = shallowMount(LoginView, {
      global: {
        stubs: {
          'el-card': { template: '<div><slot /></div>' },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<label><slot /></label>' },
          'el-input': true,
          'el-alert': true,
          'el-button': true,
        },
      },
    })

    Object.assign(wrapper.vm as unknown as { username: string; password: string }, {
      username: 'admin',
      password: 'password',
    })
    await (wrapper.vm as unknown as { submit: () => Promise<void> }).submit()

    expect(authApi.login).toHaveBeenCalledWith('admin', 'password')
    expect(authApi.getCurrentUser).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/admin')
  })
})

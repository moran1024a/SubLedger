import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'
import LoginView from '@/views/LoginView.vue'
import * as authApi from '@/api/auth'
import { ApiError } from '@/types/api'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query: {} }),
}))
vi.mock('@/api/auth', () => ({ login: vi.fn(), getCurrentUser: vi.fn(), logout: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { error: vi.fn() },
}))

beforeEach(() => {
  setActivePinia(createPinia())
  push.mockReset()
  vi.clearAllMocks()
})

describe('LoginView', () => {
  it.each([500, 502, 503, 504])(
    'reports service error %i without clearing the password',
    async (status) => {
      vi.mocked(authApi.login).mockRejectedValue(
        new ApiError({ status, code: 'INTERNAL_ERROR', message: 'failed' }),
      )
      const wrapper = shallowMount(LoginView)
      const vm = wrapper.vm as unknown as {
        username: string
        password: string
        error: string
        submit: () => Promise<void>
      }
      vm.username = 'user'
      vm.password = 'password'
      await vm.submit()
      expect(vm.error).toContain('服务暂时不可用')
      expect(vm.password).toBe('password')
      expect(push).not.toHaveBeenCalled()
    },
  )

  it('submits once and ignores late navigation after the page is gone', async () => {
    let complete!: (value: Awaited<ReturnType<typeof authApi.login>>) => void
    vi.mocked(authApi.login).mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      }),
    )
    const wrapper = shallowMount(LoginView)
    const vm = wrapper.vm as unknown as {
      username: string
      password: string
      submit: () => Promise<void>
    }
    vm.username = 'user'
    vm.password = 'password'
    const first = vm.submit()
    await vm.submit()
    expect(authApi.login).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    complete({
      id: 1,
      username: 'user',
      role: 'user',
      is_active: true,
      timezone: 'UTC',
      currency_code: 'CNY',
      created_at: '',
      updated_at: '',
    })
    await first
    expect(push).not.toHaveBeenCalled()
  })
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

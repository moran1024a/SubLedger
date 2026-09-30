import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ApiError } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'

vi.mock('@/api/auth', () => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}))

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('auth store', () => {
  it('treats an already-invalid remote session as a completed logout', async () => {
    vi.mocked(authApi.logout).mockRejectedValue(
      new ApiError({ status: 401, code: 'AUTH_SESSION_INVALID', message: '会话失效' }),
    )
    const auth = useAuthStore()
    auth.setUser({
      id: 1,
      username: 'user',
      role: 'user',
      is_active: true,
      timezone: 'UTC',
      currency_code: 'CNY',
      created_at: '',
      updated_at: '',
    })

    await expect(auth.logout()).resolves.toBeUndefined()
    expect(auth.user).toBeNull()
    expect(auth.initialized).toBe(true)
  })

  it('clears local state even when logout fails for another reason', async () => {
    vi.mocked(authApi.logout).mockRejectedValue(new Error('offline'))
    const auth = useAuthStore()
    auth.setUser({
      id: 1,
      username: 'user',
      role: 'user',
      is_active: true,
      timezone: 'UTC',
      currency_code: 'CNY',
      created_at: '',
      updated_at: '',
    })

    await expect(auth.logout()).rejects.toThrow('offline')
    expect(auth.user).toBeNull()
  })
})

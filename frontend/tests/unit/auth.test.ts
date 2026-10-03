import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ApiError } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import type { CurrentUser } from '@/types/api'

const member: CurrentUser = {
  id: 1,
  username: 'member',
  role: 'user',
  is_active: true,
  timezone: 'UTC',
  currency_code: 'CNY',
  created_at: '',
  updated_at: '',
}

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
  it('does not clear a new login when an old logout finishes later', async () => {
    let complete!: () => void
    vi.mocked(authApi.logout).mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      }),
    )
    const auth = useAuthStore()
    auth.setUser(member)
    const leaving = auth.logout()
    auth.clear()
    vi.mocked(authApi.login).mockResolvedValue({ ...member, id: 2, username: 'other' })
    await auth.login('other', 'password')
    complete()
    await leaving
    expect(auth.user?.id).toBe(2)
  })
  it('rejects a profile response that arrives after logout or another login', async () => {
    const auth = useAuthStore()
    auth.setUser(member)
    const version = auth.sessionVersion
    auth.clear()
    expect(auth.setUser({ ...member, username: 'late' }, version)).toBe(false)
    expect(auth.user).toBeNull()
    vi.mocked(authApi.login).mockResolvedValue({ ...member, id: 2, username: 'other' })
    await auth.login('other', 'password')
    expect(auth.setUser(member, version)).toBe(false)
    expect(auth.user?.id).toBe(2)
  })

  it('does not restore an invalidated in-flight login', async () => {
    let complete!: (user: CurrentUser) => void
    vi.mocked(authApi.login).mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      }),
    )
    const auth = useAuthStore()
    const pending = auth.login('member', 'password')
    auth.clear()
    complete(member)
    expect(await pending).toBe(false)
    expect(auth.user).toBeNull()
  })
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

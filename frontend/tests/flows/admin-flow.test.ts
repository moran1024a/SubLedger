import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { login as loginRequest } from '@/api/auth'
import {
  createUser,
  disableUser,
  enableUser,
  getHealth,
  resetUserPassword,
  updateUser,
} from '@/api/users'
import { getSystemLogs, getUserLogs } from '@/api/logs'
import { setForbiddenHandler, setUnauthorizedHandler } from '@/api/client'

const admin = {
  id: 0,
  username: 'admin',
  role: 'admin' as const,
  is_active: true,
  timezone: 'UTC',
  currency_code: 'CNY',
  created_at: '',
  updated_at: '',
}
const member = { ...admin, id: 1, username: 'member', role: 'user' as const }
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  setUnauthorizedHandler(() => {})
  setForbiddenHandler(() => {})
})

describe('administrator flow', () => {
  it('covers user lifecycle, logs, and degraded health', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = init?.method ?? 'GET'
        calls.push(`${method} ${url}`)
        if (url.endsWith('/auth/login')) {
          const payload = JSON.parse(String(init?.body)) as { username: string }
          if (payload.username === 'member')
            return json({ code: 'AUTH_INVALID_CREDENTIALS', message: '用户名或密码错误' }, 401)
          return json(admin)
        }
        if (url.endsWith('/auth/me')) return json(admin)
        if (url.endsWith('/admin/users') && method === 'POST') return json(member, 201)
        if (url.endsWith('/admin/users/1') && method === 'PATCH')
          return json({ ...member, username: 'renamed' })
        if (url.endsWith('/admin/users/1/password')) return new Response(null, { status: 204 })
        if (url.endsWith('/admin/users/1/disable')) return new Response(null, { status: 204 })
        if (url.endsWith('/admin/users/1/enable')) return json(member)
        if (url.endsWith('/admin/users/1/logs')) return json([])
        if (url.endsWith('/admin/system-logs')) return json([])
        if (url === '/health')
          return json(
            { status: 'degraded', application: 'ok', database: 'error', scheduler: 'ok' },
            503,
          )
        throw new Error(`Unexpected request: ${method} ${url}`)
      }),
    )

    await useAuthStore().login('admin', 'password')
    const created = await createUser({ username: 'member', password: 'password' })
    await updateUser(created.id, { username: 'renamed' })
    await resetUserPassword(created.id, 'new-password')
    await disableUser(created.id)
    await expect(loginRequest('member', 'password')).rejects.toMatchObject({
      status: 401,
      code: 'AUTH_INVALID_CREDENTIALS',
    })
    await enableUser(created.id)
    await getUserLogs(created.id)
    await getSystemLogs()
    const health = await getHealth()

    expect(health.status).toBe('degraded')
    expect(calls).toEqual(
      expect.arrayContaining([
        'POST /api/v1/admin/users',
        'PATCH /api/v1/admin/users/1',
        'PUT /api/v1/admin/users/1/password',
        'POST /api/v1/admin/users/1/disable',
        'POST /api/v1/admin/users/1/enable',
        'GET /health',
      ]),
    )
  })
})

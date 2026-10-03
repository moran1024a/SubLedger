import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { RouteLocationNormalized } from 'vue-router'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import type { CurrentUser } from '@/types/api'

const user = (role: 'user' | 'admin'): CurrentUser => ({
  id: role === 'admin' ? 0 : 1,
  username: role,
  role,
  is_active: true,
  timezone: 'UTC',
  currency_code: 'CNY',
  created_at: '',
  updated_at: '',
})

beforeEach(async () => {
  setActivePinia(createPinia())
  const auth = useAuthStore()
  auth.clear()
  await router.replace('/login')
})

describe('route access', () => {
  it('redirects anonymous users to login with the target path', async () => {
    await router.push('/plans')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/plans')
  })

  it('redirects an admin root visit to the management home', async () => {
    useAuthStore().setUser(user('admin'))
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/admin')
  })

  it('sends role mismatches to the forbidden page', async () => {
    useAuthStore().setUser(user('user'))
    await router.push('/admin/users')
    expect(router.currentRoute.value.path).toBe('/403')
  })

  it('titles the document with the route and product name', async () => {
    useAuthStore().setUser(user('user'))
    await router.push('/plans')
    expect(document.title).toBe('账单规则 · 订阅本')
    await router.push('/404')
    expect(document.title).toBe('页面不存在 · 订阅本')
  })

  it('redirects authenticated users away from login', async () => {
    useAuthStore().setUser(user('user'))
    await router.push('/404')
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/')
  })
})

describe('scroll restoration', () => {
  it('restores a saved position only after the page leave transition', async () => {
    vi.useFakeTimers()
    try {
      const scroll = router.options.scrollBehavior!
      const at = (path: string) => router.resolve(path) as unknown as RouteLocationNormalized
      const to = at('/plans')
      const from = at('/bills')
      const saved = { left: 0, top: 320 }
      let restored: unknown = null
      void Promise.resolve(scroll(to, from, saved)).then((value) => {
        restored = value
      })
      await vi.advanceTimersByTimeAsync(100)
      expect(restored).toBeNull()
      await vi.advanceTimersByTimeAsync(100)
      expect(restored).toEqual(saved)
      expect(scroll(to, from, null)).toEqual({ top: 0 })
      expect(scroll(to, at('/plans?page=2'), null)).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})

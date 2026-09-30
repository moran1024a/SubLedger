import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
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

  it('redirects authenticated users away from login', async () => {
    useAuthStore().setUser(user('user'))
    await router.push('/404')
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/')
  })
})

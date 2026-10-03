import { request } from './client'
import type { CurrentUser } from '@/types/api'

export function login(username: string, password: string) {
  return request<CurrentUser>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    timeoutMs: 15000,
  })
}

export function getCurrentUser() {
  return request<CurrentUser>('/auth/me')
}

export function logout() {
  return request<void>('/auth/logout', { method: 'POST', timeoutMs: 10000 })
}

import { request, requestRoot } from './client'
import type { AdminSummary, CurrentUser, UserPage } from '@/types/api'

export function updateProfile(
  payload: Partial<Pick<CurrentUser, 'username' | 'timezone' | 'currency_code'>>,
) {
  return request<CurrentUser>('/me/profile', { method: 'PATCH', body: JSON.stringify(payload) })
}

export function changePassword(current_password: string, new_password: string) {
  return request<void>('/me/password', {
    method: 'PUT',
    body: JSON.stringify({ current_password, new_password }),
  })
}

export function listUsers(
  filters: { q?: string; is_active?: boolean; page?: number; page_size?: number } = {},
) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value))
  })
  return request<UserPage>(`/admin/users?${query.toString()}`)
}
export function getAdminSummary() {
  return request<AdminSummary>('/admin/summary')
}
export function getUser(id: number) {
  return request<CurrentUser>(`/admin/users/${id}`)
}
export function createUser(payload: {
  username: string
  password: string
  timezone?: string
  currency_code?: string
}) {
  return request<CurrentUser>('/admin/users', { method: 'POST', body: JSON.stringify(payload) })
}
export function updateUser(
  id: number,
  payload: Partial<Pick<CurrentUser, 'username' | 'timezone' | 'currency_code'>> & {
    revoke_sessions?: boolean
  },
) {
  return request<CurrentUser>(`/admin/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
export function resetUserPassword(id: number, password: string) {
  return request<void>(`/admin/users/${id}/password`, {
    method: 'PUT',
    body: JSON.stringify({ password }),
  })
}
export function disableUser(id: number) {
  return request<void>(`/admin/users/${id}/disable`, { method: 'POST' })
}
export function enableUser(id: number) {
  return request<CurrentUser>(`/admin/users/${id}/enable`, { method: 'POST' })
}

export function getHealth() {
  return requestRoot<import('@/types/api').HealthResponse>('/health', {}, [503])
}

import { request } from './client'
import type { NotificationPayload, NotificationSettings } from '@/types/api'

export function getNotificationSettings(signal?: AbortSignal) {
  return request<NotificationSettings>('/me/notification-settings', { signal })
}
export function saveNotificationSettings(payload: NotificationPayload) {
  return request<NotificationSettings>('/me/notification-settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}
export function testEmail() {
  return request<void>('/me/notification-settings/test-email', { method: 'POST' })
}
export function testFeishu() {
  return request<void>('/me/notification-settings/test-feishu', { method: 'POST' })
}

export interface NotificationFilters {
  channel?: 'email' | 'feishu'
  status?: import('@/types/api').NotificationStatus
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}
export function listNotificationRecords(filters: NotificationFilters = {}, signal?: AbortSignal) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value))
  })
  return request<import('@/types/api').NotificationRecordPage>(
    `/me/notification-records?${query}`,
    { signal },
  )
}

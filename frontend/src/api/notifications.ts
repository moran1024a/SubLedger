import { request } from './client'
import type { NotificationPayload, NotificationSettings } from '@/types/api'

export function getNotificationSettings() {
  return request<NotificationSettings>('/me/notification-settings')
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

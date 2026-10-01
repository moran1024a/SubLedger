import type { LocationQuery } from 'vue-router'
import type { NotificationFilters } from '@/api/notifications'
import type { NotificationStatus } from '@/types/api'
import { validDate } from './billFilters'
export const notificationLabels: Record<NotificationStatus, string> = {
  pending: '待处理',
  retry_wait: '等待重试',
  sent: '已发送',
  failed: '失败',
  unknown: '结果未知',
  expired: '已过提醒日期',
}
export function readNotificationQuery(
  query: LocationQuery,
): NotificationFilters & { page: number; page_size: number } {
  const text = (key: string) => (typeof query[key] === 'string' ? (query[key] as string) : '')
  const page = Number(text('page')),
    size = Number(text('page_size'))
  return {
    channel: ['email', 'feishu'].includes(text('channel'))
      ? (text('channel') as 'email' | 'feishu')
      : undefined,
    status: Object.hasOwn(notificationLabels, text('status'))
      ? (text('status') as NotificationStatus)
      : undefined,
    start_date: validDate(text('start_date')) ? text('start_date') : undefined,
    end_date: validDate(text('end_date')) ? text('end_date') : undefined,
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    page_size: [20, 50, 100].includes(size) ? size : 20,
  }
}

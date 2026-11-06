import { request } from './client'
import type { BillCalendarResponse } from '@/types/api'

export function getBillCalendar(month?: string, signal?: AbortSignal) {
  const query = month ? `?month=${encodeURIComponent(month)}` : ''
  return request<BillCalendarResponse>(`/bills/calendar${query}`, { signal })
}

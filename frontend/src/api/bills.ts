import { request } from './client'
import type { BillOccurrence, BillOccurrencePage, BillTimeStatus } from '@/types/api'

export interface BillFilters {
  q?: string
  sort?: 'asc' | 'desc'
  start_date?: string | null
  end_date?: string | null
  time_status?: BillTimeStatus
  is_valid?: boolean
  plan_id?: number
  page?: number
  page_size?: number
}

export function listBills(filters: BillFilters = {}, signal?: AbortSignal) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') query.set(key, String(value))
  })
  return request<BillOccurrencePage>(`/bills?${query.toString()}`, { signal })
}

export function updateBillValidity(id: number, isValid: boolean) {
  return request<BillOccurrence>(`/bills/${id}/validity`, {
    method: 'PATCH',
    body: JSON.stringify({ is_valid: isValid }),
  })
}

export function getBill(id: number, signal?: AbortSignal) {
  return request<BillOccurrence>(`/bills/${id}`, { signal })
}

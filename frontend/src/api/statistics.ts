import { request } from './client'
import type { StatisticsResponse } from '@/types/api'

export function getSummary(signal?: AbortSignal) {
  return request<StatisticsResponse>('/statistics/summary', { signal })
}

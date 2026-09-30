import { request } from './client'
import type { StatisticsResponse } from '@/types/api'

export function getSummary() {
  return request<StatisticsResponse>('/statistics/summary')
}

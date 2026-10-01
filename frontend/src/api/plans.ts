import { request } from './client'
import type { BillPlan, BillPlanPatch, BillPlanPayload } from '@/types/api'

export function listPlans(signal?: AbortSignal) {
  return request<BillPlan[]>('/plans', { signal })
}
export function getPlan(id: number, signal?: AbortSignal) {
  return request<BillPlan>(`/plans/${id}`, { signal })
}
export function createPlan(payload: BillPlanPayload) {
  return request<BillPlan>('/plans', { method: 'POST', body: JSON.stringify(payload) })
}
export function updatePlan(id: number, payload: BillPlanPatch) {
  return request<BillPlan>(`/plans/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export function deletePlan(id: number) {
  return request<void>(`/plans/${id}`, { method: 'DELETE' })
}
export function disablePlan(id: number) {
  return request<void>(`/plans/${id}/disable`, { method: 'POST' })
}
export function enablePlan(id: number) {
  return request<BillPlan>(`/plans/${id}/enable`, { method: 'POST' })
}

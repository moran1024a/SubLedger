import { request } from './client'
import type { BillPlanGroup, PlanLayout, PlanLayoutOrder } from '@/types/api'

export const listPlanGroups = (signal?: AbortSignal) =>
  request<BillPlanGroup[]>('/plan-groups', { signal })

export const getPlanLayout = (signal?: AbortSignal) =>
  request<PlanLayout>('/plans/layout', { signal })

export const savePlanLayout = (payload: PlanLayoutOrder) =>
  request<PlanLayout>('/plans/layout', { method: 'PUT', body: JSON.stringify(payload) })

export const createPlanGroup = (name: string, version: string) =>
  request<PlanLayout>('/plan-groups', { method: 'POST', body: JSON.stringify({ name, version }) })

export const renamePlanGroup = (id: number, name: string, version: string) =>
  request<PlanLayout>(`/plan-groups/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name, version }),
  })

export const deletePlanGroup = (id: number, version: string) =>
  request<PlanLayout>(`/plan-groups/${id}`, {
    method: 'DELETE',
    body: JSON.stringify({ version }),
  })

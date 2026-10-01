import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listBills } from '@/api/bills'
import { request } from '@/api/client'

vi.mock('@/api/client', () => ({ request: vi.fn() }))

beforeEach(() => vi.clearAllMocks())

describe('bill query parameters', () => {
  it('omits null, undefined and empty date filters', () => {
    listBills({ start_date: null, end_date: undefined, time_status: undefined })
    expect(request).toHaveBeenLastCalledWith('/bills?', { signal: undefined })
    listBills({ start_date: '', end_date: null })
    expect(request).toHaveBeenLastCalledWith('/bills?', { signal: undefined })
  })

  it('preserves false, zero and valid date values', () => {
    listBills({ start_date: '2026-09-30', is_valid: false, plan_id: 0, page: 0 })
    expect(request).toHaveBeenCalledWith(
      '/bills?start_date=2026-09-30&is_valid=false&plan_id=0&page=0',
      { signal: undefined },
    )
  })
})

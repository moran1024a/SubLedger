import { flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BillDetailDrawer from '@/components/billing/BillDetailDrawer.vue'
import HomeView from '@/views/HomeView.vue'
import { getBill, listBills, updateBillValidity } from '@/api/bills'
import { getSummary } from '@/api/statistics'
import { ApiError, type BillOccurrence } from '@/types/api'

vi.mock('@/api/bills', () => ({
  getBill: vi.fn(),
  listBills: vi.fn(),
  updateBillValidity: vi.fn(),
}))
vi.mock('@/api/statistics', () => ({ getSummary: vi.fn() }))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))
const bill: BillOccurrence = {
  id: 1,
  plan_id: 2,
  plan_name: '双年服务',
  due_date: '2028-02-29',
  amount: '240',
  is_valid: true,
  time_status: 'upcoming',
  cycle_type: 'year',
  cycle_interval: 2,
  cycle_days: null,
  plan_status: 'enabled',
}
async function plugins() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  return [createPinia(), router]
}
beforeEach(() => vi.clearAllMocks())
describe('bill details', () => {
  it('ignores a slow response after opening another bill', async () => {
    let resolve!: (value: BillOccurrence) => void
    vi.mocked(getBill)
      .mockReturnValueOnce(
        new Promise((done) => {
          resolve = done
        }),
      )
      .mockResolvedValueOnce({ ...bill, id: 3 })
    const wrapper = shallowMount(BillDetailDrawer, {
      props: { billId: 1 },
      global: { plugins: await plugins() },
    })
    await wrapper.setProps({ billId: 3 })
    await flushPromises()
    resolve(bill)
    await flushPromises()
    expect((wrapper.vm as unknown as { bill: BillOccurrence }).bill.id).toBe(3)
    expect(vi.mocked(getBill).mock.calls[0]![1]!.aborted).toBe(true)
  })
  it('keeps the updated detail visible even if it no longer matches the list', async () => {
    vi.mocked(getBill).mockResolvedValue(bill)
    vi.mocked(updateBillValidity).mockResolvedValue({ ...bill, is_valid: false })
    const wrapper = shallowMount(BillDetailDrawer, {
      props: { billId: 1 },
      global: { plugins: await plugins() },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as { bill: BillOccurrence; toggle: () => Promise<void> }
    await vm.toggle()
    expect(vm.bill.is_valid).toBe(false)
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.emitted('close')).toBeUndefined()
  })
  it('retains details and offers verification when a write times out without retrying', async () => {
    vi.mocked(getBill).mockResolvedValue(bill)
    vi.mocked(updateBillValidity).mockRejectedValue(
      new ApiError({ status: 0, code: 'TIMEOUT', message: '超时' }),
    )
    const wrapper = shallowMount(BillDetailDrawer, {
      props: { billId: 1 },
      global: { plugins: await plugins() },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      bill: BillOccurrence
      feedback: string
      toggle: () => Promise<void>
    }
    await vm.toggle()
    expect(vm.feedback).toContain('结果待确认')
    expect(vm.bill).toEqual(bill)
    expect(updateBillValidity).toHaveBeenCalledOnce()
    expect(wrapper.emitted('changed')).toBeUndefined()
  })
})
it('shows real upcoming bills independently when dashboard statistics fail', async () => {
  vi.mocked(getSummary).mockRejectedValue(new Error('statistics unavailable'))
  vi.mocked(listBills).mockResolvedValue({ items: [bill], total: 1, page: 1, page_size: 10 })
  const wrapper = shallowMount(HomeView, { global: { plugins: await plugins() } })
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    upcoming: BillOccurrence[]
    error: ApiError
    billsError: ApiError | null
  }
  expect(vm.upcoming).toEqual([bill])
  expect(vm.error).toBeTruthy()
  expect(vm.billsError).toBeNull()
  expect(listBills).toHaveBeenCalledWith(
    { time_status: 'upcoming', is_valid: true, sort: 'asc', page_size: 10 },
    expect.any(AbortSignal),
  )
})

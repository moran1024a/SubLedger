import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import BillsView from '@/views/bills/BillsView.vue'
import { listBills, updateBillValidity } from '@/api/bills'
import { listPlans } from '@/api/plans'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, type BillOccurrence, type BillOccurrencePage } from '@/types/api'

vi.mock('@/api/bills', () => ({ listBills: vi.fn(), updateBillValidity: vi.fn() }))
vi.mock('@/api/plans', () => ({ listPlans: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

const bill = {
  id: 3,
  plan_id: 2,
  plan_name: '云服务',
  due_date: '2026-07-20',
  amount: '12.50',
  is_valid: true,
  time_status: 'upcoming' as const,
  cycle_type: 'custom_days' as const,
  cycle_days: 14,
}

interface BillsVm {
  bills: BillOccurrence[]
  total: number
  page: number
  loading: boolean
  error: ApiError | null
  dateRange: string[] | null
  keyword: string
  timeStatus: 'upcoming' | 'passed' | 'all'
  query: () => void
  reset: () => void
  changeStatus: () => void
  navigate: () => Promise<void>
  load: () => Promise<void>
}

function deferred() {
  let resolve!: (value: BillOccurrencePage) => void
  let reject!: (cause: unknown) => void
  const promise = new Promise<BillOccurrencePage>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

let router: Router

function mountView() {
  return shallowMount(BillsView, {
    global: {
      plugins: [router],
      stubs: { PageHeader: true, LoadingBlock: true, ErrorState: true, EmptyState: true },
    },
  })
}

beforeEach(async () => {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/bills', component: { template: '<div />' } }],
  })
  await router.push('/bills')
  await router.isReady()
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.mocked(listPlans).mockResolvedValue([])
  vi.mocked(listBills).mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 })
  vi.mocked(updateBillValidity).mockResolvedValue({} as never)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

describe('BillsView', () => {
  it('accepts cleared date controls without stringifying their null values', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as BillsVm
    vm.dateRange = null
    vm.query()
    await flushPromises()

    expect(listBills).toHaveBeenLastCalledWith(
      expect.objectContaining({ start_date: '', end_date: '' }),
      expect.any(AbortSignal),
    )
  })

  it.each(['success', 'error'])(
    'ignores an older %s while the latest request is pending',
    async (kind) => {
      const wrapper = mountView()
      await flushPromises()
      const vm = wrapper.vm as unknown as BillsVm
      const older = deferred()
      const latest = deferred()
      vi.mocked(listBills).mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
      vm.page = 2
      const olderLoad = vm.load()
      vm.page = 3
      const latestLoad = vm.load()

      if (kind === 'success') older.resolve({ items: [bill], total: 60, page: 2, page_size: 20 })
      else older.reject(new ApiError({ status: 500, code: 'FAILED', message: '旧请求失败' }))
      await olderLoad
      expect(vm.loading).toBe(true)
      expect(vm.bills).toEqual([])
      expect(vm.total).toBe(0)
      expect(vm.error).toBeNull()

      latest.resolve({ items: [{ ...bill, id: 4 }], total: 80, page: 3, page_size: 20 })
      await latestLoad
      expect(vm.loading).toBe(false)
      expect(vm.bills).toEqual([{ ...bill, id: 4 }])
      expect(vm.total).toBe(80)
    },
  )

  it.each(['success', 'error'])('ignores an older %s after the latest response', async (kind) => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as BillsVm
    const older = deferred()
    const latest = deferred()
    vi.mocked(listBills).mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
    const olderLoad = vm.load()
    const latestLoad = vm.load()
    latest.resolve({ items: [{ ...bill, id: 4 }], total: 80, page: 3, page_size: 20 })
    await latestLoad

    if (kind === 'success') older.resolve({ items: [bill], total: 60, page: 2, page_size: 20 })
    else older.reject(new ApiError({ status: 500, code: 'FAILED', message: '旧请求失败' }))
    await olderLoad
    expect(vm.bills).toEqual([{ ...bill, id: 4 }])
    expect(vm.total).toBe(80)
    expect(vm.error).toBeNull()
    expect(vm.loading).toBe(false)
  })

  it('keeps the latest error when an older successful response arrives later', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as BillsVm
    const older = deferred()
    const latest = deferred()
    vi.mocked(listBills).mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
    const olderLoad = vm.load()
    const latestLoad = vm.load()
    const failure = new ApiError({ status: 500, code: 'FAILED', message: '当前请求失败' })
    latest.reject(failure)
    await latestLoad
    older.resolve({ items: [bill], total: 60, page: 2, page_size: 20 })
    await olderLoad

    expect(vm.error).toBe(failure)
    expect(vm.bills).toEqual([])
    expect(vm.total).toBe(0)
    expect(vm.loading).toBe(false)
  })

  it('uses the bill response cycle data and confirms invalidation', async () => {
    const wrapper = shallowMount(BillsView, {
      global: {
        plugins: [router],
        stubs: { PageHeader: true, LoadingBlock: true, ErrorState: true, EmptyState: true },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      cycleText: (value: typeof bill) => string
      toggle: (value: typeof bill) => Promise<void>
    }

    expect(vm.cycleText(bill)).toBe('每 14 天')
    await vm.toggle(bill)
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('不再计入统计'),
      expect.any(String),
      expect.any(Object),
    )
    expect(updateBillValidity).toHaveBeenCalledWith(3, false)
  })
})

describe('bill query interactions', () => {
  it('starts with upcoming even when rule choices are still pending', async () => {
    vi.mocked(listPlans).mockReturnValue(new Promise(() => {}))
    const wrapper = mountView()
    await flushPromises()
    expect(listBills).toHaveBeenCalledWith(
      expect.objectContaining({ time_status: 'upcoming', sort: 'asc' }),
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })

  it('keeps draft filters out of pagination and restores submitted conditions from URL', async () => {
    vi.mocked(listBills).mockResolvedValue({ items: [bill], total: 60, page: 1, page_size: 20 })
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as BillsVm
    vm.keyword = 'cloud'
    vm.query()
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('cloud')
    vm.keyword = 'not submitted'
    vm.page = 2
    await vm.navigate()
    await flushPromises()
    expect(listBills).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'cloud', page: 2 }),
      expect.any(AbortSignal),
    )
    expect(vm.keyword).toBe('cloud')
    wrapper.unmount()
    mountView()
    await flushPromises()
    expect(listBills).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'cloud', page: 2 }),
      expect.any(AbortSignal),
    )
  })

  it('switches history to descending and reset clears even an unsubmitted draft', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as BillsVm
    vm.timeStatus = 'passed'
    vm.changeStatus()
    await flushPromises()
    expect(listBills).toHaveBeenLastCalledWith(
      expect.objectContaining({ time_status: 'passed', sort: 'desc' }),
      expect.any(AbortSignal),
    )
    vm.reset()
    await flushPromises()
    vm.keyword = 'draft'
    vm.reset()
    await flushPromises()
    expect(vm.keyword).toBe('')
    expect(listBills).toHaveBeenLastCalledWith(
      expect.objectContaining({ time_status: 'upcoming', sort: 'asc', q: '' }),
      expect.any(AbortSignal),
    )
  })

  it('rejects inverted dates without querying', async () => {
    const wrapper = mountView()
    await flushPromises()
    vi.mocked(listBills).mockClear()
    const vm = wrapper.vm as unknown as BillsVm
    vm.dateRange = ['2026-10-02', '2026-10-01']
    vm.query()
    await flushPromises()
    expect(listBills).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalled()
  })

  it('returns to the last valid page and updates the URL', async () => {
    await router.push('/bills?time_status=passed&page=3')
    vi.mocked(listBills).mockResolvedValue({ items: [], total: 21, page: 3, page_size: 20 })
    const wrapper = mountView()
    await flushPromises()
    expect((wrapper.vm as unknown as BillsVm).page).toBe(2)
    expect(router.currentRoute.value.query.page).toBe('2')
    expect(listBills).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2, sort: 'desc' }),
      expect.any(AbortSignal),
    )
  })
})

it('opens a detail without resetting draft filters or reloading the list', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as { keyword: string }
  vm.keyword = '尚未查询的名称'
  const calls = vi.mocked(listBills).mock.calls.length
  await router.push({ query: { bill_id: '3' } })
  await flushPromises()
  expect(vm.keyword).toBe('尚未查询的名称')
  expect(listBills).toHaveBeenCalledTimes(calls)
  await router.replace({ query: {} })
  await flushPromises()
  expect(listBills).toHaveBeenCalledTimes(calls)
})

it('renders the details drawer for a bill in the URL without resetting draft filters', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as BillsVm
  vm.keyword = '尚未提交'
  await router.push('/bills?bill_id=7')
  await flushPromises()
  expect(wrapper.findComponent({ name: 'BillDetailDrawer' }).props('billId')).toBe(7)
  expect(vm.keyword).toBe('尚未提交')
  expect(listBills).toHaveBeenCalledOnce()
})

it('refreshes default filters when URL normalization does not change the filter key', async () => {
  const pending = deferred()
  vi.mocked(listBills).mockReturnValueOnce(pending.promise)
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as BillsVm
  vm.query()
  await flushPromises()
  expect(listBills).toHaveBeenCalledTimes(2)
  expect(vi.mocked(listBills).mock.calls[0]![1]!.aborted).toBe(true)
  expect(vm.loading).toBe(false)
  pending.resolve({ items: [bill], page: 1, page_size: 20, total: 1 })
  await flushPromises()
  expect(vm.bills).toEqual([])
})

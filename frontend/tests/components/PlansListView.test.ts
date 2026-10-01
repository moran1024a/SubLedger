import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import PlansListView from '@/views/plans/PlansListView.vue'
import { deletePlan, listPlans } from '@/api/plans'
import { ElMessageBox } from 'element-plus'
import { ApiError, type BillPlan } from '@/types/api'

vi.mock('@/api/plans', () => ({
  deletePlan: vi.fn(),
  disablePlan: vi.fn(),
  enablePlan: vi.fn(),
  listPlans: vi.fn(),
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

const plan: BillPlan = {
  id: 2,
  future_bills_rebuilt: false,
  name: '云服务',
  amount: '12.50',
  first_due_date: '2026-07-20',
  cycle_type: 'monthly',
  cycle_days: null,
  is_enabled: true,
  note: null,
  created_at: '',
  updated_at: '',
}

let router: Router
beforeEach(async () => {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/plans', component: { template: '<div />' } }],
  })
  await router.push('/plans')
  await router.isReady()
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.mocked(listPlans).mockResolvedValue([plan])
  vi.mocked(deletePlan).mockResolvedValue(undefined)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

function mountView() {
  return shallowMount(PlansListView, {
    global: {
      plugins: [router],
      stubs: {
        PageHeader: true,
        LoadingBlock: true,
        ErrorState: true,
        EmptyState: true,
        StatusTag: true,
        MoneyText: true,
      },
    },
  })
}

describe('PlansListView', () => {
  it('confirms the date boundary, deletes the rule, and reloads the list', async () => {
    const wrapper = mountView()
    await flushPromises()

    await (wrapper.vm as unknown as { remove: (value: BillPlan) => Promise<void> }).remove(plan)

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('今天以前的已过账单会保留'),
      '确认删除账单规则',
      expect.objectContaining({ confirmButtonText: '删除' }),
    )
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('今天及未来账单会同步删除'),
      expect.any(String),
      expect.any(Object),
    )
    expect(deletePlan).toHaveBeenCalledWith(2)
    expect(listPlans).toHaveBeenCalledTimes(2)
  })

  it('does not delete when confirmation is cancelled', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const wrapper = mountView()
    await flushPromises()

    await (wrapper.vm as unknown as { remove: (value: BillPlan) => Promise<void> }).remove(plan)

    expect(deletePlan).not.toHaveBeenCalled()
  })

  it('refreshes a stale list when the rule is already gone', async () => {
    vi.mocked(deletePlan).mockRejectedValue(
      new ApiError({ status: 404, code: 'BILL_PLAN_NOT_FOUND', message: '账单规则不存在' }),
    )
    const wrapper = mountView()
    await flushPromises()

    await (wrapper.vm as unknown as { remove: (value: BillPlan) => Promise<void> }).remove(plan)

    expect(listPlans).toHaveBeenCalledTimes(2)
  })
})

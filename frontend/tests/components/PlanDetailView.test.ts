import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import PlanDetailView from '@/views/plans/PlanDetailView.vue'
import { deletePlan, getPlan } from '@/api/plans'
import { ElMessageBox } from 'element-plus'
import { ApiError, type BillPlan } from '@/types/api'

const replace = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '2' }, query: {}, fullPath: '/plans/2' }),
  useRouter: () => ({ push: vi.fn(), replace }),
}))
vi.mock('@/api/plans', () => ({
  deletePlan: vi.fn(),
  disablePlan: vi.fn(),
  enablePlan: vi.fn(),
  getPlan: vi.fn(),
  updatePlan: vi.fn(),
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

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.mocked(getPlan).mockResolvedValue(plan)
  vi.mocked(deletePlan).mockResolvedValue(undefined)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

describe('PlanDetailView', () => {
  function mountView() {
    return shallowMount(PlanDetailView, {
      global: {
        stubs: {
          PageHeader: true,
          LoadingBlock: true,
          ErrorState: true,
          BillPlanForm: true,
          StatusTag: true,
          MoneyText: true,
        },
      },
    })
  }

  it('deletes the rule and replaces the deleted detail route', async () => {
    const wrapper = mountView()
    await flushPromises()

    await (wrapper.vm as unknown as { remove: () => Promise<void> }).remove()

    expect(deletePlan).toHaveBeenCalledWith(2)
    expect(replace).toHaveBeenCalledWith('/plans')
  })

  it('leaves a stale detail route when the rule is already gone', async () => {
    vi.mocked(deletePlan).mockRejectedValue(
      new ApiError({ status: 404, code: 'BILL_PLAN_NOT_FOUND', message: '账单规则不存在' }),
    )
    const wrapper = mountView()
    await flushPromises()

    await (wrapper.vm as unknown as { remove: () => Promise<void> }).remove()

    expect(replace).toHaveBeenCalledWith('/plans')
  })
})

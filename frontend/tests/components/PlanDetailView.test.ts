import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import PlanDetailView from '@/views/plans/PlanDetailView.vue'
import { deletePlan, disablePlan, enablePlan, getPlan, updatePlan } from '@/api/plans'
import { ElMessageBox } from 'element-plus'
import { ApiError, type BillPlan, type BillPlanPayload } from '@/types/api'

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

  it('warns that a schedule change rebuilds reminders that may be sent again', async () => {
    vi.mocked(updatePlan).mockResolvedValue({ ...plan, first_due_date: '2026-08-01' })
    const wrapper = mountView()
    await flushPromises()
    const payload: BillPlanPayload = {
      name: plan.name,
      amount: plan.amount,
      first_due_date: '2026-08-01',
      cycle_type: 'month',
      cycle_interval: 1,
      cycle_days: null,
      note: null,
    }
    await (wrapper.vm as unknown as { save: (value: BillPlanPayload) => Promise<void> }).save(
      payload,
    )
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('今日及未来的提醒记录会重建，已发送的当天提醒可能再次发送。'),
      '确认保存账单规则',
      expect.any(Object),
    )
    expect(updatePlan).toHaveBeenCalledWith(2, payload)
  })

  it('explains that disabling reduces today, month and year totals', async () => {
    const wrapper = mountView()
    await flushPromises()
    await (wrapper.vm as unknown as { toggle: () => Promise<void> }).toggle()
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('今日、本月、全年合计会同步减少'),
      '确认停用',
      expect.any(Object),
    )
    expect(disablePlan).toHaveBeenCalledWith(2)
  })

  it('confirms enabling and explains manually invalidated bills stay invalid', async () => {
    vi.mocked(getPlan).mockResolvedValue({ ...plan, is_enabled: false })
    const wrapper = mountView()
    await flushPromises()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    const vm = wrapper.vm as unknown as { toggle: () => Promise<void> }
    await vm.toggle()
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('手动标记无效的账单不会恢复。'),
      '确认启用',
      expect.any(Object),
    )
    expect(enablePlan).not.toHaveBeenCalled()
    await vm.toggle()
    expect(enablePlan).toHaveBeenCalledWith(2)
  })
})

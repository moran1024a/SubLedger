import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { defineComponent, type Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import PlanFormView from '@/views/plans/PlanFormView.vue'
import PlanDetailView from '@/views/plans/PlanDetailView.vue'
import PlansListView from '@/views/plans/PlansListView.vue'
import BillsView from '@/views/bills/BillsView.vue'
import HomeView from '@/views/HomeView.vue'
import BillDetailDrawer from '@/components/billing/BillDetailDrawer.vue'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import { createPlan, deletePlan, disablePlan, getPlan, listPlans, updatePlan } from '@/api/plans'
import { getBill, listBills, updateBillValidity } from '@/api/bills'
import { getSummary } from '@/api/statistics'
import {
  ApiError,
  type BillOccurrence,
  type BillPlan,
  type BillPlanPayload,
  type StatisticsResponse,
} from '@/types/api'

vi.mock('@/api/plans', () => ({
  createPlan: vi.fn(),
  deletePlan: vi.fn(),
  disablePlan: vi.fn(),
  enablePlan: vi.fn(),
  getPlan: vi.fn(),
  listPlans: vi.fn(),
  updatePlan: vi.fn(),
}))
vi.mock('@/api/bills', () => ({
  getBill: vi.fn(),
  listBills: vi.fn(),
  updateBillValidity: vi.fn(),
}))
vi.mock('@/api/statistics', () => ({ getSummary: vi.fn() }))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

const plan: BillPlan = {
  id: 2,
  name: '云服务',
  amount: '12.50',
  first_due_date: '2026-07-20',
  cycle_type: 'month',
  cycle_interval: 1,
  cycle_days: null,
  is_enabled: true,
  note: null,
  future_bills_rebuilt: false,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
}
const payload: BillPlanPayload = {
  name: plan.name,
  amount: plan.amount,
  first_due_date: plan.first_due_date,
  cycle_type: 'month',
  cycle_interval: 1,
  cycle_days: null,
  note: null,
}
const bill: BillOccurrence = {
  id: 3,
  plan_id: 2,
  plan_name: '云服务',
  amount: '12.50',
  due_date: '2026-07-20',
  cycle_type: 'month',
  cycle_interval: 1,
  cycle_days: null,
  is_valid: true,
  time_status: 'upcoming',
  plan_status: 'enabled',
}
const timeout = () => new ApiError({ status: 0, code: 'TIMEOUT', message: '超时' })
const rejected = () => new ApiError({ status: 409, code: 'CONFLICT', message: '此操作不能执行' })
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
const wrappers: VueWrapper[] = []
const stubs = {
  PageHeader: true,
  LoadingBlock: true,
  ErrorState: true,
  EmptyState: true,
  OperationFeedback: true,
  StatusTag: true,
  MoneyText: true,
  BillPlanForm: true,
  BillDetailDrawer: true,
  'el-card': { template: '<div><slot /><slot name="header" /></div>' },
  'el-table': true,
  'el-descriptions': true,
  'el-drawer': { template: '<div><slot /></div>' },
  'el-empty': true,
}
async function view(component: Component, path: string, extraStubs = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/plans/new',
        component: component === PlanFormView ? PlanFormView : { template: '<div />' },
      },
      {
        path: '/plans/:id',
        component: component === PlanDetailView ? PlanDetailView : { template: '<div />' },
      },
      {
        path: '/plans',
        component: component === PlansListView ? PlansListView : { template: '<div />' },
      },
      { path: '/bills', component: component === BillsView ? BillsView : { template: '<div />' } },
      { path: '/', component: component === HomeView ? HomeView : { template: '<div />' } },
      { path: '/settings/notifications', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  const host = mount(defineComponent({ template: '<router-view />' }), {
    global: { plugins: [createPinia(), router], stubs: { ...stubs, ...extraStubs } },
  })
  wrappers.push(host)
  await flushPromises()
  return { router, host, wrapper: host.findComponent(component) }
}
async function drawer(id = 3) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  const wrapper = mount(BillDetailDrawer, {
    props: { billId: id },
    global: { plugins: [createPinia(), router], stubs },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(createPlan).mockResolvedValue(plan)
  vi.mocked(getPlan).mockImplementation(async (id) => ({ ...plan, id }))
  vi.mocked(updatePlan).mockResolvedValue(plan)
  vi.mocked(listPlans).mockResolvedValue([{ ...plan }])
  vi.mocked(getBill).mockImplementation(async (id) => ({ ...bill, id }))
  vi.mocked(listBills).mockResolvedValue({ items: [{ ...bill }], total: 1, page: 1, page_size: 20 })
  vi.mocked(updateBillValidity).mockResolvedValue({ ...bill, is_valid: false })
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
  vi.mocked(getSummary).mockRejectedValue(new Error('statistics unavailable'))
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
})

describe('billing writes remain scoped to their resource', () => {
  it('does not navigate or show success after a create response arrives on another page', async () => {
    const pending = deferred<BillPlan>()
    vi.mocked(createPlan).mockReturnValue(pending.promise)
    const { router, wrapper } = await view(PlanFormView, '/plans/new')
    const saving = (
      wrapper.vm as unknown as { save: (value: BillPlanPayload) => Promise<void> }
    ).save(payload)
    await router.push('/bills')
    pending.resolve(plan)
    await saving
    expect(router.currentRoute.value.path).toBe('/bills')
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('confirms before resubmitting an uncertain create and never matches it to a similar rule', async () => {
    vi.mocked(createPlan).mockRejectedValueOnce(timeout()).mockResolvedValueOnce(plan)
    const { router, wrapper } = await view(PlanFormView, '/plans/new', {
      BillPlanForm: false,
      'el-form': { template: '<form><slot /></form>' },
      'el-form-item': { template: '<div><slot /></div>' },
    })
    const vm = wrapper.vm as unknown as {
      save: (value: BillPlanPayload) => Promise<void>
      operationMessage: string
      submitting: boolean
    }
    await vm.save(payload)
    expect(createPlan).toHaveBeenCalledOnce()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(vm.operationMessage).toContain('结果待确认')

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await vm.save(payload)
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('重复创建会产生两条规则'),
      '确认再次提交',
      expect.objectContaining({ confirmButtonText: '继续提交', cancelButtonText: '取消' }),
    )
    expect(createPlan).toHaveBeenCalledOnce()
    expect(vm.operationMessage).toContain('结果待确认')
    expect(vm.submitting).toBe(false)

    await vm.save(payload)
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(2)
    expect(createPlan).toHaveBeenCalledTimes(2)
    expect(listPlans).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/plans/2')
  })

  it('opens the rule list in a new tab to verify an uncertain create without losing the draft', async () => {
    vi.mocked(createPlan).mockRejectedValue(timeout())
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    const { router, wrapper } = await view(PlanFormView, '/plans/new')
    await (wrapper.vm as unknown as { save: (value: BillPlanPayload) => Promise<void> }).save(
      payload,
    )
    await flushPromises()
    const feedback = wrapper.findComponent(OperationFeedback)
    expect(feedback.props('action')).toBe('查看最近规则，核实是否已创建')
    feedback.vm.$emit('check')
    expect(open).toHaveBeenCalledWith('/plans', '_blank', 'noopener')
    expect(router.currentRoute.value.path).toBe('/plans/new')
    open.mockRestore()
  })

  it('does not confirm a representational amount or legacy cycle change', async () => {
    vi.mocked(getPlan).mockResolvedValue({
      ...plan,
      cycle_type: 'monthly',
      cycle_interval: undefined,
    })
    const { wrapper } = await view(PlanDetailView, '/plans/2')
    await (wrapper.vm as unknown as { save: (value: BillPlanPayload) => Promise<void> }).save({
      ...payload,
      amount: '12.5',
    })
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(updatePlan).toHaveBeenCalledWith(2, expect.objectContaining({ amount: '12.5' }))
  })

  it('awaits only the edit form discard confirmation before unmounting it', async () => {
    const confirmation = deferred<unknown>()
    vi.mocked(ElMessageBox.confirm).mockReturnValue(confirmation.promise as never)
    const { wrapper } = await view(PlanDetailView, '/plans/2', {
      BillPlanForm: false,
      'el-form': { template: '<form><slot /></form>' },
      'el-form-item': { template: '<div><slot /></div>' },
    })
    const vm = wrapper.vm as unknown as { editing: boolean; cancelEdit: () => Promise<void> }
    vm.editing = true
    await flushPromises()
    const form = wrapper.findComponent(BillPlanForm).vm as unknown as {
      form: { name: string }
      dirty: boolean
    }
    form.form.name = '草稿'
    const cancelling = vm.cancelEdit()
    expect(vm.editing).toBe(true)
    expect(form.dirty).toBe(true)
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    confirmation.resolve('confirm')
    await cancelling
    await flushPromises()
    expect(vm.editing).toBe(false)
    expect(wrapper.findComponent(BillPlanForm).exists()).toBe(false)
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
  })

  it.each(['invalid', '-1', '1e2'])('ends loading for invalid detail ID %s', async (id) => {
    const { wrapper } = await view(PlanDetailView, '/plans/' + id)
    const vm = wrapper.vm as unknown as { loading: boolean; error: ApiError }
    expect(vm.loading).toBe(false)
    expect(vm.error.message).toContain('地址无效')
    expect(getPlan).not.toHaveBeenCalled()
  })

  it('does not clear a newer pending save when an older resource finishes', async () => {
    const old = deferred<BillPlan>(),
      latest = deferred<BillPlan>()
    vi.mocked(updatePlan).mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise)
    const { router, wrapper } = await view(PlanDetailView, '/plans/2')
    const vm = wrapper.vm as unknown as {
      submitting: boolean
      plan: BillPlan
      save: (value: BillPlanPayload) => Promise<void>
    }
    const first = vm.save(payload)
    await router.push('/plans/4')
    await flushPromises()
    const second = vm.save(payload)
    old.resolve(plan)
    await first
    expect(vm.submitting).toBe(true)
    expect(vm.plan.id).toBe(4)
    expect(ElMessage.success).not.toHaveBeenCalled()
    latest.resolve({ ...plan, id: 4 })
    await second
    expect(vm.submitting).toBe(false)
  })

  it('locks all rule actions through confirmation and ignores approval after leaving', async () => {
    const confirmation = deferred<unknown>()
    vi.mocked(ElMessageBox.confirm).mockReturnValue(confirmation.promise as never)
    const { router, wrapper } = await view(PlansListView, '/plans')
    const vm = wrapper.vm as unknown as {
      actionId: number | null
      toggle: (value: BillPlan) => Promise<void>
      remove: (value: BillPlan) => Promise<void>
    }
    const toggling = vm.toggle(plan)
    await vm.remove(plan)
    expect(vm.actionId).toBe(2)
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('云服务'),
      expect.any(String),
      expect.any(Object),
    )
    await router.push('/bills')
    confirmation.resolve('confirm')
    await toggling
    expect(disablePlan).not.toHaveBeenCalled()
    expect(deletePlan).not.toHaveBeenCalled()
  })

  it('does not mutate a row whose current validity changed during confirmation', async () => {
    const confirmation = deferred<unknown>()
    vi.mocked(ElMessageBox.confirm).mockReturnValue(confirmation.promise as never)
    const { wrapper } = await view(BillsView, '/bills')
    const vm = wrapper.vm as unknown as {
      bills: BillOccurrence[]
      toggle: (value: BillOccurrence) => Promise<void>
    }
    const toggling = vm.toggle(bill)
    vm.bills = [{ ...bill, is_valid: false }]
    confirmation.resolve('confirm')
    await toggling
    expect(updateBillValidity).not.toHaveBeenCalled()
  })

  it('keeps new details untouched and invalidates the same parent after a late drawer write', async () => {
    const pending = deferred<BillOccurrence>()
    vi.mocked(updateBillValidity).mockReturnValue(pending.promise)
    const wrapper = await drawer()
    const vm = wrapper.vm as unknown as {
      bill: BillOccurrence
      feedback: string
      saving: boolean
      toggle: () => Promise<void>
    }
    const toggling = vm.toggle()
    await flushPromises()
    await wrapper.setProps({ billId: 8 })
    await flushPromises()
    pending.resolve({ ...bill, is_valid: false })
    await toggling
    expect(vm.bill.id).toBe(8)
    expect(vm.feedback).toBe('')
    expect(vm.saving).toBe(false)
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(ElMessage.success).not.toHaveBeenCalled()
  })
})

describe('billing verification and synchronization', () => {
  it.each([
    { component: BillsView, path: '/bills', kind: 'list' },
    { component: HomeView, path: '/', kind: 'home' },
  ])(
    'refreshes $kind after browser back closes a drawer whose write then succeeds',
    async ({ component, path, kind }) => {
      const summary: StatisticsResponse = {
        date: '2026-07-20',
        today: { count: 1, amount: '12.50' },
        current_month: { count: 1, amount: '12.50' },
        current_year: { count: 1, amount: '12.50' },
        averages: { monthly: '12.50', daily: '0.41' },
        next_bill: null,
      }
      vi.mocked(getSummary).mockResolvedValue(summary)
      const pending = deferred<BillOccurrence>()
      vi.mocked(updateBillValidity).mockReturnValue(pending.promise)
      const { router, wrapper } = await view(component, path, { BillDetailDrawer: false })
      const parentVm = wrapper.vm as unknown as {
        billId: number | null
        bills: BillOccurrence[]
        upcoming: BillOccurrence[]
        data: StatisticsResponse
        openBill: (id: number) => Promise<void>
      }
      await parentVm.openBill(3)
      await flushPromises()
      const detail = wrapper.findComponent(BillDetailDrawer)
      const drawerVm = detail.vm as unknown as {
        bill: BillOccurrence | null
        toggle: () => Promise<void>
      }
      const saving = drawerVm.toggle()
      await flushPromises()
      expect(updateBillValidity).toHaveBeenCalledOnce()
      const backed = new Promise<void>((resolve) => {
        const stop = router.afterEach(() => {
          stop()
          resolve()
        })
      })
      router.back()
      await backed
      await flushPromises()
      expect(router.currentRoute.value.path).toBe(path)
      expect(parentVm.billId).toBeNull()
      expect(listBills).toHaveBeenCalledOnce()
      vi.mocked(listBills).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
      vi.mocked(getSummary).mockResolvedValue({ ...summary, today: { count: 0, amount: '0.00' } })
      pending.resolve({ ...bill, is_valid: false })
      await saving
      await flushPromises()
      expect(listBills).toHaveBeenCalledTimes(2)
      expect(kind === 'list' ? parentVm.bills : parentVm.upcoming).toEqual([])
      if (kind === 'home') {
        expect(getSummary).toHaveBeenCalledTimes(2)
        expect(parentVm.data.today.count).toBe(0)
      }
      expect(drawerVm.bill).toBeNull()
      expect(detail.emitted('changed')).toHaveLength(1)
      expect(ElMessage.success).not.toHaveBeenCalled()
    },
  )

  it('does not invalidate the old parent after leaving its route during a drawer write', async () => {
    const pending = deferred<BillOccurrence>()
    vi.mocked(updateBillValidity).mockReturnValue(pending.promise)
    const { router, wrapper } = await view(BillsView, '/bills?bill_id=3', {
      BillDetailDrawer: false,
    })
    const detail = wrapper.findComponent(BillDetailDrawer)
    const saving = (detail.vm as unknown as { toggle: () => Promise<void> }).toggle()
    await flushPromises()
    await router.push('/plans')
    pending.resolve({ ...bill, is_valid: false })
    await saving
    await flushPromises()
    expect(detail.emitted('changed')).toBeUndefined()
    expect(listBills).toHaveBeenCalledOnce()
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it.each([
    { component: BillsView, path: '/bills', kind: 'list' },
    { component: HomeView, path: '/', kind: 'home' },
  ])('explains and clears malformed bill links on the $kind page', async ({ component, path }) => {
    const { router, wrapper } = await view(component, path + '?bill_id=bad&q=cloud', {
      BillDetailDrawer: false,
    })
    for (const query of ['bill_id=bad', 'bill_id=0', 'bill_id=3&bill_id=4', 'bill_id']) {
      await router.replace(path + '?' + query + '&q=cloud')
      await flushPromises()
      const feedback = wrapper
        .findAllComponents(OperationFeedback)
        .find((item) => item.props('message').includes('详情链接无效'))
      expect(feedback).toBeDefined()
      expect(feedback!.props('action')).toBe('清除无效链接')
      const detail = wrapper.findComponent(BillDetailDrawer)
      expect(detail.props('billId')).toBeNull()
      expect((detail.vm as unknown as { loading: boolean }).loading).toBe(false)
      feedback!.vm.$emit('check')
      await flushPromises()
      expect(router.currentRoute.value.query).toEqual({ q: 'cloud' })
      expect(
        wrapper
          .findAllComponents(OperationFeedback)
          .some((item) => item.props('message').includes('详情链接无效')),
      ).toBe(false)
    }
    expect(getBill).not.toHaveBeenCalled()
    expect(updateBillValidity).not.toHaveBeenCalled()
  })

  it('retains an uncertain plan save after successfully reloading the unchanged target', async () => {
    vi.mocked(updatePlan).mockRejectedValue(timeout())
    const { wrapper } = await view(PlanDetailView, '/plans/2')
    const vm = wrapper.vm as unknown as {
      operationMessage: string
      plan: BillPlan
      save: (value: BillPlanPayload) => Promise<void>
      reload: () => Promise<void>
    }
    await vm.save({ ...payload, name: '新名称' })
    await vm.reload()
    expect(vm.plan.name).toBe(plan.name)
    expect(vm.operationMessage).toContain('原操作结果仍待确认')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(updatePlan).toHaveBeenCalledOnce()
  })

  it('clears a previous definitive failure when a later plan save succeeds', async () => {
    vi.mocked(updatePlan)
      .mockRejectedValueOnce(rejected())
      .mockResolvedValueOnce({ ...plan, name: '新名称' })
    const { wrapper } = await view(PlanDetailView, '/plans/2')
    const vm = wrapper.vm as unknown as {
      operationMessage: string
      save: (value: BillPlanPayload) => Promise<void>
    }
    await vm.save({ ...payload, name: '新名称' })
    expect(vm.operationMessage).toBe('此操作不能执行')
    await vm.save({ ...payload, name: '新名称' })
    expect(vm.operationMessage).toBe('')
    expect(ElMessage.success).toHaveBeenCalledOnce()
  })

  it('ends drawer loading and offers an explanation for an invalid bill identifier', async () => {
    const wrapper = await drawer(-1)
    const vm = wrapper.vm as unknown as { loading: boolean; error: ApiError }
    expect(vm.loading).toBe(false)
    expect(vm.error.message).toContain('地址无效')
    expect(getBill).not.toHaveBeenCalled()
  })
  it.each([false, true])(
    'clears definitive feedback and preserves uncertain feedback (%s) after a GET',
    async (uncertain) => {
      vi.mocked(updateBillValidity).mockRejectedValue(uncertain ? timeout() : rejected())
      const wrapper = await drawer()
      const vm = wrapper.vm as unknown as {
        feedback: string
        toggle: () => Promise<void>
        verify: () => Promise<void>
      }
      await vm.toggle()
      expect(vm.feedback).not.toBe('')
      await vm.verify()
      expect(vm.feedback).toBe(
        uncertain ? '已重新查询，当前账单为有效。原操作结果仍待确认，请核对后再操作。' : '',
      )
      expect(ElMessage.success).not.toHaveBeenCalled()
      expect(wrapper.emitted('changed')).toHaveLength(1)
      expect(updateBillValidity).toHaveBeenCalledOnce()
    },
  )

  it('retains drawer verification failure separately and never refreshes its parent on failure', async () => {
    vi.mocked(updateBillValidity).mockRejectedValue(timeout())
    const wrapper = await drawer()
    const vm = wrapper.vm as unknown as {
      feedback: string
      error: ApiError
      toggle: () => Promise<void>
      verify: () => Promise<void>
    }
    await vm.toggle()
    vi.mocked(getBill).mockRejectedValue(new Error('query unavailable'))
    await vm.verify()
    expect(vm.feedback).toContain('结果待确认')
    expect(vm.error).toBeInstanceOf(ApiError)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('updates an open drawer after its parent refreshes the list', async () => {
    const wrapper = await drawer()
    vi.mocked(getBill).mockResolvedValue({ ...bill, is_valid: false })
    await wrapper.setProps({ refreshKey: 1 })
    await flushPromises()
    expect((wrapper.vm as unknown as { bill: BillOccurrence }).bill.is_valid).toBe(false)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('refreshes bills after drawer verification and retains a list refresh failure', async () => {
    const { wrapper } = await view(BillsView, '/bills?bill_id=3')
    const vm = wrapper.vm as unknown as {
      error: ApiError
      bills: BillOccurrence[]
      refreshKey: number
      drawerBusy: boolean
    }
    const key = vm.refreshKey
    const detail = wrapper.findComponent(BillDetailDrawer)
    detail.vm.$emit('busy', true)
    await flushPromises()
    expect(vm.drawerBusy).toBe(true)
    vi.mocked(listBills).mockRejectedValue(new Error('list unavailable'))
    detail.vm.$emit('changed')
    await flushPromises()
    expect(vm.error).toBeInstanceOf(ApiError)
    expect(vm.bills).toEqual([bill])
    expect(vm.refreshKey).toBe(key)
  })

  it('still refreshes an open drawer when a successful list write cannot reload the list', async () => {
    const { wrapper } = await view(BillsView, '/bills?bill_id=3')
    const vm = wrapper.vm as unknown as {
      error: ApiError
      refreshKey: number
      toggle: (value: BillOccurrence) => Promise<void>
    }
    const key = vm.refreshKey
    vi.mocked(listBills).mockRejectedValue(new Error('list unavailable'))
    await vm.toggle(bill)
    await flushPromises()
    expect(vm.error).toBeInstanceOf(ApiError)
    expect(vm.refreshKey).toBeGreaterThan(key)
    expect(wrapper.findComponent(BillDetailDrawer).props('refreshKey')).toBe(vm.refreshKey)
  })

  it('refreshes homepage statistics and bills independently after drawer verification', async () => {
    const { wrapper } = await view(HomeView, '/?bill_id=3')
    vi.mocked(listBills).mockRejectedValue(new Error('bills unavailable'))
    wrapper.findComponent(BillDetailDrawer).vm.$emit('changed')
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      error: ApiError
      billsError: ApiError
      upcoming: BillOccurrence[]
    }
    expect(getSummary).toHaveBeenCalledTimes(2)
    expect(listBills).toHaveBeenCalledTimes(2)
    expect(vm.error).toBeInstanceOf(ApiError)
    expect(vm.billsError).toBeInstanceOf(ApiError)
    expect(vm.upcoming).toEqual([bill])
  })
})

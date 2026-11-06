import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import BillCalendar from '@/components/billing/BillCalendar.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { getBillCalendar } from '@/api/calendar'
import { ApiError, type BillCalendarResponse, type CalendarBill } from '@/types/api'

vi.mock('@/api/calendar', () => ({ getBillCalendar: vi.fn() }))
const entry = (plan_id: number, bill_id: number | null): CalendarBill => ({
  plan_id,
  bill_id,
  plan_name: `订阅 ${plan_id}`,
  amount: '10.00',
  cycle_type: 'month',
  cycle_interval: 1,
  plan_status: 'enabled',
  is_estimated: bill_id === null,
})
function fixture(month = '2026-11'): BillCalendarResponse {
  return {
    month,
    today: '2026-11-07',
    count: month === '2026-11' ? 4 : 0,
    amount: month === '2026-11' ? '40.00' : '0.00',
    estimated_count: month === '2026-11' ? 2 : 0,
    days:
      month !== '2026-11'
        ? []
        : [
            {
              date: '2026-11-05',
              count: 1,
              amount: '10.00',
              estimated_count: 0,
              bills: [entry(1, 101)],
            },
            {
              date: '2026-11-07',
              count: 2,
              amount: '20.00',
              estimated_count: 1,
              bills: [entry(2, 102), entry(3, null)],
            },
            {
              date: '2026-11-22',
              count: 1,
              amount: '10.00',
              estimated_count: 1,
              bills: [entry(4, null)],
            },
          ],
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}
async function mountCalendar() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/plans/:id', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  const wrapper = mount(BillCalendar, {
    props: { refreshKey: 0 },
    global: {
      plugins: [createPinia(), router],
      stubs: {
        'el-card': { template: '<section><slot /></section>' },
        'el-button': {
          props: ['disabled'],
          template: '<button :disabled="disabled"><slot /></button>',
        },
        ErrorState: true,
        LoadingBlock: true,
      },
    },
  })
  await flushPromises()
  return { wrapper, router }
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getBillCalendar).mockImplementation(async (month) => fixture(month))
})

describe('home bill calendar', () => {
  it('highlights the server account date and distinguishes past, today and future bill dates', async () => {
    const { wrapper } = await mountCalendar()
    expect(getBillCalendar).toHaveBeenCalledWith(undefined, expect.any(AbortSignal))
    expect(wrapper.findAll('.calendar-day')).toHaveLength(42)
    expect(wrapper.find('[data-date="2026-11-07"]').attributes('aria-current')).toBe('date')
    expect(wrapper.find('[data-date="2026-11-07"]').classes()).toContain('is-selected')
    expect(wrapper.find('[data-date="2026-11-05"]').classes()).toContain('tone-past')
    expect(wrapper.find('[data-date="2026-11-07"]').classes()).toContain('tone-today')
    expect(wrapper.find('[data-date="2026-11-22"]').classes()).toContain('tone-future')
    expect(wrapper.find('[data-date="2026-10-31"]').classes()).toContain('outside-month')
    expect(wrapper.find('.calendar-caption').text()).toContain('4 笔')
    expect(wrapper.find('.current-month').text()).toBe('本月')
    expect(wrapper.findAll('.day-bill')).toHaveLength(2)
  })
  it('opens a recorded bill through the existing drawer event', async () => {
    const { wrapper, router } = await mountCalendar()
    await wrapper.find('[data-date="2026-11-05"]').trigger('click')
    expect(wrapper.find('.day-panel-heading').text()).toContain('11 月 5 日')
    await wrapper.find('.day-bill').trigger('click')
    expect(wrapper.emitted('openBill')?.[0]?.[0]).toBe(101)
    expect(router.currentRoute.value.path).toBe('/')
  })
  it('labels a projection and opens its rule without inventing a bill ID', async () => {
    const { wrapper, router } = await mountCalendar()
    await wrapper.find('[data-date="2026-11-22"]').trigger('click')
    expect(wrapper.find('.estimate-tag').text()).toBe('预计 · 查看规则')
    await wrapper.find('.day-bill').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/plans/4')
    expect(router.currentRoute.value.query.return_to).toBe('/')
    expect(wrapper.emitted('openBill')).toBeUndefined()
  })
  it('switches through adjacent dates and returns to the server current month', async () => {
    const { wrapper } = await mountCalendar()
    await wrapper.find('[data-date="2026-12-01"]').trigger('click')
    await flushPromises()
    expect(getBillCalendar).toHaveBeenLastCalledWith('2026-12', expect.any(AbortSignal))
    expect(wrapper.find('.current-month').exists()).toBe(false)
    expect(wrapper.findAll('.has-bills')).toHaveLength(0)
    expect(wrapper.find('.day-empty').text()).toContain('这一天没有有效账单')
    await wrapper.find('.today-button').trigger('click')
    await flushPromises()
    expect(getBillCalendar).toHaveBeenLastCalledWith(undefined, expect.any(AbortSignal))
    expect(wrapper.find('[data-date="2026-11-07"]').classes()).toContain('is-selected')
  })
  it('keeps the newest month when requests complete out of order', async () => {
    const { wrapper } = await mountCalendar()
    const december = deferred<BillCalendarResponse>()
    vi.mocked(getBillCalendar).mockReturnValueOnce(december.promise)
    await wrapper.find('[aria-label="下个月"]').trigger('click')
    const oldSignal = vi.mocked(getBillCalendar).mock.calls.at(-1)![1]!
    await wrapper.find('[aria-label="下个月"]').trigger('click')
    await flushPromises()
    expect(oldSignal.aborted).toBe(true)
    december.resolve(fixture('2026-12'))
    await flushPromises()
    expect(wrapper.find('.month-label').text()).toContain('2027 年 1 月')
    expect(wrapper.find('[data-date="2027-01-01"]').classes()).toContain('is-selected')
  })
  it('never presents an unloaded month as an empty month and can retry', async () => {
    vi.mocked(getBillCalendar).mockRejectedValueOnce(new Error('offline'))
    const { wrapper } = await mountCalendar()
    expect(wrapper.findComponent(ErrorState).exists()).toBe(true)
    expect(wrapper.find('.day-empty').exists()).toBe(false)
    expect(wrapper.find('.calendar-caption').text()).not.toContain('0 笔')
    wrapper.findComponent(ErrorState).vm.$emit('retry')
    await flushPromises()
    expect(wrapper.findComponent(ErrorState).exists()).toBe(false)
  })
  it('preserves the selected date when refreshing and removes a newly invalid bill', async () => {
    const { wrapper } = await mountCalendar()
    await wrapper.find('[data-date="2026-11-22"]').trigger('click')
    const updated = fixture()
    updated.days = updated.days.filter((day) => day.date !== '2026-11-22')
    updated.count = 3
    updated.estimated_count = 1
    updated.amount = '30.00'
    vi.mocked(getBillCalendar).mockResolvedValueOnce(updated)
    await wrapper.setProps({ refreshKey: 1 })
    await flushPromises()
    expect(wrapper.find('[data-date="2026-11-22"]').classes()).toContain('is-selected')
    expect(wrapper.find('[data-date="2026-11-22"]').classes()).not.toContain('has-bills')
    expect(wrapper.find('.day-empty').exists()).toBe(true)
  })
  it('keeps prior data on refresh failure and disables stale detail actions', async () => {
    const { wrapper } = await mountCalendar()
    vi.mocked(getBillCalendar).mockRejectedValueOnce(
      new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '服务错误' }),
    )
    await wrapper.setProps({ refreshKey: 1 })
    await flushPromises()
    expect(wrapper.findComponent(ErrorState).props('message')).toContain('保留上次结果')
    expect(wrapper.find('.day-bill').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-date="2026-11-07"]').classes()).toContain('has-bills')
  })
  it('supports keyboard navigation across month boundaries', async () => {
    const { wrapper } = await mountCalendar()
    await wrapper.find('[data-date="2026-11-30"]').trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(wrapper.find('[data-date="2026-12-01"]').attributes('tabindex')).toBe('0')
    expect(getBillCalendar).toHaveBeenLastCalledWith('2026-12', expect.any(AbortSignal))
  })
  it('blocks interaction during an active bill write and cancels queries on unmount', async () => {
    const { wrapper } = await mountCalendar()
    await wrapper.setProps({ disabled: true })
    await wrapper.find('[aria-label="下个月"]').trigger('click')
    await wrapper.find('.day-bill').trigger('click')
    expect(getBillCalendar).toHaveBeenCalledOnce()
    expect(wrapper.emitted('openBill')).toBeUndefined()
    const pending = deferred<BillCalendarResponse>()
    vi.mocked(getBillCalendar).mockReturnValueOnce(pending.promise)
    await wrapper.setProps({ disabled: false, refreshKey: 1 })
    const signal = vi.mocked(getBillCalendar).mock.calls.at(-1)![1]!
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
    pending.resolve(fixture())
    await flushPromises()
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PlansListView from '@/views/plans/PlansListView.vue'
import {
  createPlanGroup,
  deletePlanGroup,
  getPlanLayout,
  renamePlanGroup,
  savePlanLayout,
} from '@/api/planGroups'
import { ApiError, type BillPlan, type BillPlanGroup, type PlanLayout } from '@/types/api'

vi.mock('@/api/planGroups', () => ({
  getPlanLayout: vi.fn(),
  savePlanLayout: vi.fn(),
  createPlanGroup: vi.fn(),
  renamePlanGroup: vi.fn(),
  deletePlanGroup: vi.fn(),
}))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))
type Group = BillPlanGroup & { plans: BillPlan[] }
type View = {
  groups: Group[]
  search: string
  canSort: boolean
  saving: boolean
  layoutStale: boolean
  operationMessage: string
  moveGroup: (index: number, delta: number) => Promise<void>
  movePlan: (group: Group, index: number, delta: number) => Promise<void>
  moveToGroup: (group: Group, plan: BillPlan, id: number) => Promise<void>
  changeGroup: (group?: Group, remove?: boolean) => Promise<void>
  startDrag: () => void
  endDrag: () => Promise<void>
  load: () => Promise<void>
}
const rule = (id: number, group_id: number | null = null): BillPlan => ({
  id,
  group_id,
  name: `规则${id}`,
  amount: '10.00',
  first_due_date: '2026-11-07',
  cycle_type: 'month',
  cycle_days: null,
  is_enabled: true,
  note: null,
  created_at: '2026-11-07T00:00:00Z',
  updated_at: '2026-11-07T00:00:00Z',
  future_bills_rebuilt: false,
})
let layout: PlanLayout
beforeEach(() => {
  vi.resetAllMocks()
  layout = {
    version: 'v1',
    groups: [
      { id: 1, name: '未分组', is_default: true, sort_order: 0 },
      { id: 2, name: '服务', is_default: false, sort_order: 1 },
      { id: 3, name: '空组', is_default: false, sort_order: 2 },
    ],
    plans: [rule(11), rule(10), rule(12, 2)],
  }
  vi.mocked(getPlanLayout).mockImplementation(async () => structuredClone(layout))
  vi.mocked(savePlanLayout).mockImplementation(async (order) => {
    layout = {
      version: 'v2',
      groups: order.groups.map((item, index) => ({
        ...layout.groups.find((group) => group.id === item.id)!,
        sort_order: index,
      })),
      plans: order.groups.flatMap((group) =>
        group.plan_ids.map((id, index) => ({
          ...layout.plans.find((plan) => plan.id === id)!,
          group_id: group.id === 1 ? null : group.id,
          sort_order: index,
        })),
      ),
    }
    return structuredClone(layout)
  })
})
async function mountView(renderGroups = false) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/plans', component: { template: '<div />' } }],
  })
  await router.push('/plans')
  const wrapper = (renderGroups ? mount : shallowMount)(PlansListView, {
    attachTo: renderGroups ? document.body : undefined,
    global: {
      plugins: [createPinia(), router],
      stubs: renderGroups ? { 'el-card': { template: '<div><slot /></div>' } } : {},
    },
  })
  await flushPromises()
  return { wrapper, vm: wrapper.vm as unknown as View }
}

describe('rule groups and persistent order', () => {
  it('collapses a group without losing its rules or folded state when reordered and refreshed', async () => {
    const { wrapper, vm } = await mountView(true)
    const toggle = () => wrapper.find('[data-group-id="1"] .group-toggle')
    await toggle().trigger('click')
    await flushPromises()
    expect(toggle().attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('#group-rules-1').isVisible()).toBe(false)
    expect(wrapper.find('#group-rules-2').isVisible()).toBe(true)
    expect(savePlanLayout).not.toHaveBeenCalled()
    await vm.moveGroup(0, 1)
    expect(savePlanLayout).toHaveBeenLastCalledWith(
      expect.objectContaining({
        groups: [
          { id: 2, plan_ids: [12] },
          { id: 1, plan_ids: [11, 10] },
          { id: 3, plan_ids: [] },
        ],
      }),
    )
    await vm.load()
    await flushPromises()
    expect(wrapper.find('#group-rules-1').isVisible()).toBe(false)
    await toggle().trigger('click')
    await flushPromises()
    expect(wrapper.find('#group-rules-1').isVisible()).toBe(true)
    expect(wrapper.find('#group-rules-1').findAll('[data-plan-id]')).toHaveLength(2)
  })
  it('reveals matches inside a folded group during filtering and restores the fold afterward', async () => {
    const { wrapper, vm } = await mountView(true)
    await wrapper.find('[data-group-id="1"] .group-toggle').trigger('click')
    vm.search = '规则11'
    await flushPromises()
    expect(wrapper.find('#group-rules-1').isVisible()).toBe(true)
    expect(wrapper.find('[data-plan-id="11"]').isVisible()).toBe(true)
    expect(wrapper.find('[data-group-id="1"] .group-toggle').attributes('disabled')).toBeDefined()
    vm.search = ''
    await flushPromises()
    expect(wrapper.find('#group-rules-1').isVisible()).toBe(false)
    expect(savePlanLayout).not.toHaveBeenCalled()
  })
  it('loads empty groups and preserves the saved rule order', async () => {
    const { vm } = await mountView()
    expect(vm.groups.map((group) => group.plans.map((plan) => plan.id))).toEqual([
      [11, 10],
      [12],
      [],
    ])
    expect(vm.canSort).toBe(true)
  })
  it('saves group movement including the default group', async () => {
    const { vm } = await mountView()
    await vm.moveGroup(0, 1)
    expect(savePlanLayout).toHaveBeenCalledWith({
      version: 'v1',
      groups: [
        { id: 2, plan_ids: [12] },
        { id: 1, plan_ids: [11, 10] },
        { id: 3, plan_ids: [] },
      ],
    })
    expect(vm.groups.map((group) => group.id)).toEqual([2, 1, 3])
  })
  it('saves rule order and moves to an empty group', async () => {
    const { vm } = await mountView()
    await vm.movePlan(vm.groups[0]!, 1, -1)
    await vm.moveToGroup(vm.groups[0]!, vm.groups[0]!.plans[0]!, 3)
    expect(vm.groups.map((group) => group.plans.map((plan) => plan.id))).toEqual([[11], [12], [10]])
    expect(savePlanLayout).toHaveBeenLastCalledWith(expect.objectContaining({ version: 'v2' }))
  })
  it('saves a cross-group drag once and ignores a drag without a move', async () => {
    const { vm } = await mountView()
    vm.startDrag()
    await vm.endDrag()
    expect(savePlanLayout).not.toHaveBeenCalled()
    vm.startDrag()
    vm.groups[2]!.plans.push(vm.groups[0]!.plans.splice(0, 1)[0]!)
    await vm.endDrag()
    expect(savePlanLayout).toHaveBeenCalledOnce()
    expect(vm.groups[2]!.plans[0]!.group_id).toBe(3)
  })
  it('pauses all sorting while filtered', async () => {
    const { vm } = await mountView()
    vm.search = '规则11'
    await flushPromises()
    expect(vm.canSort).toBe(false)
    await vm.moveGroup(0, 1)
    await vm.movePlan(vm.groups[0]!, 1, -1)
    await vm.moveToGroup(vm.groups[0]!, vm.groups[0]!.plans[0]!, 3)
    expect(savePlanLayout).not.toHaveBeenCalled()
  })
  it('does not send a drag save after leaving the page before the next render', async () => {
    const { wrapper, vm } = await mountView()
    vm.startDrag()
    vm.groups[2]!.plans.push(vm.groups[0]!.plans.splice(0, 1)[0]!)
    const ending = vm.endDrag()
    wrapper.unmount()
    await ending
    expect(savePlanLayout).not.toHaveBeenCalled()
  })
  it.each([
    new ApiError({ status: 409, code: 'BILL_LAYOUT_CHANGED', message: '分组已变化' }),
    new ApiError({ status: 0, code: 'TIMEOUT', message: '超时' }),
  ])('requires an authoritative reload after an unsuccessful save', async (error) => {
    const { vm } = await mountView()
    vi.mocked(savePlanLayout).mockRejectedValueOnce(error)
    await vm.moveGroup(0, 1)
    expect(vm.groups.map((group) => group.id)).toEqual([1, 2, 3])
    expect(vm.layoutStale).toBe(true)
    expect(vm.canSort).toBe(false)
    await vm.moveGroup(0, 1)
    expect(savePlanLayout).toHaveBeenCalledOnce()
    await vm.load()
    expect(vm.canSort).toBe(true)
    expect(vm.layoutStale).toBe(false)
  })
  it('blocks duplicate saves and discards a late result after unmount', async () => {
    const { wrapper, vm } = await mountView()
    let resolve!: (value: PlanLayout) => void
    vi.mocked(savePlanLayout).mockReturnValue(
      new Promise((done) => {
        resolve = done
      }),
    )
    const saving = vm.moveGroup(0, 1)
    await vm.moveGroup(1, 1)
    expect(savePlanLayout).toHaveBeenCalledOnce()
    expect(vm.saving).toBe(true)
    wrapper.unmount()
    resolve(structuredClone(layout))
    await saving
    expect(ElMessage.success).not.toHaveBeenCalled()
  })
  it('creates and renames groups with trimmed names and a current version', async () => {
    const { vm } = await mountView()
    vi.mocked(ElMessageBox.prompt).mockResolvedValue({
      value: '  家庭  ',
      action: 'confirm',
    } as never)
    vi.mocked(createPlanGroup).mockResolvedValue(layout)
    vi.mocked(renamePlanGroup).mockResolvedValue(layout)
    await vm.changeGroup()
    expect(createPlanGroup).toHaveBeenCalledWith('家庭', 'v1')
    await vm.changeGroup(vm.groups[1])
    expect(renamePlanGroup).toHaveBeenCalledWith(2, '家庭', 'v1')
    await vm.changeGroup(vm.groups[0])
    expect(renamePlanGroup).toHaveBeenCalledOnce()
  })
  it('confirms group deletion with rule preservation and honors cancellation', async () => {
    const { vm } = await mountView()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await vm.changeGroup(vm.groups[1], true)
    expect(deletePlanGroup).not.toHaveBeenCalled()
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
    vi.mocked(deletePlanGroup).mockResolvedValue(layout)
    await vm.changeGroup(vm.groups[1], true)
    expect(ElMessageBox.confirm).toHaveBeenLastCalledWith(
      expect.stringContaining('账单会保留'),
      '删除分组',
      expect.any(Object),
    )
    expect(deletePlanGroup).toHaveBeenCalledWith(2, 'v1')
  })
})

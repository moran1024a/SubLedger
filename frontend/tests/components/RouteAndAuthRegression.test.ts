import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent } from 'vue'
import App from '@/App.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import appRouter from '@/router'
import PlanDetailView from '@/views/plans/PlanDetailView.vue'
import { getPlan, updatePlan } from '@/api/plans'
import { getCurrentUser } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { ElMessageBox } from 'element-plus'
import { ApiError } from '@/types/api'

vi.mock('@/api/plans', () => ({
  getPlan: vi.fn(),
  updatePlan: vi.fn(),
  deletePlan: vi.fn(),
  disablePlan: vi.fn(),
  enablePlan: vi.fn(),
}))
vi.mock('@/api/auth', () => ({ getCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
const plan = {
  id: 1,
  name: 'First plan',
  first_due_date: '2026-10-01',
  cycle_type: 'monthly' as const,
  cycle_days: null,
  amount: '12.00',
  is_enabled: true,
  note: '',
  future_bills_rebuilt: false,
  created_at: '',
  updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
})

it('reused detail route reloads and edits the current plan', async () => {
  vi.mocked(getPlan).mockImplementation(async (id) => ({ ...plan, id }))
  vi.mocked(updatePlan).mockResolvedValue({ ...plan, id: 2 })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/plans/:id', component: PlanDetailView }],
  })
  await router.push('/plans/1')
  await router.isReady()
  const host = mount(defineComponent({ template: '<router-view />' }), {
    global: { plugins: [router], stubs: { BillPlanForm: true, LoadingBlock: true } },
  })
  await flushPromises()
  await router.push('/plans/2')
  await flushPromises()
  expect(getPlan).toHaveBeenCalledTimes(2)
  const vm = host.findComponent(PlanDetailView).vm as unknown as {
    plan: typeof plan
    save: (payload: typeof plan) => Promise<void>
  }
  expect(vm.plan.id).toBe(2)
  await vm.save(plan)
  expect(updatePlan).toHaveBeenCalledWith(2, plan)
  host.unmount()
})

it('temporary auth initialization failure allows a retry', async () => {
  const store = useAuthStore()
  vi.mocked(getCurrentUser).mockRejectedValueOnce(
    new ApiError({ status: 0, code: 'NETWORK', message: 'offline' }),
  )
  await expect(store.initialize()).rejects.toBeInstanceOf(ApiError)
  expect(store.initialized).toBe(false)
  vi.mocked(getCurrentUser).mockRejectedValueOnce(
    new ApiError({ status: 401, code: 'UNAUTHORIZED', message: 'login' }),
  )
  await store.initialize()
  expect(getCurrentUser).toHaveBeenCalledTimes(2)
  expect(store.initialized).toBe(true)
})

const member = {
  id: 1,
  username: 'member',
  role: 'user' as const,
  is_active: true,
  timezone: 'UTC',
  currency_code: 'CNY',
  created_at: '',
  updated_at: '',
}

async function mountAppAt(path: string) {
  await appRouter.replace(path)
  await appRouter.isReady()
  const host = mount(App, { global: { plugins: [appRouter], stubs: { RouterView: true } } })
  await flushPromises()
  return host
}

it.each([
  ['admin', { ...member, id: 0, username: 'admin', role: 'admin' as const }, '/', '/admin'],
  ['expired', null, '/plans', '/login'],
])('re-runs the guards after retrying a failed initialization (%s)', async (_, next, from, to) => {
  vi.mocked(getCurrentUser).mockRejectedValueOnce(
    new ApiError({ status: 0, code: 'NETWORK', message: 'offline' }),
  )
  const host = await mountAppAt(from)
  expect(useAuthStore().initializationError).toBeTruthy()
  expect(appRouter.currentRoute.value.path).toBe(from)

  if (next) vi.mocked(getCurrentUser).mockResolvedValueOnce(next)
  else
    vi.mocked(getCurrentUser).mockRejectedValueOnce(
      new ApiError({ status: 401, code: 'AUTH_SESSION_INVALID', message: '会话失效' }),
    )
  host.findComponent(ErrorState).vm.$emit('retry')
  await flushPromises()

  expect(getCurrentUser).toHaveBeenCalledTimes(2)
  await vi.waitFor(() => expect(appRouter.currentRoute.value.path).toBe(to))
  host.unmount()
})

it('shares initialization and discards a response after logout', async () => {
  const store = useAuthStore()
  let resolve!: (value: Awaited<ReturnType<typeof getCurrentUser>>) => void
  vi.mocked(getCurrentUser).mockReturnValue(
    new Promise((done) => {
      resolve = done
    }),
  )
  const first = store.initialize()
  const second = store.initialize()
  expect(getCurrentUser).toHaveBeenCalledTimes(1)
  store.clear()
  resolve({
    id: 1,
    username: 'old',
    role: 'user',
    is_active: true,
    timezone: 'UTC',
    currency_code: 'CNY',
    created_at: '',
    updated_at: '',
  })
  await Promise.all([first, second])
  expect(store.user).toBeNull()
})

it('does not apply a confirmation opened for a previous route', async () => {
  vi.mocked(getPlan).mockImplementation(async (id) => ({ ...plan, id }))
  let confirm!: () => void
  vi.mocked(ElMessageBox.confirm).mockReturnValue(
    new Promise((resolve) => {
      confirm = () => resolve('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
    }),
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/plans/:id', component: PlanDetailView }],
  })
  await router.push('/plans/1')
  const host = mount(defineComponent({ template: '<router-view />' }), {
    global: { plugins: [router], stubs: { BillPlanForm: true, LoadingBlock: true } },
  })
  await flushPromises()
  const vm = host.findComponent(PlanDetailView).vm as unknown as {
    save: (payload: typeof plan) => Promise<void>
  }
  const saving = vm.save({ ...plan, amount: '20.00' })
  await router.push('/plans/2')
  await flushPromises()
  confirm()
  await saving
  expect(updatePlan).not.toHaveBeenCalled()
  host.unmount()
})

it('ignores late detail responses after navigating to another ID', async () => {
  let resolve!: (value: typeof plan) => void
  vi.mocked(getPlan).mockImplementation((id) =>
    id === 1
      ? new Promise((done) => {
          resolve = done
        })
      : Promise.resolve({ ...plan, id }),
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/plans/:id', component: PlanDetailView }],
  })
  await router.push('/plans/1')
  const host = mount(defineComponent({ template: '<router-view />' }), {
    global: { plugins: [router], stubs: { BillPlanForm: true, LoadingBlock: true } },
  })
  await router.push('/plans/2')
  await flushPromises()
  resolve(plan)
  await flushPromises()
  const vm = host.findComponent(PlanDetailView).vm as unknown as { plan: typeof plan }
  expect(vm.plan.id).toBe(2)
  host.unmount()
})

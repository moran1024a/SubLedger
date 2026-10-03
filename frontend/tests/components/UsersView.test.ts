import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, matchedRouteKey, type Router } from 'vue-router'
import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import UsersView from '@/views/admin/UsersView.vue'
import {
  createUser,
  disableUser,
  enableUser,
  getAdminSummary,
  listUsers,
  resetUserPassword,
} from '@/api/users'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, type CurrentUser } from '@/types/api'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/users', () => ({
  createUser: vi.fn(),
  disableUser: vi.fn(),
  enableUser: vi.fn(),
  getAdminSummary: vi.fn(),
  listUsers: vi.fn(),
  resetUserPassword: vi.fn(),
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

const normalUser: CurrentUser = {
  id: 1,
  username: 'member',
  role: 'user',
  is_active: true,
  timezone: 'UTC',
  currency_code: 'CNY',
  created_at: '',
  updated_at: '',
}

let router: Router
function mountView(renderContent = false) {
  const mountComponent = renderContent ? mount : shallowMount
  return mountComponent(UsersView, {
    global: {
      plugins: [router],
      stubs: renderContent
        ? {
            'el-card': { template: '<section><slot /></section>' },
            'el-table': { props: ['data'], template: '<div class="users-table"><slot /></div>' },
          }
        : {},
      provide: {
        [matchedRouteKey as symbol]: computed(() => router.currentRoute.value.matched[0]),
      },
    },
  })
}
beforeEach(async () => {
  setActivePinia(createPinia())
  useAuthStore().setUser({ ...normalUser, id: 0, role: 'admin' })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/users', component: { template: '<div />' } },
      { path: '/other', component: { template: '<div />' } },
    ],
  })
  await router.push('/admin/users')
  await router.isReady()
  vi.clearAllMocks()
  vi.mocked(listUsers).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  vi.mocked(getAdminSummary).mockResolvedValue({
    total_users: 2,
    active_users: 1,
    inactive_users: 0,
  })
  vi.mocked(createUser).mockResolvedValue(normalUser)
  vi.mocked(disableUser).mockResolvedValue(undefined)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
})

describe('UsersView', () => {
  it('creates a user from a validated form', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      createForm: { username: string; password: string; confirm: string }
      submitCreate: () => Promise<void>
    }
    Object.assign(vm.createForm, {
      username: ' new-user ',
      password: 'password',
      confirm: 'password',
    })

    await vm.submitCreate()
    expect(createUser).toHaveBeenCalledWith({
      username: 'new-user',
      password: 'password',
      timezone: 'UTC',
      currency_code: 'CNY',
    })
  })

  it('shows the complete disable warning before disabling a user', async () => {
    const wrapper = mountView()
    await flushPromises()
    await (wrapper.vm as unknown as { toggle: (user: CurrentUser) => Promise<void> }).toggle(
      normalUser,
    )

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('停用期间的历史不会补处理'),
      expect.any(String),
      expect.any(Object),
    )
    expect(disableUser).toHaveBeenCalledWith(1)
  })
})

it('keeps drafts out of paginated user requests', async () => {
  vi.mocked(listUsers).mockResolvedValue({ items: [normalUser], total: 40, page: 1, page_size: 20 })
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    search: string
    status: string
    page: number
    query: () => void
    load: () => Promise<void>
  }
  vm.search = 'member'
  vm.status = 'active'
  vm.query()
  await flushPromises()
  vm.search = 'unsubmitted'
  vm.page = 2
  await vm.load()
  expect(listUsers).toHaveBeenLastCalledWith(
    {
      q: 'member',
      is_active: true,
      page: 2,
      page_size: 20,
    },
    expect.any(AbortSignal),
  )
})

it('locks creation through the request and prevents closing or leaving mid-submit', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    createForm: { username: string; password: string; confirm: string }
    createVisible: boolean
    openCreate: () => Promise<void>
    submitCreate: () => Promise<void>
    closeCreate: () => Promise<void>
  }
  await vm.openCreate()
  Object.assign(vm.createForm, {
    username: 'member-two',
    password: 'password',
    confirm: 'password',
  })
  let done!: (user: CurrentUser) => void
  vi.mocked(createUser).mockReturnValue(
    new Promise((resolve) => {
      done = resolve
    }),
  )
  const pending = vm.submitCreate()
  await vm.submitCreate()
  await vm.closeCreate()
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  await router.push('/other')
  expect(router.currentRoute.value.path).toBe('/admin/users')
  expect(vm.createVisible).toBe(true)
  expect(createUser).toHaveBeenCalledOnce()
  done(normalUser)
  await pending
  expect(vm.createVisible).toBe(false)
})

it('locks password reset before confirmation and preserves the draft on cancellation', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    resetForm: { password: string; confirm: string }
    resetVisible: boolean
    resetSaving: boolean
    openReset: (user: CurrentUser) => Promise<void>
    submitReset: () => Promise<void>
    closeReset: (done?: () => void) => Promise<void>
  }
  await vm.openReset(normalUser)
  Object.assign(vm.resetForm, { password: 'new-password', confirm: 'new-password' })
  let cancel!: () => void
  vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        cancel = () => reject('cancel')
      }) as never,
  )
  const pending = vm.submitReset()
  await vm.submitReset()
  const done = vi.fn()
  await vm.closeReset(done)
  expect(vm.resetSaving).toBe(true)
  expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
  expect(resetUserPassword).not.toHaveBeenCalled()
  expect(done).not.toHaveBeenCalled()
  cancel()
  await pending
  expect(vm.resetSaving).toBe(false)
  expect(vm.resetVisible).toBe(true)
  expect(vm.resetForm.password).toBe('new-password')
})

it('locks disable before confirmation so repeated clicks cause only one write', async () => {
  const wrapper = mountView()
  await flushPromises()
  let confirm!: () => void
  vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        confirm = () => resolve('confirm' as never)
      }) as never,
  )
  const vm = wrapper.vm as unknown as {
    toggle: (user: CurrentUser) => Promise<void>
    actionId: number | null
  }
  const pending = vm.toggle(normalUser)
  await vm.toggle(normalUser)
  expect(vm.actionId).toBe(normalUser.id)
  expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
  expect(disableUser).not.toHaveBeenCalled()
  confirm()
  await pending
  expect(disableUser).toHaveBeenCalledOnce()
})

it('uses the same discard protection for cancellation, dialog close and navigation', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    createForm: { username: string }
    createVisible: boolean
    dirty: boolean
    openCreate: () => Promise<void>
    closeCreate: (done?: () => void) => Promise<void>
  }
  await vm.openCreate()
  vm.createForm.username = 'draft'
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  const done = vi.fn()
  await vm.closeCreate(done)
  expect(done).not.toHaveBeenCalled()
  expect(vm.createVisible).toBe(true)
  expect(vm.createForm.username).toBe('draft')
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  await router.push('/other')
  expect(router.currentRoute.value.path).toBe('/admin/users')
  expect(vm.dirty).toBe(true)
  await vm.closeCreate(done)
  expect(done).toHaveBeenCalledOnce()
  expect(vm.createVisible).toBe(false)
  expect(vm.dirty).toBe(false)
})

it('treats a changed timezone or currency in the create dialog as unsaved', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    createForm: { timezone: string; currency_code: string }
    dirty: boolean
    openCreate: () => Promise<void>
  }
  await vm.openCreate()
  expect(vm.dirty).toBe(false)
  vm.createForm.timezone = 'Asia/Tokyo'
  expect(vm.dirty).toBe(true)
  vm.createForm.timezone = 'UTC'
  expect(vm.dirty).toBe(false)
  vm.createForm.currency_code = 'USD'
  expect(vm.dirty).toBe(true)
})

it('keeps uncertain creation drafts, never retries automatically and asks before retrying', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    createForm: { username: string; password: string; confirm: string }
    createVisible: boolean
    createMessage: string
    openCreate: () => Promise<void>
    submitCreate: () => Promise<void>
    check: () => Promise<void>
  }
  await vm.openCreate()
  Object.assign(vm.createForm, { username: 'new-user', password: 'password', confirm: 'password' })
  vi.mocked(createUser).mockRejectedValueOnce(new Error('offline'))
  await vm.submitCreate()
  expect(vm.createMessage).toContain('结果待确认')
  expect(vm.createVisible).toBe(true)
  expect(vm.createForm.password).toBe('password')
  expect(ElMessage.error).not.toHaveBeenCalled()
  await vm.check()
  expect(ElMessage.success).not.toHaveBeenCalled()
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  await vm.submitCreate()
  expect(createUser).toHaveBeenCalledOnce()
})

it.each([false, true])(
  'ignores a reset confirmation after the session ends (new session: %s)',
  async (newSession) => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      resetForm: { password: string; confirm: string }
      resetSaving: boolean
      resetVisible: boolean
      openReset: (user: CurrentUser) => Promise<void>
      submitReset: () => Promise<void>
    }
    await vm.openReset(normalUser)
    Object.assign(vm.resetForm, { password: 'new-password', confirm: 'new-password' })
    let confirm!: () => void
    vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          confirm = () => resolve('confirm' as never)
        }) as never,
    )
    const pending = vm.submitReset()
    const auth = useAuthStore()
    auth.clear()
    if (newSession) auth.setUser({ ...normalUser, id: 0, role: 'admin' })
    await flushPromises()
    confirm()
    await pending
    expect(resetUserPassword).not.toHaveBeenCalled()
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(vm.resetSaving).toBe(false)
    expect(vm.resetVisible).toBe(false)
  },
)

it.each([false, true])(
  'ignores a late creation response after the session ends (new session: %s)',
  async (newSession) => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      createForm: { username: string; password: string; confirm: string }
      createVisible: boolean
      createSaving: boolean
      openCreate: () => Promise<void>
      submitCreate: () => Promise<void>
    }
    await vm.openCreate()
    Object.assign(vm.createForm, {
      username: 'old-session-user',
      password: 'password',
      confirm: 'password',
    })
    let done!: (user: CurrentUser) => void
    vi.mocked(createUser).mockReturnValueOnce(
      new Promise((resolve) => {
        done = resolve
      }),
    )
    const pending = vm.submitCreate()
    const auth = useAuthStore()
    auth.clear()
    if (newSession) auth.setUser({ ...normalUser, id: 0, role: 'admin' })
    await flushPromises()
    if (newSession) {
      await vm.openCreate()
      vm.createForm.username = 'new-session-draft'
    }
    done(normalUser)
    await pending
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(vm.createSaving).toBe(false)
    expect(vm.createVisible).toBe(newSession)
    expect(vm.createForm.username).toBe(newSession ? 'new-session-draft' : '')
  },
)

it('renders a local loading overlay without a global loading directive', async () => {
  let done!: (value: Awaited<ReturnType<typeof listUsers>>) => void
  vi.mocked(listUsers).mockReturnValueOnce(
    new Promise((resolve) => {
      done = resolve
    }),
  )
  const wrapper = mountView(true)
  await flushPromises()
  expect(wrapper.find('.users-table .el-loading-mask').exists(), wrapper.html()).toBe(true)
  const vm = wrapper.vm as unknown as { loading: boolean }
  expect(vm.loading).toBe(true)
  done({ items: [normalUser], total: 1, page: 1, page_size: 20 })
  await flushPromises()
  expect(vm.loading).toBe(false)
  expect(wrapper.find('.users-table').exists()).toBe(true)
  await vi.waitFor(() => expect(wrapper.find('.users-table .el-loading-mask').exists()).toBe(false))
})

it('does not open an old reset dialog after a discard confirmation crosses sessions', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    createForm: { username: string }
    createVisible: boolean
    resetVisible: boolean
    selected: CurrentUser | null
    openCreate: () => Promise<void>
    openReset: (user: CurrentUser) => Promise<void>
  }
  await vm.openCreate()
  vm.createForm.username = 'old-session-draft'
  let confirm!: () => void
  vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        confirm = () => resolve('confirm' as never)
      }) as never,
  )
  const pending = vm.openReset(normalUser)
  const auth = useAuthStore()
  auth.clear()
  auth.setUser({ ...normalUser, id: 0, role: 'admin' })
  await flushPromises()
  confirm()
  await pending
  expect(vm.createVisible).toBe(false)
  expect(vm.resetVisible).toBe(false)
  expect(vm.selected).toBeNull()
})

it('submits the chosen timezone and an uppercased custom currency for a new user', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    createForm: { username: string; password: string; confirm: string; timezone: string }
    createFieldErrors: Record<string, string>
    openCreate: () => Promise<void>
    setCreateCurrency: (value: string) => void
    submitCreate: () => Promise<void>
  }
  await vm.openCreate()
  Object.assign(vm.createForm, {
    username: 'member-two',
    password: 'password',
    confirm: 'password',
    timezone: 'Asia/Tokyo',
  })
  vm.setCreateCurrency('bad1')
  await vm.submitCreate()
  expect(vm.createFieldErrors.currency_code).toBe('货币代码需为 3 到 8 位大写字母')
  expect(createUser).not.toHaveBeenCalled()
  vm.setCreateCurrency(' btc ')
  await vm.submitCreate()
  expect(createUser).toHaveBeenCalledWith({
    username: 'member-two',
    password: 'password',
    timezone: 'Asia/Tokyo',
    currency_code: 'BTC',
  })
})

it('asks before enabling a user and keeps the account disabled when cancelled', async () => {
  vi.mocked(enableUser).mockResolvedValue(normalUser)
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as { toggle: (user: CurrentUser) => Promise<void> }
  const inactive = { ...normalUser, is_active: false }
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  await vm.toggle(inactive)
  expect(ElMessageBox.confirm).toHaveBeenCalledWith(
    '启用后会补齐该用户的账单并恢复提醒。确定启用吗？',
    expect.any(String),
    expect.any(Object),
  )
  expect(enableUser).not.toHaveBeenCalled()
  await vm.toggle(inactive)
  expect(enableUser).toHaveBeenCalledWith(1)
})

it('clears each dialog message when that dialog closes', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    createForm: { username: string; password: string; confirm: string }
    createMessage: string
    resetMessage: string
    openCreate: () => Promise<void>
    submitCreate: () => Promise<void>
    closeCreate: () => Promise<void>
  }
  await vm.openCreate()
  Object.assign(vm.createForm, { username: 'taken', password: 'password', confirm: 'password' })
  vi.mocked(createUser).mockRejectedValueOnce(
    new ApiError({ status: 409, code: 'USERNAME_EXISTS', message: '用户名已存在' }),
  )
  await vm.submitCreate()
  expect(vm.createMessage).toBe('用户名已存在')
  expect(vm.resetMessage).toBe('')
  await vm.closeCreate()
  expect(vm.createMessage).toBe('')
})

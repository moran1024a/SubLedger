import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage, ElMessageBox } from 'element-plus'
import UserDetailView from '@/views/admin/UserDetailView.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { disableUser, enableUser, getUser, resetUserPassword, updateUser } from '@/api/users'
import type { CurrentUser } from '@/types/api'

vi.mock('@/api/users', () => ({
  disableUser: vi.fn(),
  enableUser: vi.fn(),
  getUser: vi.fn(),
  resetUserPassword: vi.fn(),
  updateUser: vi.fn(),
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
const user: CurrentUser = {
  id: 1,
  username: 'member',
  role: 'user',
  is_active: true,
  timezone: 'UTC',
  currency_code: 'CNY',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}
type View = {
  user: CurrentUser | null
  form: { username: string; timezone: string; currency_code: string }
  password: { value: string; confirm: string }
  dirty: boolean
  profileDirty: boolean
  resetting: boolean
  saving: boolean
  operationMessage: string
  uncertain: { profile: boolean; password: boolean; status: boolean }
  save: () => Promise<void>
  reset: () => Promise<void>
  toggle: () => Promise<void>
  check: () => Promise<void>
}
let router: Router
let root: VueWrapper
let view: View
beforeEach(async () => {
  vi.clearAllMocks()
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().setUser({ ...user, id: 0, role: 'admin' })
  vi.mocked(getUser).mockImplementation(async (id) => ({
    ...user,
    id,
    username: id === 1 ? 'member' : 'second-user',
  }))
  vi.mocked(updateUser).mockResolvedValue({ ...user })
  vi.mocked(disableUser).mockResolvedValue(undefined)
  vi.mocked(enableUser).mockResolvedValue({ ...user })
  vi.mocked(resetUserPassword).mockResolvedValue(undefined)
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/users/:id', component: UserDetailView },
      { path: '/other', component: { template: '<div />' } },
    ],
  })
  await router.push('/admin/users/1')
  root = mount({ template: '<router-view />' }, { global: { plugins: [pinia, router] } })
  await flushPromises()
  view = root.findComponent(UserDetailView).vm as unknown as View
})

describe('user detail interaction', () => {
  it('updates only the profile baseline with server values after saving', async () => {
    view.form.username = ' normalized '
    Object.assign(view.password, { value: 'password-draft', confirm: 'password-draft' })
    vi.mocked(updateUser).mockResolvedValue({
      ...user,
      username: 'normalized',
      timezone: 'Asia/Shanghai',
      currency_code: 'USD',
    })
    await view.save()
    expect(view.form).toEqual({
      username: 'normalized',
      timezone: 'Asia/Shanghai',
      currency_code: 'USD',
    })
    expect(view.profileDirty).toBe(false)
    expect(view.password.value).toBe('password-draft')
    expect(view.dirty).toBe(true)
  })

  it('updates only the password baseline after resetting', async () => {
    view.form.username = 'profile-draft'
    Object.assign(view.password, { value: 'new-password', confirm: 'new-password' })
    await view.reset()
    expect(view.password).toEqual({ value: '', confirm: '' })
    expect(view.form.username).toBe('profile-draft')
    expect(view.profileDirty).toBe(true)
    expect(view.dirty).toBe(true)
  })

  it('merges disable status without refetching over either draft', async () => {
    view.form.username = 'profile-draft'
    view.password.value = 'password-draft'
    await view.toggle()
    expect(view.user?.is_active).toBe(false)
    expect(view.form.username).toBe('profile-draft')
    expect(view.password.value).toBe('password-draft')
    expect(view.dirty).toBe(true)
    expect(getUser).toHaveBeenCalledOnce()
  })

  it('locks reset before confirmation and keeps the draft when cancelled', async () => {
    Object.assign(view.password, { value: 'new-password', confirm: 'new-password' })
    let cancel!: () => void
    vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          cancel = () => reject('cancel')
        }) as never,
    )
    const pending = view.reset()
    await view.reset()
    expect(view.resetting).toBe(true)
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    cancel()
    await pending
    expect(resetUserPassword).not.toHaveBeenCalled()
    expect(view.password.value).toBe('new-password')
    expect(view.dirty).toBe(true)
  })

  it('does not overwrite the next user or show success for a late profile response', async () => {
    view.form.username = 'old-user-draft'
    let done!: (value: CurrentUser) => void
    vi.mocked(updateUser).mockReturnValue(
      new Promise((resolve) => {
        done = resolve
      }),
    )
    const pending = view.save()
    await router.push('/admin/users/2')
    await flushPromises()
    done({ ...user, username: 'late-old-user' })
    await pending
    expect(view.user?.id).toBe(2)
    expect(view.form.username).toBe('second-user')
    expect(view.saving).toBe(false)
    expect(view.dirty).toBe(false)
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('does not send a confirmed reset if navigation already changed the target', async () => {
    Object.assign(view.password, { value: 'new-password', confirm: 'new-password' })
    let confirm!: () => void
    vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          confirm = () => resolve('confirm' as never)
        }) as never,
    )
    const pending = view.reset()
    await router.push('/admin/users/2')
    await flushPromises()
    confirm()
    await pending
    expect(resetUserPassword).not.toHaveBeenCalled()
    expect(view.user?.id).toBe(2)
    expect(view.password.value).toBe('')
  })

  it('keeps uncertain password results after GET and requires an explicit retry', async () => {
    Object.assign(view.password, { value: 'new-password', confirm: 'new-password' })
    vi.mocked(resetUserPassword).mockRejectedValueOnce(new Error('offline'))
    await view.reset()
    expect(view.operationMessage).toContain('结果待确认')
    expect(view.uncertain.password).toBe(true)
    await view.check()
    expect(view.operationMessage).toContain('不能确认密码是否重置')
    expect(view.uncertain.password).toBe(true)
    expect(view.password.value).toBe('new-password')
    expect(ElMessage.success).not.toHaveBeenCalled()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await view.reset()
    expect(resetUserPassword).toHaveBeenCalledOnce()
    expect(view.operationMessage).toContain('不能确认密码是否重置')
  })

  it('retains the current drafts when switching users is cancelled', async () => {
    view.form.username = 'unsaved-name'
    view.password.value = 'password-draft'
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await router.push('/admin/users/2')
    expect(router.currentRoute.value.path).toBe('/admin/users/1')
    expect(view.form.username).toBe('unsaved-name')
    expect(view.password.value).toBe('password-draft')
    expect(view.dirty).toBe(true)
  })
})

it.each([false, true])(
  'ignores a password confirmation after the session ends (new session: %s)',
  async (newSession) => {
    Object.assign(view.password, { value: 'new-password', confirm: 'new-password' })
    let confirm!: () => void
    vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          confirm = () => resolve('confirm' as never)
        }) as never,
    )
    const pending = view.reset()
    await flushPromises()
    const auth = useAuthStore()
    auth.clear()
    if (newSession) auth.setUser({ ...user, id: 0, role: 'admin' })
    await flushPromises()
    confirm()
    await pending
    expect(resetUserPassword).not.toHaveBeenCalled()
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(view.resetting).toBe(false)
    expect(view.password.value).toBe('')
  },
)

it.each([false, true])(
  'ignores a late profile write after the session ends (new session: %s)',
  async (newSession) => {
    view.form.username = 'old-session-draft'
    let done!: (user: CurrentUser) => void
    vi.mocked(updateUser).mockReturnValueOnce(
      new Promise((resolve) => {
        done = resolve
      }),
    )
    const pending = view.save()
    await flushPromises()
    const auth = useAuthStore()
    auth.clear()
    if (newSession) {
      vi.mocked(getUser).mockResolvedValue({ ...user, username: 'current-session-user' })
      auth.setUser({ ...user, id: 0, role: 'admin' })
    }
    await flushPromises()
    done({ ...user, username: 'late-old-session-user' })
    await pending
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(view.saving).toBe(false)
    expect(view.user?.username ?? null).toBe(newSession ? 'current-session-user' : null)
    expect(view.form.username).toBe(newSession ? 'current-session-user' : '')
  },
)

it('shows current server profile values for an uncertain write while retaining both drafts', async () => {
  view.form.username = 'draft-name'
  view.form.timezone = 'Asia/Tokyo'
  view.form.currency_code = 'JPY'
  view.password.value = 'password-draft'
  vi.mocked(updateUser).mockRejectedValueOnce(new Error('offline'))
  await view.save()
  vi.mocked(getUser).mockResolvedValue({
    ...user,
    username: 'server-name',
    timezone: 'Asia/Shanghai',
    currency_code: 'USD',
  })
  await view.check()
  const message = root.findComponent(OperationFeedback).props('message')
  expect(message).toContain('用户名 server-name')
  expect(message).toContain('时区 Asia/Shanghai')
  expect(message).toContain('货币 USD')
  expect(message).toContain('操作结果仍待确认')
  expect(view.form).toEqual({
    username: 'draft-name',
    timezone: 'Asia/Tokyo',
    currency_code: 'JPY',
  })
  expect(view.password.value).toBe('password-draft')
  expect(view.uncertain.profile).toBe(true)
  expect(view.dirty).toBe(true)
  expect(ElMessage.success).not.toHaveBeenCalled()
})

describe('user detail edge routes', () => {
  async function remount(path: string) {
    root.unmount()
    await router.push(path)
    vi.mocked(getUser).mockClear()
    const wrapper = mount(
      { template: '<router-view />' },
      {
        global: {
          plugins: [router],
          stubs: {
            'el-card': { template: '<section><slot /></section>' },
            'el-form': { template: '<form><slot /></form>' },
            'el-form-item': { template: '<div><slot /></div>' },
          },
        },
      },
    )
    await flushPromises()
    return wrapper
  }

  it('shows an empty state with a way back for an invalid id', async () => {
    const wrapper = await remount('/admin/users/abc')
    expect(getUser).not.toHaveBeenCalled()
    expect(wrapper.findComponent(EmptyState).props('title')).toBe('用户不存在或链接无效')
  })

  it('locks timezone and currency for the administrator and links to its logs', async () => {
    vi.mocked(getUser).mockImplementation(async (id) => ({
      ...user,
      id,
      role: 'admin',
      username: 'admin',
    }))
    const wrapper = await remount('/admin/users/0')
    const selects = wrapper.findAll('el-select-stub')
    expect(selects).toHaveLength(2)
    selects.forEach((select) => expect(select.attributes('disabled')).toBe('true'))
    expect(wrapper.text()).toContain('管理员资料请在个人设置修改')
    const actions = wrapper.findAllComponents({ name: 'ElButton' })
    const logs = actions.find((button) => button.text() === '查看日志') ?? actions[1]!
    const push = vi.spyOn(router, 'push').mockResolvedValue(undefined)
    logs.vm.$emit('click')
    expect(push).toHaveBeenCalledWith({ path: '/admin/logs/users', query: { user_id: '0' } })
  })
})

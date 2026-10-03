import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProfileView from '@/views/settings/ProfileView.vue'
import { useAuthStore } from '@/stores/auth'
import { changePassword, updateProfile } from '@/api/users'
import { getCurrentUser } from '@/api/auth'
import { ApiError, type CurrentUser } from '@/types/api'

vi.mock('@/api/users', () => ({ changePassword: vi.fn(), updateProfile: vi.fn() }))
vi.mock('@/api/auth', () => ({ getCurrentUser: vi.fn() }))
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
  profile: { username: string; timezone: string; currency_code: string }
  password: { current: string; next: string; confirm: string }
  dirty: boolean
  profileDirty: boolean
  passwordSaving: boolean
  profileUncertain: boolean
  profileError: string
  passwordError: string
  saveProfile: () => Promise<void>
  savePassword: () => Promise<void>
  checkProfile: () => Promise<void>
}
let router: Router
let root: VueWrapper
let view: View
beforeEach(async () => {
  vi.clearAllMocks()
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().setUser({ ...user })
  vi.mocked(updateProfile).mockResolvedValue({ ...user })
  vi.mocked(changePassword).mockResolvedValue(undefined)
  vi.mocked(getCurrentUser).mockResolvedValue({ ...user })
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/settings/profile', component: ProfileView },
      { path: '/login', component: { template: '<div>login</div>' } },
      { path: '/other', component: { template: '<div />' } },
    ],
  })
  await router.push('/settings/profile')
  await router.isReady()
  root = mount(
    { template: '<router-view />' },
    {
      global: {
        plugins: [pinia, router],
        stubs: {
          'el-card': { template: '<section><slot name="header" /><slot /></section>' },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
        },
      },
    },
  )
  await flushPromises()
  view = root.findComponent(ProfileView).vm as unknown as View
})

describe('profile drafts and password changes', () => {
  it('fills normalized profile values without clearing the password draft', async () => {
    view.profile.username = ' normalized '
    view.password.next = 'password-draft'
    vi.mocked(updateProfile).mockResolvedValue({
      ...user,
      username: 'normalized',
      timezone: 'Asia/Shanghai',
      currency_code: 'USD',
    })
    await view.saveProfile()
    expect(view.profile).toEqual({
      username: 'normalized',
      timezone: 'Asia/Shanghai',
      currency_code: 'USD',
    })
    expect(useAuthStore().user?.username).toBe('normalized')
    expect(view.profileDirty).toBe(false)
    expect(view.password.next).toBe('password-draft')
    expect(view.dirty).toBe(true)
  })

  it('locks before confirming the loss of a profile draft and keeps both drafts on cancellation', async () => {
    view.profile.username = 'unsaved-name'
    Object.assign(view.password, {
      current: 'old-password',
      next: 'new-password',
      confirm: 'new-password',
    })
    let cancel!: () => void
    vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          cancel = () => reject('cancel')
        }) as never,
    )
    const pending = view.savePassword()
    await view.savePassword()
    expect(view.passwordSaving).toBe(true)
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('个人资料有未保存的修改'),
      expect.any(String),
      expect.any(Object),
    )
    expect(changePassword).not.toHaveBeenCalled()
    cancel()
    await pending
    expect(view.passwordSaving).toBe(false)
    expect(view.profile.username).toBe('unsaved-name')
    expect(view.password.next).toBe('new-password')
    expect(view.dirty).toBe(true)
  })

  it('preserves drafts and the session after failure, and signs out only on success', async () => {
    view.profile.username = 'unsaved-name'
    Object.assign(view.password, {
      current: 'old-password',
      next: 'new-password',
      confirm: 'new-password',
    })
    vi.mocked(changePassword).mockRejectedValueOnce(
      new ApiError({ status: 400, code: 'PASSWORD_INCORRECT', message: '当前密码不正确' }),
    )
    await view.savePassword()
    expect(view.profile.username).toBe('unsaved-name')
    expect(view.password.current).toBe('old-password')
    expect(view.passwordError).toBe('当前密码不正确')
    expect(useAuthStore().user?.id).toBe(1)
    expect(router.currentRoute.value.path).toBe('/settings/profile')
    await view.savePassword()
    expect(useAuthStore().user).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it.each([false, true])(
    'ignores a late profile response after sign-out (switch account: %s)',
    async (switchAccount) => {
      view.profile.username = 'request-draft'
      let done!: (value: CurrentUser) => void
      vi.mocked(updateProfile).mockReturnValue(
        new Promise((resolve) => {
          done = resolve
        }),
      )
      const pending = view.saveProfile()
      const auth = useAuthStore()
      auth.clear()
      if (switchAccount) auth.setUser({ ...user, id: 2, username: 'second-account' })
      done({ ...user, username: 'late-first-account' })
      await pending
      expect(auth.user?.username ?? null).toBe(switchAccount ? 'second-account' : null)
      expect(view.profile.username).toBe(switchAccount ? 'second-account' : '')
      expect(ElMessage.success).not.toHaveBeenCalled()
    },
  )

  it('keeps an uncertain save visible when a retry confirmation is cancelled', async () => {
    view.profile.username = 'unsaved-name'
    vi.mocked(updateProfile).mockRejectedValueOnce(new Error('offline'))
    await view.saveProfile()
    expect(view.profileUncertain).toBe(true)
    expect(view.profileError).toContain('结果待确认')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await view.saveProfile()
    expect(updateProfile).toHaveBeenCalledOnce()
    expect(view.profileError).toContain('结果待确认')
    expect(view.profile.username).toBe('unsaved-name')
    await view.saveProfile()
    expect(updateProfile).toHaveBeenCalledTimes(2)
    expect(view.profileUncertain).toBe(false)
    expect(view.profileError).toBe('')
  })

  it('reads current profile data for comparison while retaining drafts and the uncertain result', async () => {
    view.profile.username = 'unsaved-name'
    view.password.next = 'password-draft'
    vi.mocked(updateProfile).mockRejectedValueOnce(new Error('offline'))
    await view.saveProfile()
    vi.mocked(getCurrentUser).mockResolvedValue({ ...user, username: 'server-name' })
    await view.checkProfile()
    expect(view.profile.username).toBe('unsaved-name')
    expect(view.password.next).toBe('password-draft')
    expect(view.profileError).toContain('server-name')
    expect(view.profileUncertain).toBe(true)
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('retains draft protection when navigation is cancelled', async () => {
    view.profile.username = 'unsaved-name'
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await router.push('/other')
    expect(router.currentRoute.value.path).toBe('/settings/profile')
    expect(view.profile.username).toBe('unsaved-name')
    expect(view.dirty).toBe(true)
  })
})

it('keeps an uncertain password change recoverable without signing out or silently retrying', async () => {
  Object.assign(view.password, {
    current: 'old-password',
    next: 'new-password',
    confirm: 'new-password',
  })
  vi.mocked(changePassword).mockRejectedValueOnce(new Error('offline'))
  await view.savePassword()
  expect(view.passwordError).toContain('结果待确认')
  expect(useAuthStore().user?.id).toBe(1)
  expect(root.text()).toContain('隐私窗口')
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  await view.savePassword()
  expect(changePassword).toHaveBeenCalledOnce()
  expect(view.passwordError).toContain('结果待确认')
  expect(view.password.next).toBe('new-password')
})

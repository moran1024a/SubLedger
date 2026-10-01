import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory, type Router } from 'vue-router'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import NotificationsView from '@/views/settings/NotificationsView.vue'
import { getNotificationSettings, saveNotificationSettings, testEmail } from '@/api/notifications'
import { ApiError, type NotificationSettings } from '@/types/api'
import ErrorState from '@/components/common/ErrorState.vue'

vi.mock('@/api/notifications', () => ({
  getNotificationSettings: vi.fn(),
  saveNotificationSettings: vi.fn(),
  testEmail: vi.fn(),
  testFeishu: vi.fn(),
}))
vi.mock('@/composables/useUnsavedChanges', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/composables/useUnsavedChanges')>()),
  useUnsavedChanges: () => ({ dirty: ref(false) }),
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

const settings: NotificationSettings = {
  email_enabled: true,
  smtp_host: 'smtp.example.com',
  smtp_port: 465,
  smtp_security: 'ssl',
  smtp_username: 'user',
  smtp_password_configured: true,
  sender_email: 'sender@example.com',
  sender_name: 'SubLedger',
  recipient_email: 'receiver@example.com',
  feishu_enabled: true,
  feishu_webhook_configured: true,
  feishu_secret_configured: true,
  advance_enabled: true,
  advance_days: 3,
  advance_time: '09:00:00',
  same_day_enabled: true,
  same_day_time: '08:30:00',
}

function mountView() {
  return shallowMount(NotificationsView, {
    global: {
      plugins: [router],
      stubs: {
        PageHeader: { template: '<header><slot name="actions" /></header>' },
        LoadingBlock: true,
        ErrorState: true,
        'el-button': {
          props: ['disabled', 'loading'],
          template:
            '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
        },
      },
    },
  })
}

let router: Router
beforeEach(async () => {
  setActivePinia(createPinia())
  router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/settings/notifications', component: { template: '<div />' } }],
  })
  await router.push('/settings/notifications')
  await router.isReady()
  vi.clearAllMocks()
  vi.mocked(getNotificationSettings).mockResolvedValue(settings)
  vi.mocked(saveNotificationSettings).mockResolvedValue(settings)
})

describe('NotificationsView', () => {
  it('blocks the button and save handler until initial settings have loaded', async () => {
    let resolve!: (value: NotificationSettings) => void
    vi.mocked(getNotificationSettings).mockReturnValue(new Promise((done) => (resolve = done)))
    const wrapper = mountView()
    const vm = wrapper.vm as unknown as { save: () => Promise<void> }

    expect(wrapper.find('button').element.disabled).toBe(true)
    await vm.save()
    expect(saveNotificationSettings).not.toHaveBeenCalled()

    resolve(settings)
    await flushPromises()
    expect(wrapper.find('button').element.disabled).toBe(false)
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(saveNotificationSettings).toHaveBeenCalledOnce()
  })

  it('blocks saving after a load error and enables it after a successful retry', async () => {
    vi.mocked(getNotificationSettings).mockRejectedValueOnce(
      new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '加载失败' }),
    )
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as { save: () => Promise<void> }

    expect(wrapper.find('button').element.disabled).toBe(true)
    await vm.save()
    expect(saveNotificationSettings).not.toHaveBeenCalled()

    wrapper.findComponent(ErrorState).vm.$emit('retry')
    await flushPromises()
    expect(getNotificationSettings).toHaveBeenCalledTimes(2)
    expect(wrapper.find('button').element.disabled).toBe(false)
    await vm.save()
    expect(saveNotificationSettings).toHaveBeenCalledOnce()
  })

  it('preserves existing secrets by omitting empty sensitive inputs', async () => {
    const wrapper = shallowMount(NotificationsView, {
      global: {
        plugins: [router],
        stubs: { PageHeader: true, LoadingBlock: true, ErrorState: true },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      form: { smtp_password: string; feishu_webhook: string; feishu_secret: string }
      payload: () => Record<string, unknown>
      save: () => Promise<void>
    }

    expect(vm.form.smtp_password).toBe('')
    expect(vm.form.feishu_webhook).toBe('')
    expect(vm.payload()).not.toHaveProperty('smtp_password')
    expect(vm.payload()).not.toHaveProperty('feishu_webhook')
    expect(vm.payload()).not.toHaveProperty('feishu_secret')

    await vm.save()
    expect(saveNotificationSettings).toHaveBeenCalledWith(
      expect.objectContaining({ advance_time: '09:00:00', same_day_time: '08:30:00' }),
    )
  })

  it('does not submit an enabled channel with missing required fields', async () => {
    vi.mocked(getNotificationSettings).mockResolvedValue({ ...settings, email_enabled: false })
    const wrapper = shallowMount(NotificationsView, {
      global: {
        plugins: [router],
        stubs: { PageHeader: true, LoadingBlock: true, ErrorState: true },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      form: { email_enabled: boolean; smtp_host: string }
      fieldErrors: Record<string, string>
      save: () => Promise<void>
    }
    vm.form.email_enabled = true
    vm.form.smtp_host = ''
    await vm.save()

    expect(vm.fieldErrors.smtp_host).toBeTruthy()
    expect(saveNotificationSettings).not.toHaveBeenCalled()
  })
})

it('tests the unsaved draft, gates saving, and invalidates a proof when the secret changes', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    form: { smtp_password: string; advance_days: number }
    blockedByTest: string[]
    proofs: { email: { token: string } }
    test: (kind: 'email') => Promise<void>
    save: () => Promise<void>
  }
  vm.form.smtp_password = 'new-secret'
  await flushPromises()
  expect(vm.blockedByTest).toEqual(['email'])
  await vm.save()
  expect(saveNotificationSettings).not.toHaveBeenCalled()
  vi.mocked(testEmail).mockResolvedValue({
    channel: 'email',
    verification_token: 'proof',
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  })
  await vm.test('email')
  expect(testEmail).toHaveBeenCalledWith(expect.objectContaining({ smtp_password: 'new-secret' }))
  expect(saveNotificationSettings).not.toHaveBeenCalled()
  expect(vm.blockedByTest).toEqual([])
  vm.form.advance_days = 8
  expect(vm.blockedByTest).toEqual([])
  vm.form.smtp_password = 'different-secret'
  await flushPromises()
  expect(vm.proofs.email.token).toBe('')
  expect(vm.blockedByTest).toEqual(['email'])
  await vm.test('email')
  await vm.save()
  expect(saveNotificationSettings).toHaveBeenCalledWith(
    expect.objectContaining({
      smtp_password: 'different-secret',
      email_verification_token: 'proof',
      advance_days: 8,
    }),
  )
})

it('ignores a successful test that belongs to an older draft', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    form: { smtp_password: string }
    proofs: { email: { token: string } }
    test: (kind: 'email') => Promise<void>
  }
  let done!: (value: Awaited<ReturnType<typeof testEmail>>) => void
  vi.mocked(testEmail).mockReturnValue(
    new Promise((resolve) => {
      done = resolve
    }),
  )
  vm.form.smtp_password = 'draft-one'
  const pending = vm.test('email')
  vm.form.smtp_password = 'draft-two'
  done({
    channel: 'email',
    verification_token: 'stale',
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  })
  await pending
  expect(vm.proofs.email.token).toBe('')
})

it('does not silently save default SMTP values when editing only reminder timing', async () => {
  vi.mocked(getNotificationSettings).mockResolvedValue({
    ...settings,
    email_enabled: false,
    feishu_enabled: false,
    smtp_host: null,
    smtp_port: null,
    smtp_security: null,
    sender_email: null,
    recipient_email: null,
  })
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as { form: { advance_days: number }; save: () => Promise<void> }
  vm.form.advance_days = 5
  await vm.save()
  const payload = vi.mocked(saveNotificationSettings).mock.calls[0]![0]
  expect(payload.advance_days).toBe(5)
  expect(payload).not.toHaveProperty('smtp_port')
  expect(payload).not.toHaveProperty('smtp_security')
})

it('expires a passed draft and prevents saving after its deadline', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    form: { smtp_password: string }
    proofs: { email: { token: string } }
    test: (kind: 'email') => Promise<void>
    save: () => Promise<void>
  }
  vi.useFakeTimers()
  try {
    vm.form.smtp_password = 'changed-secret'
    vi.mocked(testEmail).mockResolvedValue({
      channel: 'email',
      verification_token: 'proof',
      expires_at: new Date(Date.now() + 600_000).toISOString(),
    })
    await vm.test('email')
    expect(vm.proofs.email.token).toBe('proof')
    await vi.advanceTimersByTimeAsync(600_001)
    await vm.save()
    expect(vm.proofs.email.token).toBe('')
    expect(saveNotificationSettings).not.toHaveBeenCalled()
  } finally {
    vi.useRealTimers()
  }
})

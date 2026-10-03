import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory, matchedRouteKey, type Router } from 'vue-router'
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime } from '@/utils/format'
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
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
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
      provide: {
        [matchedRouteKey as symbol]: computed(() => router.currentRoute.value.matched[0]),
      },
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
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
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
        provide: {
          [matchedRouteKey as symbol]: computed(() => router.currentRoute.value.matched[0]),
        },
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
        provide: {
          [matchedRouteKey as symbol]: computed(() => router.currentRoute.value.matched[0]),
        },
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

it('shows the server deadline instead of assuming ten minutes', async () => {
  const wrapper = mountView()
  await flushPromises()
  const expiresAt = new Date(Date.now() + 120_000).toISOString()
  vi.mocked(testEmail).mockResolvedValue({
    channel: 'email',
    verification_token: 'short-proof',
    expires_at: expiresAt,
  })
  const vm = wrapper.vm as unknown as {
    test: (kind: 'email') => Promise<void>
    statusText: (kind: 'email') => string
  }
  await vm.test('email')
  expect(vm.statusText('email')).toContain(formatDateTime(expiresAt))
  expect(vm.statusText('email')).not.toContain('10 分钟')
})

it.each([
  ['NOTIFICATION_TEST_BUSY', '测试通道繁忙'],
  ['NOTIFICATION_TEST_RATE_LIMITED', '等待冷却'],
])('explains %s without retrying or inventing a countdown', async (code, message) => {
  const wrapper = mountView()
  await flushPromises()
  vi.mocked(testEmail).mockRejectedValue(new ApiError({ status: 429, code, message: 'limited' }))
  const vm = wrapper.vm as unknown as {
    test: (kind: 'email') => Promise<void>
    statusText: (kind: 'email') => string
  }
  await vm.test('email')
  expect(vm.statusText('email')).toContain(message)
  expect(vm.statusText('email')).not.toMatch(/\d+.*秒/)
  expect(testEmail).toHaveBeenCalledOnce()
})

it('ignores late tests after unmount without creating expiry timers or messages', async () => {
  const wrapper = mountView()
  await flushPromises()
  let done!: (value: Awaited<ReturnType<typeof testEmail>>) => void
  vi.mocked(testEmail).mockReturnValue(
    new Promise((resolve) => {
      done = resolve
    }),
  )
  const pending = (wrapper.vm as unknown as { test: (kind: 'email') => Promise<void> }).test(
    'email',
  )
  wrapper.unmount()
  vi.useFakeTimers()
  try {
    done({
      channel: 'email',
      verification_token: 'late',
      expires_at: new Date(Date.now() + 120_000).toISOString(),
    })
    await pending
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  } finally {
    vi.useRealTimers()
  }
})

it('preserves the draft and dirty state when a confirmed reload fails', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    form: { smtp_password: string }
    dirty: boolean
    reload: () => Promise<void>
  }
  vm.form.smtp_password = 'unsaved-secret'
  vi.mocked(getNotificationSettings).mockRejectedValueOnce(new Error('offline'))
  await vm.reload()
  expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
  expect(vm.form.smtp_password).toBe('unsaved-secret')
  expect(vm.dirty).toBe(true)
})

it('does not confirm an uncertain secret write from GET and locks its explicit retry confirmation', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    form: { smtp_password: string }
    save: () => Promise<void>
    test: (kind: 'email') => Promise<void>
    reload: () => Promise<void>
    operationMessage: string
    saveUncertain: boolean
  }
  vm.form.smtp_password = 'new-secret'
  vi.mocked(testEmail).mockResolvedValue({
    channel: 'email',
    verification_token: 'proof',
    expires_at: new Date(Date.now() + 120_000).toISOString(),
  })
  await vm.test('email')
  vi.mocked(ElMessage.success).mockClear()
  vi.mocked(saveNotificationSettings).mockRejectedValueOnce(new Error('offline'))
  await vm.save()
  expect(vm.saveUncertain).toBe(true)
  await vm.reload()
  expect(vm.operationMessage).toContain('无法确认本次密码或密钥是否保存')
  expect(vm.saveUncertain).toBe(true)
  expect(ElMessage.success).not.toHaveBeenCalled()
  let confirm!: () => void
  vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        confirm = () => resolve('confirm' as never)
      }) as never,
  )
  const pending = vm.save()
  await vm.save()
  expect(saveNotificationSettings).toHaveBeenCalledTimes(1)
  confirm()
  await pending
  expect(saveNotificationSettings).toHaveBeenCalledTimes(2)
})

it('checks expiry again after retry confirmation even if the timer has not run', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    form: { smtp_password: string }
    test: (kind: 'email') => Promise<void>
    save: () => Promise<void>
    operationMessage: string
  }
  vi.useFakeTimers()
  try {
    vm.form.smtp_password = 'new-secret'
    vi.mocked(testEmail).mockResolvedValue({
      channel: 'email',
      verification_token: 'proof',
      expires_at: new Date(Date.now() + 1000).toISOString(),
    })
    await vm.test('email')
    vi.mocked(saveNotificationSettings).mockRejectedValueOnce(new Error('offline'))
    await vm.save()
    let confirm!: () => void
    vi.mocked(ElMessageBox.confirm).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          confirm = () => resolve('confirm' as never)
        }) as never,
    )
    const pending = vm.save()
    vi.setSystemTime(Date.now() + 1001)
    confirm()
    await pending
    expect(saveNotificationSettings).toHaveBeenCalledOnce()
    expect(vm.operationMessage).toContain('已过期')
  } finally {
    wrapper.unmount()
    vi.useRealTimers()
  }
})

it('asks again before a retry can replace a draft retained after a failed reload', async () => {
  const wrapper = mountView()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    form: { smtp_password: string }
    dirty: boolean
    reload: () => Promise<void>
  }
  vm.form.smtp_password = 'draft-secret'
  vi.mocked(getNotificationSettings).mockRejectedValueOnce(new Error('offline'))
  await vm.reload()
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  wrapper.findComponent(ErrorState).vm.$emit('retry')
  await flushPromises()
  expect(getNotificationSettings).toHaveBeenCalledTimes(2)
  expect(vm.form.smtp_password).toBe('draft-secret')
  expect(vm.dirty).toBe(true)
})

describe('channel cards', () => {
  it('keeps the save button enabled for an untested change and explains the block on save', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      form: { smtp_password: string }
      operationMessage: string
    }
    vm.form.smtp_password = 'changed-secret'
    await flushPromises()
    const saveButton = wrapper.find('button')
    expect(saveButton.text()).toBe('保存设置')
    expect(saveButton.element.disabled).toBe(false)
    await saveButton.trigger('click')
    await flushPromises()
    expect(saveNotificationSettings).not.toHaveBeenCalled()
    expect(vm.operationMessage).toBe('请先测试通过当前修改的邮件配置')
  })

  it('reverts a disabled channel and saves it without a test or channel fields', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      form: { email_enabled: boolean; smtp_host: string; smtp_password: string }
      blockedByTest: string[]
      save: () => Promise<void>
    }
    vm.form.smtp_host = 'changed.example.com'
    vm.form.smtp_password = 'changed-secret'
    expect(vm.blockedByTest).toEqual(['email'])
    vm.form.email_enabled = false
    expect(vm.form.smtp_host).toBe('smtp.example.com')
    expect(vm.form.smtp_password).toBe('')
    expect(vm.blockedByTest).toEqual([])
    await vm.save()
    const payload = vi.mocked(saveNotificationSettings).mock.calls[0]![0]
    expect(payload.email_enabled).toBe(false)
    expect(payload).not.toHaveProperty('smtp_host')
    expect(payload).not.toHaveProperty('email_verification_token')
  })

  it('restores loaded channel values and clears the proof when reverting manually', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      form: { smtp_username: string; smtp_password: string }
      proofs: { email: { token: string } }
      channelBaseline: { email: string }
      fingerprint: (kind: 'email') => string
      test: (kind: 'email') => Promise<void>
      revertChannel: (kind: 'email') => void
    }
    vm.form.smtp_username = 'other-user'
    vm.form.smtp_password = 'secret'
    vi.mocked(testEmail).mockResolvedValue({
      channel: 'email',
      verification_token: 'proof',
      expires_at: new Date(Date.now() + 600_000).toISOString(),
    })
    await vm.test('email')
    expect(vm.proofs.email.token).toBe('proof')
    vm.revertChannel('email')
    expect(vm.form.smtp_username).toBe('user')
    expect(vm.form.smtp_password).toBe('')
    expect(vm.fingerprint('email')).toBe(vm.channelBaseline.email)
    expect(vm.proofs.email.token).toBe('')
  })

  it('describes channels that were never configured', async () => {
    vi.mocked(getNotificationSettings).mockResolvedValue({
      ...settings,
      email_enabled: false,
      smtp_host: null,
      feishu_enabled: false,
      feishu_webhook_configured: false,
      feishu_secret_configured: false,
    })
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as { statusText: (kind: 'email' | 'feishu') => string }
    expect(vm.statusText('email')).toBe('尚未配置，启用后需测试通过才能保存')
    expect(vm.statusText('feishu')).toBe('尚未配置，启用后需测试通过才能保存')
  })

  it('clears a field error as soon as that field changes', async () => {
    vi.mocked(getNotificationSettings).mockResolvedValue({ ...settings, email_enabled: false })
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      form: { email_enabled: boolean; smtp_host: string; sender_email: string }
      fieldErrors: Record<string, string>
      save: () => Promise<void>
    }
    vm.form.email_enabled = true
    vm.form.smtp_host = ''
    vm.form.sender_email = ''
    await vm.save()
    expect(ElMessage.error).toHaveBeenCalled()
    expect(vm.fieldErrors.smtp_host).toBeTruthy()
    expect(vm.fieldErrors.sender_email).toBeTruthy()
    vm.form.smtp_host = 'smtp.example.com'
    expect(vm.fieldErrors.smtp_host).toBeUndefined()
    expect(vm.fieldErrors.sender_email).toBeTruthy()
  })
})

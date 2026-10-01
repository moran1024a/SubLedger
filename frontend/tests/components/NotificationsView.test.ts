import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import NotificationsView from '@/views/settings/NotificationsView.vue'
import { getNotificationSettings, saveNotificationSettings } from '@/api/notifications'
import { ApiError, type NotificationSettings } from '@/types/api'
import ErrorState from '@/components/common/ErrorState.vue'

vi.mock('@/api/notifications', () => ({
  getNotificationSettings: vi.fn(),
  saveNotificationSettings: vi.fn(),
  testEmail: vi.fn(),
  testFeishu: vi.fn(),
}))
vi.mock('@/composables/useUnsavedChanges', () => ({
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

beforeEach(() => {
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
      global: { stubs: { PageHeader: true, LoadingBlock: true, ErrorState: true } },
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
      global: { stubs: { PageHeader: true, LoadingBlock: true, ErrorState: true } },
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

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminHomeView from '@/views/admin/AdminHomeView.vue'
import NotificationRecords from '@/components/notifications/NotificationRecords.vue'
import { getAdminSummary, getHealth, getRuntime } from '@/api/users'
import { listNotificationRecords } from '@/api/notifications'

vi.mock('@/api/users', () => ({
  getAdminSummary: vi.fn(),
  getHealth: vi.fn(),
  getRuntime: vi.fn(),
}))
vi.mock('@/api/notifications', () => ({ listNotificationRecords: vi.fn() }))
const TaskTable = { props: ['data'], template: '<div>{{ JSON.stringify(data) }}</div>' }

beforeEach(() => {
  vi.clearAllMocks()
})
describe('runtime status', () => {
  it('shows task health when account statistics fail', async () => {
    vi.mocked(getAdminSummary).mockRejectedValue(new Error('offline'))
    vi.mocked(getHealth).mockResolvedValue({
      status: 'degraded',
      application: 'ok',
      database: 'ok',
      scheduler: 'error',
    })
    vi.mocked(getRuntime).mockResolvedValue({
      status: 'error',
      tasks: [
        {
          id: 'notification_check',
          name: '通知检查',
          status: 'error',
          next_run_at: null,
          last_started_at: null,
          last_finished_at: null,
          last_success_at: null,
          duration_seconds: 30,
          consecutive_failures: 3,
          last_error: 'DatabaseError',
          counts: null,
        },
      ],
    })
    const wrapper = mount(AdminHomeView, {
      global: { stubs: { 'el-table': TaskTable, 'el-card': { template: '<div><slot /></div>' } } },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('通知检查')
    expect(wrapper.text()).toContain('DatabaseError')
    wrapper.unmount()
  })
})

describe('notification records queries', () => {
  it('cancels stale queries and uses submitted filters when paging', async () => {
    vi.mocked(listNotificationRecords).mockResolvedValue({
      items: [],
      total: 45,
      page: 1,
      page_size: 20,
    })
    const wrapper = mount(NotificationRecords, { global: { plugins: [createPinia()] } })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      channel: string
      status: string
      page: number
      query: () => Promise<void>
      load: () => Promise<void>
    }
    vm.channel = 'email'
    vm.query()
    await flushPromises()
    vm.channel = 'feishu'
    vm.page = 2
    await vm.load()
    expect(listNotificationRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ channel: 'email', page: 2 }),
      expect.any(AbortSignal),
    )
    const signal = vi.mocked(listNotificationRecords).mock.calls.at(-1)![1]!
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
  })
})

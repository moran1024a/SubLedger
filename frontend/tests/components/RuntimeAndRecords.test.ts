import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import StatusTag from '@/components/common/StatusTag.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
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
      global: {
        plugins: [createPinia()],
        stubs: { 'el-table': TaskTable, 'el-card': { template: '<div><slot /></div>' } },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('通知检查')
    expect(wrapper.text()).toContain('DatabaseError')
    wrapper.unmount()
  })
})

describe('admin home timezone and task results', () => {
  const successAt = '2026-07-20T00:30:00Z'
  function runtimeWithError() {
    return {
      status: 'error' as const,
      tasks: [
        {
          id: 'notification_check',
          name: '通知检查',
          status: 'warning' as const,
          next_run_at: null,
          last_started_at: null,
          last_finished_at: null,
          last_success_at: successAt,
          duration_seconds: 2,
          consecutive_failures: 1,
          last_error: 'SMTPException',
          counts: { sent: 3, failed: 1, unknown: 0 },
        },
      ],
    }
  }
  function mountHome() {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().setUser({
      id: 0,
      username: 'admin',
      role: 'admin',
      is_active: true,
      timezone: 'Asia/Tokyo',
      currency_code: 'CNY',
      created_at: '',
      updated_at: '',
    })
    return mount(AdminHomeView, {
      global: {
        plugins: [pinia],
        stubs: { 'el-table': true, 'el-card': { template: '<div><slot /></div>' } },
      },
    })
  }
  beforeEach(() => {
    vi.mocked(getAdminSummary).mockResolvedValue({
      total_users: 2,
      active_users: 1,
      inactive_users: 0,
    })
    vi.mocked(getHealth).mockResolvedValue({
      status: 'ok',
      application: 'ok',
      database: 'ok',
      scheduler: 'ok',
    })
    vi.mocked(getRuntime).mockResolvedValue(runtimeWithError())
  })

  it('formats task times in the account timezone and keeps counts beside the error tag', async () => {
    const wrapper = mountHome()
    await flushPromises()
    expect(formatDateTime(successAt, 'Asia/Tokyo')).not.toBe(formatDateTime(successAt, 'UTC'))
    expect(wrapper.text()).toContain('时间按账户时区 Asia/Tokyo 显示')
    expect(wrapper.text()).toContain(formatDateTime(successAt, 'Asia/Tokyo'))
    expect(wrapper.text()).toContain('成功 3，失败 1，未知 0')
    expect(wrapper.text()).toMatch(/数据获取于 \d{2}:\d{2}/)
    const tag = wrapper
      .findAllComponents(StatusTag)
      .find((item) => item.props('tone') === 'danger')!
    expect(tag.attributes('title')).toBe('SMTPException')
    expect(wrapper.find('.error-class').text()).toBe('SMTPException')
  })

  it('keeps the loaded tasks visible while refreshing', async () => {
    const wrapper = mountHome()
    await flushPromises()
    vi.mocked(getRuntime).mockReturnValue(new Promise(() => {}))
    void (wrapper.vm as unknown as { load: () => Promise<void> }).load()
    await flushPromises()
    expect(wrapper.findComponent(LoadingBlock).exists()).toBe(false)
    expect(wrapper.text()).toContain('通知检查')
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
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/settings/notifications', component: { template: '<div />' } }],
    })
    await router.push('/settings/notifications?tab=records')
    await router.isReady()
    const wrapper = mount(NotificationRecords, { global: { plugins: [createPinia(), router] } })
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

it('resets draft inputs and queries once even when canonical filters are unchanged', async () => {
  vi.mocked(listNotificationRecords).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/settings/notifications', component: { template: '<div />' } }],
  })
  await router.push('/settings/notifications?tab=records&page=invalid')
  const wrapper = mount(NotificationRecords, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    channel: string
    status: string
    dates: string[] | null
    reset: () => void
    load: () => Promise<void>
  }
  vm.channel = 'email'
  vm.status = 'failed'
  vm.dates = ['2026-01-01', '2026-02-01']
  vm.reset()
  await flushPromises()
  expect(vm.channel).toBe('')
  expect(vm.status).toBe('')
  expect(vm.dates).toBeNull()
  expect(listNotificationRecords).toHaveBeenCalledTimes(2)
  vm.reset()
  await flushPromises()
  expect(listNotificationRecords).toHaveBeenCalledTimes(3)
  vm.channel = 'feishu'
  await vm.load()
  expect(listNotificationRecords).toHaveBeenLastCalledWith(
    { page: 1, page_size: 20 },
    expect.any(AbortSignal),
  )
})

it('restores notification filters from URL history after a new query', async () => {
  vi.mocked(listNotificationRecords).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/settings/notifications', component: { template: '<div />' } }],
  })
  await router.push(
    '/settings/notifications?tab=records&channel=email&status=failed&start_date=2026-01-01&end_date=2026-02-01',
  )
  const wrapper = mount(NotificationRecords, { global: { plugins: [createPinia(), router] } })
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    channel: string
    status: string
    dates: string[] | null
    query: () => void
  }
  expect(vm.channel).toBe('email')
  expect(vm.status).toBe('failed')
  vm.channel = 'feishu'
  vm.status = 'sent'
  vm.query()
  await flushPromises()
  router.back()
  await flushPromises()
  expect(vm.channel).toBe('email')
  expect(vm.status).toBe('failed')
  expect(vm.dates).toEqual(['2026-01-01', '2026-02-01'])
  expect(listNotificationRecords).toHaveBeenLastCalledWith(
    expect.objectContaining({ channel: 'email', status: 'failed', start_date: '2026-01-01' }),
    expect.any(AbortSignal),
  )
})

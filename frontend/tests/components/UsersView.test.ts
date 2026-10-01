import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import UsersView from '@/views/admin/UsersView.vue'
import { createUser, disableUser, getAdminSummary, listUsers } from '@/api/users'
import { ElMessageBox } from 'element-plus'
import type { CurrentUser } from '@/types/api'

vi.mock('@/api/users', () => ({
  createUser: vi.fn(),
  disableUser: vi.fn(),
  enableUser: vi.fn(),
  getAdminSummary: vi.fn(),
  listUsers: vi.fn(),
  resetUserPassword: vi.fn(),
}))
vi.mock('element-plus', () => ({
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

beforeEach(() => {
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
    const wrapper = shallowMount(UsersView, {
      global: {
        stubs: {
          PageHeader: true,
          ErrorState: true,
          EmptyState: true,
          StatusTag: true,
          'el-card': true,
          'el-table': true,
          'el-table-column': true,
          'el-dialog': true,
        },
      },
    })
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
    expect(createUser).toHaveBeenCalledWith({ username: 'new-user', password: 'password' })
  })

  it('shows the complete disable warning before disabling a user', async () => {
    const wrapper = shallowMount(UsersView, {
      global: {
        stubs: {
          PageHeader: true,
          ErrorState: true,
          EmptyState: true,
          StatusTag: true,
          'el-card': true,
          'el-table': true,
          'el-table-column': true,
          'el-dialog': true,
        },
      },
    })
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
  const wrapper = shallowMount(UsersView)
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
  expect(listUsers).toHaveBeenLastCalledWith({
    q: 'member',
    is_active: true,
    page: 2,
    page_size: 20,
  })
})

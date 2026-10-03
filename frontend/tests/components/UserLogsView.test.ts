import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import UserLogsView from '@/views/admin/UserLogsView.vue'
import { downloadUserLog, getUserLogs, saveBlob } from '@/api/logs'
import { getUser, listUsers } from '@/api/users'
import { ApiError, type LogFile } from '@/types/api'
import EmptyState from '@/components/common/EmptyState.vue'
import LogFileTable from '@/components/logs/LogFileTable.vue'

const route = vi.hoisted(() => ({ query: {} as Record<string, string> }))
const router = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => router }))
vi.mock('@/api/users', () => ({ listUsers: vi.fn(), getUser: vi.fn() }))
vi.mock('@/api/logs', () => ({ getUserLogs: vi.fn(), downloadUserLog: vi.fn(), saveBlob: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { error: vi.fn() },
}))

const file: LogFile = { date: '2026-09-30', filename: '2026-09-30.log', size: 10, modified_at: '' }

interface UserLogsVm {
  selectedId: number | undefined
  files: LogFile[]
  loading: boolean
  error: ApiError | null
  downloadFile: (filename?: string) => Promise<void>
}

function deferred() {
  let resolve!: (value: LogFile[]) => void
  let reject!: (cause: unknown) => void
  const promise = new Promise<LogFile[]>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

function mountView() {
  return shallowMount(UserLogsView, {
    global: {
      stubs: {
        PageHeader: { template: '<header><slot name="actions" /></header>' },
        LogFileTable: true,
        EmptyState: true,
        LoadingBlock: true,
        ErrorState: true,
        'el-button': {
          props: ['disabled', 'loading'],
          template:
            '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
        },
        'el-select': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template:
            '<select @change="$emit(\'update:modelValue\', Number($event.target.value))"><slot /></select>',
        },
        'el-option': {
          props: ['label', 'value'],
          template: '<option :value="value">{{ label }}</option>',
        },
        'el-card': {
          template: '<section><header><slot name="header" /></header><slot /></section>',
        },
      },
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  route.query = {}
  vi.mocked(listUsers).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  vi.mocked(getUserLogs).mockResolvedValue([])
  router.replace.mockResolvedValue(undefined)
  vi.mocked(downloadUserLog).mockResolvedValue({ blob: new Blob(['log']), filename: file.filename })
})

describe('UserLogsView', () => {
  it('labels the user filter and preserves the choose-user and empty-log states', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('label').attributes('for')).toBe('log-user-select')
    expect(wrapper.get('select').attributes('aria-label')).toBe('选择日志用户')
    expect(wrapper.findComponent(EmptyState).props('title')).toBe('请选择用户')
    const vm = wrapper.vm as unknown as UserLogsVm
    vm.selectedId = 1
    await flushPromises()
    expect(wrapper.findComponent(EmptyState).props('title')).toBe('暂无日志文件')
  })

  it('identifies the selected account and passes its files and download events to the shared list', async () => {
    vi.mocked(listUsers).mockResolvedValueOnce({
      items: [
        {
          id: 1,
          username: '日志账户'.repeat(12),
          role: 'user',
          is_active: true,
          timezone: 'UTC',
          currency_code: 'CNY',
          created_at: '',
          updated_at: '',
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    })
    const wrapper = mountView()
    await flushPromises()
    vi.mocked(getUserLogs).mockResolvedValueOnce([file])
    const vm = wrapper.vm as unknown as UserLogsVm
    vm.selectedId = 1
    await flushPromises()
    expect(wrapper.text()).toContain(`${'日志账户'.repeat(12)}的日志`)
    expect(wrapper.findComponent(LogFileTable).props('files')).toEqual([file])
    wrapper.findComponent(LogFileTable).vm.$emit('download', file.filename)
    await flushPromises()
    expect(downloadUserLog).toHaveBeenCalledWith(1, file.filename, expect.any(AbortSignal))
  })

  it.each(['success', 'error'])(
    'ignores an older user %s while the new user is loading',
    async (kind) => {
      const wrapper = mountView()
      await flushPromises()
      const vm = wrapper.vm as unknown as UserLogsVm
      const older = deferred()
      const latest = deferred()
      vi.mocked(getUserLogs).mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
      vm.selectedId = 1
      vm.selectedId = 2

      expect(getUserLogs).toHaveBeenNthCalledWith(1, 1, expect.any(AbortSignal))
      expect(getUserLogs).toHaveBeenNthCalledWith(2, 2, expect.any(AbortSignal))
      if (kind === 'success') older.resolve([file])
      else older.reject(new ApiError({ status: 500, code: 'FAILED', message: '旧用户查询失败' }))
      await flushPromises()
      expect(vm.files).toEqual([])
      expect(vm.error).toBeNull()
      expect(vm.loading).toBe(true)

      latest.resolve([{ ...file, filename: 'new-user.log' }])
      await flushPromises()
      expect(vm.files).toEqual([{ ...file, filename: 'new-user.log' }])
      expect(vm.loading).toBe(false)
    },
  )

  it.each(['success', 'error'])(
    'ignores an older user %s after the new user has loaded',
    async (kind) => {
      const wrapper = mountView()
      await flushPromises()
      const vm = wrapper.vm as unknown as UserLogsVm
      const older = deferred()
      const latest = deferred()
      vi.mocked(getUserLogs).mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
      vm.selectedId = 1
      vm.selectedId = 2
      latest.resolve([{ ...file, filename: 'new-user.log' }])
      await flushPromises()

      if (kind === 'success') older.resolve([file])
      else older.reject(new ApiError({ status: 500, code: 'FAILED', message: '旧用户查询失败' }))
      await flushPromises()
      expect(vm.files).toEqual([{ ...file, filename: 'new-user.log' }])
      expect(vm.error).toBeNull()
      expect(vm.loading).toBe(false)
    },
  )

  it.each(['success', 'error'])(
    'invalidates an in-flight %s when the selection is cleared',
    async (kind) => {
      const wrapper = mountView()
      await flushPromises()
      const vm = wrapper.vm as unknown as UserLogsVm
      const pending = deferred()
      vi.mocked(getUserLogs).mockReturnValueOnce(pending.promise)
      vm.selectedId = 1
      expect(vm.loading).toBe(true)
      vm.selectedId = undefined
      expect(vm.files).toEqual([])
      expect(vm.error).toBeNull()
      expect(vm.loading).toBe(false)

      if (kind === 'success') pending.resolve([file])
      else pending.reject(new ApiError({ status: 500, code: 'FAILED', message: '旧用户查询失败' }))
      await flushPromises()
      expect(vm.files).toEqual([])
      expect(vm.error).toBeNull()
      expect(vm.loading).toBe(false)
      expect(router.replace).toHaveBeenLastCalledWith({ query: {} })
      await vm.downloadFile()
      expect(downloadUserLog).not.toHaveBeenCalled()
    },
  )

  it('clears old files immediately and blocks downloads while changing users', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as UserLogsVm
    vi.mocked(getUserLogs).mockResolvedValueOnce([file])
    vm.selectedId = 1
    await flushPromises()
    expect(wrapper.find('button').element.disabled).toBe(false)

    const pending = deferred()
    vi.mocked(getUserLogs).mockReturnValueOnce(pending.promise)
    router.replace.mockReturnValueOnce(new Promise(() => {}))
    vm.selectedId = 2
    expect(vm.files).toEqual([])
    expect(vm.loading).toBe(true)
    await vm.downloadFile(file.filename)
    expect(downloadUserLog).not.toHaveBeenCalled()
    await flushPromises()
    expect(wrapper.find('button').element.disabled).toBe(true)

    pending.resolve([{ ...file, filename: 'new-user.log' }])
    await flushPromises()
    expect(wrapper.find('button').element.disabled).toBe(false)
    await vm.downloadFile('new-user.log')
    expect(downloadUserLog).toHaveBeenCalledWith(2, 'new-user.log', expect.any(AbortSignal))
    expect(saveBlob).toHaveBeenCalledOnce()
  })

  it('shows the current load error and blocks downloading after failure', async () => {
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as unknown as UserLogsVm
    const failure = new ApiError({ status: 500, code: 'FAILED', message: '当前用户查询失败' })
    vi.mocked(getUserLogs).mockRejectedValueOnce(failure)
    vm.selectedId = 1
    await flushPromises()

    expect(vm.error).toBe(failure)
    expect(vm.loading).toBe(false)
    expect(wrapper.find('button').element.disabled).toBe(true)
    await vm.downloadFile()
    expect(downloadUserLog).not.toHaveBeenCalled()
  })
})

it('loads a linked user outside the initial search page', async () => {
  route.query = { user_id: '201' }
  vi.mocked(getUser).mockResolvedValue({
    id: 201,
    username: 'outside-page',
    role: 'user',
    is_active: true,
    timezone: 'UTC',
    currency_code: 'CNY',
    created_at: '',
    updated_at: '',
  })
  const wrapper = mountView()
  await flushPromises()
  expect(getUser).toHaveBeenCalledWith(201, expect.any(AbortSignal))
  expect((wrapper.vm as unknown as UserLogsVm).selectedId).toBe(201)
  expect(getUserLogs).toHaveBeenCalledWith(201, expect.any(AbortSignal))
})

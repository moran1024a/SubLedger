import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'
import { useLogFiles } from '@/composables/useLogFiles'
import { ApiError, type LogFile } from '@/types/api'

vi.mock('@/api/logs', () => ({ saveBlob: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { error: vi.fn() },
}))

const file: LogFile = { date: '2026-09-30', filename: '2026-09-30.log', size: 1, modified_at: '' }

function setup(download: Parameters<typeof useLogFiles>[1]) {
  let api!: ReturnType<typeof useLogFiles>
  mount(
    defineComponent({
      setup() {
        api = useLogFiles(async () => [file], download)
        return () => null
      },
    }),
  )
  return api
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useLogFiles downloads', () => {
  it('adds the request ID to a download failure message', async () => {
    const api = setup(() =>
      Promise.reject(
        new ApiError({
          status: 500,
          code: 'INTERNAL_ERROR',
          message: '下载失败',
          requestId: 'req-42',
        }),
      ),
    )
    await api.load()
    await api.downloadFile(file.filename)
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('下载失败（请求 ID：req-42）')
  })

  it('shows the plain message when no request ID is available', async () => {
    const api = setup(() =>
      Promise.reject(new ApiError({ status: 404, code: 'LOG_NOT_FOUND', message: '日志不存在' })),
    )
    await api.load()
    await api.downloadFile(file.filename)
    expect(ElMessage.error).toHaveBeenCalledWith('日志不存在')
  })
})

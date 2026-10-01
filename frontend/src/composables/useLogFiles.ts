import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { saveBlob } from '@/api/logs'
import { ApiError, type LogFile } from '@/types/api'
import { asApiError } from '@/utils/apiErrors'

export function useLogFiles(
  list: () => Promise<LogFile[]> | LogFile[],
  download: (filename?: string) => Promise<{ blob: Blob; filename: string }>,
) {
  const files = ref<LogFile[]>([])
  const loading = ref(false)
  const error = ref<ApiError | null>(null)
  const downloading = ref<string | null>(null)
  let sequence = 0
  let disposed = false
  onBeforeUnmount(() => {
    disposed = true
    sequence += 1
  })
  async function load() {
    const current = ++sequence
    files.value = []
    loading.value = true
    error.value = null
    try {
      const pending = list()
      if (Array.isArray(pending)) {
        files.value = pending
        return
      }
      const result = await pending
      if (current === sequence) files.value = result
    } catch (cause) {
      if (current === sequence) error.value = asApiError(cause)
    } finally {
      if (current === sequence) loading.value = false
    }
  }
  async function downloadFile(filename?: string) {
    if (loading.value || error.value || !files.value.length || downloading.value) return
    downloading.value = filename ?? 'all'
    try {
      const result = await download(filename)
      if (!disposed) saveBlob(result.blob, result.filename)
    } catch (cause) {
      if (!disposed) ElMessage.error(cause instanceof ApiError ? cause.message : '下载失败')
    } finally {
      downloading.value = null
    }
  }
  return { files, loading, error, downloading, load, downloadFile }
}

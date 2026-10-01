import 'element-plus/es/components/message/style/css'
import { useQueryRequest } from './useQueryRequest'
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { saveBlob } from '@/api/logs'
import { ApiError, type LogFile } from '@/types/api'
import { asApiError } from '@/utils/apiErrors'

export function useLogFiles(
  list: (signal?: AbortSignal) => Promise<LogFile[]> | LogFile[],
  download: (filename?: string, signal?: AbortSignal) => Promise<{ blob: Blob; filename: string }>,
) {
  const files = ref<LogFile[]>([])
  const loading = ref(false)
  const error = ref<ApiError | null>(null)
  const downloading = ref<string | null>(null)
  const queries = useQueryRequest()
  const downloads = useQueryRequest()
  let sequence = 0
  let disposed = false
  onBeforeUnmount(() => {
    disposed = true
    sequence += 1
  })
  async function load() {
    const signal = queries.next()
    downloads.cancel()
    downloading.value = null
    const current = ++sequence
    files.value = []
    loading.value = true
    error.value = null
    try {
      const pending = list(signal)
      if (Array.isArray(pending)) {
        files.value = pending
        return
      }
      const result = await pending
      if (!signal.aborted && current === sequence) files.value = result
    } catch (cause) {
      if (!signal.aborted && current === sequence) error.value = asApiError(cause)
    } finally {
      if (!signal.aborted && current === sequence) loading.value = false
    }
  }
  async function downloadFile(filename?: string) {
    if (loading.value || error.value || !files.value.length || downloading.value) return
    const signal = downloads.next()
    downloading.value = filename ?? 'all'
    try {
      const result = await download(filename, signal)
      if (!disposed && !signal.aborted) saveBlob(result.blob, result.filename)
    } catch (cause) {
      if (!disposed && !signal.aborted)
        ElMessage.error(cause instanceof ApiError ? cause.message : '下载失败')
    } finally {
      if (!signal.aborted) downloading.value = null
    }
  }
  return { files, loading, error, downloading, load, downloadFile }
}

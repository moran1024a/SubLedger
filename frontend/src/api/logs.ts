import { download, request } from './client'
import type { LogFile } from '@/types/api'

export function getMyLogs(signal?: AbortSignal) {
  return request<LogFile[]>('/me/logs', { signal })
}
export function getSystemLogs(signal?: AbortSignal) {
  return request<LogFile[]>('/admin/system-logs', { signal })
}
export function getUserLogs(userId: number, signal?: AbortSignal) {
  return request<LogFile[]>(`/admin/users/${userId}/logs`, { signal })
}
export function downloadMyLog(filename?: string, signal?: AbortSignal) {
  return download(
    `/me/logs/download${filename ? `?filename=${encodeURIComponent(filename)}` : ''}`,
    { signal },
  )
}
export function downloadSystemLog(filename?: string, signal?: AbortSignal) {
  return download(
    `/admin/system-logs/download${filename ? `?filename=${encodeURIComponent(filename)}` : ''}`,
    { signal },
  )
}
export function downloadUserLog(userId: number, filename?: string, signal?: AbortSignal) {
  return download(
    `/admin/users/${userId}/logs/download${filename ? `?filename=${encodeURIComponent(filename)}` : ''}`,
    { signal },
  )
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

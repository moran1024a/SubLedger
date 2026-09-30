import { download, request } from './client'
import type { LogFile } from '@/types/api'

export function getMyLogs() {
  return request<LogFile[]>('/me/logs')
}
export function getSystemLogs() {
  return request<LogFile[]>('/admin/system-logs')
}
export function getUserLogs(userId: number) {
  return request<LogFile[]>(`/admin/users/${userId}/logs`)
}
export function downloadMyLog(filename?: string) {
  return download(`/me/logs/download${filename ? `?filename=${encodeURIComponent(filename)}` : ''}`)
}
export function downloadSystemLog(filename?: string) {
  return download(
    `/admin/system-logs/download${filename ? `?filename=${encodeURIComponent(filename)}` : ''}`,
  )
}
export function downloadUserLog(userId: number, filename?: string) {
  return download(
    `/admin/users/${userId}/logs/download${filename ? `?filename=${encodeURIComponent(filename)}` : ''}`,
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

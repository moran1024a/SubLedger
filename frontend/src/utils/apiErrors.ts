import { ApiError } from '@/types/api'

export function getFieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {}
  return Object.fromEntries(
    error.fields.filter(({ field }) => field).map(({ field, message }) => [field, message]),
  )
}

import { ApiError } from '@/types/api'

export function getFieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {}
  return Object.fromEntries(
    error.fields.filter(({ field }) => field).map(({ field, message }) => [field, message]),
  )
}

export function asApiError(
  cause: unknown,
  message = '无法连接服务器，请检查网络或服务状态。',
): ApiError {
  return cause instanceof ApiError ? cause : new ApiError({ status: 0, code: 'NETWORK', message })
}

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

export function isUncertainWrite(cause: unknown): boolean {
  const error = asApiError(cause)
  return error.status === 0 || error.status >= 500
}

export function writeErrorMessage(cause: unknown) {
  const error = asApiError(cause)
  return isUncertainWrite(error)
    ? '操作结果待确认。请先重新查询核实，避免重复提交。'
    : error.message
}

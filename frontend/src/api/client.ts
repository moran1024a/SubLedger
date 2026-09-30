import { ApiError, type ApiErrorBody } from '@/types/api'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
type ErrorHandler = (error: ApiError, url: string) => void | Promise<void>
let unauthorizedHandler: ErrorHandler | undefined
let forbiddenHandler: ErrorHandler | undefined

export function setUnauthorizedHandler(handler: ErrorHandler) {
  unauthorizedHandler = handler
}

export function setForbiddenHandler(handler: ErrorHandler) {
  forbiddenHandler = handler
}

function parseError(
  status: number,
  body: ApiErrorBody | null,
  responseRequestId?: string,
): ApiError {
  return new ApiError({
    status,
    code: body?.code ?? (status >= 500 ? 'INTERNAL_ERROR' : 'REQUEST_FAILED'),
    message:
      body?.message ?? (status === 0 ? '无法连接服务器，请检查网络或服务状态。' : '请求失败'),
    requestId: body?.request_id ?? responseRequestId,
    fields: body?.errors,
  })
}

async function readBody(response: Response): Promise<ApiErrorBody | null> {
  if (response.status === 204) return null
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as ApiErrorBody
  } catch {
    return null
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return requestAt<T>(`${API_BASE}${path}`, init)
}

export async function requestRoot<T>(
  path: string,
  init: RequestInit = {},
  acceptedStatuses: number[] = [],
): Promise<T> {
  return requestAt<T>(path, init, acceptedStatuses)
}

async function requestAt<T>(
  url: string,
  init: RequestInit = {},
  acceptedStatuses: number[] = [],
): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(url, { ...init, headers, credentials: 'include' })
  } catch {
    throw parseError(0, null)
  }
  const body = await readBody(response)
  if (!response.ok && !acceptedStatuses.includes(response.status)) {
    const error = parseError(
      response.status,
      body,
      response.headers.get('X-Request-ID') ?? undefined,
    )
    if (response.status === 401) await unauthorizedHandler?.(error, url)
    if (response.status === 403) await forbiddenHandler?.(error, url)
    throw error
  }
  return body as T
}

export async function download(path: string): Promise<{ blob: Blob; filename: string }> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { credentials: 'include' })
  } catch {
    throw parseError(0, null)
  }
  if (!response.ok) {
    const body = await readBody(response)
    const error = parseError(
      response.status,
      body,
      response.headers.get('X-Request-ID') ?? undefined,
    )
    if (response.status === 401) await unauthorizedHandler?.(error, response.url)
    if (response.status === 403) await forbiddenHandler?.(error, response.url)
    throw error
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  return {
    blob: await response.blob(),
    filename: encoded ? decodeURIComponent(encoded) : (plain ?? 'subledger-logs.zip'),
  }
}

export { API_BASE }

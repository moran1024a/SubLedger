import { ApiError, type ApiErrorBody } from '@/types/api'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
export type RequestOptions = RequestInit & { timeoutMs?: number }
type ErrorHandler = (error: ApiError, url: string) => void | Promise<void>
let unauthorizedHandler: ErrorHandler | undefined
let forbiddenHandler: ErrorHandler | undefined

export function setUnauthorizedHandler(handler: ErrorHandler) {
  unauthorizedHandler = handler
}
export function setForbiddenHandler(handler: ErrorHandler) {
  forbiddenHandler = handler
}

function parseError(status: number, body: ApiErrorBody | null, requestId?: string): ApiError {
  return new ApiError({
    status,
    code: body?.code ?? (status >= 500 ? 'INTERNAL_ERROR' : 'REQUEST_FAILED'),
    message:
      body?.message ?? (status === 0 ? '无法连接服务器，请检查网络或服务状态。' : '请求失败'),
    requestId: body?.request_id ?? requestId,
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

// The same deadline covers fetch, response headers, JSON and blob consumption.
async function perform<T>(
  url: string,
  options: RequestOptions,
  consume: (response: Response, check: () => void) => Promise<T>,
): Promise<T> {
  const { timeoutMs, signal: parentSignal, ...init } = options
  const write = !['GET', 'HEAD'].includes((init.method ?? 'GET').toUpperCase())
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort()
  if (parentSignal?.aborted) cancel()
  else parentSignal?.addEventListener('abort', cancel, { once: true })
  const timer = setTimeout(
    () => {
      timedOut = true
      controller.abort()
    },
    timeoutMs ?? (write ? 45000 : 15000),
  )
  const check = () => {
    if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError')
  }
  try {
    check()
    const headers = new Headers(init.headers)
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    const response = await fetch(url, {
      ...init,
      headers,
      signal: controller.signal,
      credentials: 'include',
    })
    check()
    const result = await consume(response, check)
    check()
    return result
  } catch (cause) {
    if (controller.signal.aborted) {
      throw new ApiError({
        status: 0,
        code: timedOut ? 'REQUEST_TIMEOUT' : 'REQUEST_CANCELLED',
        message: timedOut
          ? write
            ? '请求超时，操作结果待确认。请重新查询或刷新核实，避免重复提交。'
            : '请求超时，请重试。'
          : '请求已取消',
      })
    }
    if (cause instanceof ApiError) throw cause
    throw parseError(0, null)
  } finally {
    clearTimeout(timer)
    parentSignal?.removeEventListener('abort', cancel)
  }
}

async function handleError(response: Response, body: ApiErrorBody | null, url: string) {
  const error = parseError(response.status, body, response.headers.get('X-Request-ID') ?? undefined)
  if (response.status === 401) await unauthorizedHandler?.(error, url)
  if (response.status === 403) await forbiddenHandler?.(error, url)
  throw error
}

export async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  return requestAt<T>(`${API_BASE}${path}`, init)
}
export async function requestRoot<T>(
  path: string,
  init: RequestOptions = {},
  acceptedStatuses: number[] = [],
): Promise<T> {
  return requestAt<T>(path, init, acceptedStatuses)
}
async function requestAt<T>(
  url: string,
  init: RequestOptions,
  acceptedStatuses: number[] = [],
): Promise<T> {
  return perform(url, init, async (response, check) => {
    const body = await readBody(response)
    check()
    if (!response.ok && !acceptedStatuses.includes(response.status))
      await handleError(response, body, url)
    return body as T
  })
}
export async function download(
  path: string,
  init: RequestOptions = {},
): Promise<{ blob: Blob; filename: string }> {
  return perform(`${API_BASE}${path}`, { timeoutMs: 60000, ...init }, async (response, check) => {
    if (!response.ok) {
      const body = await readBody(response)
      check()
      await handleError(response, body, response.url)
    }
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
    return {
      blob: await response.blob(),
      filename: encoded ? decodeURIComponent(encoded) : (plain ?? 'subledger-logs.zip'),
    }
  })
}
export { API_BASE }

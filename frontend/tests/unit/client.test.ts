import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  download,
  request,
  setForbiddenHandler,
  setUnauthorizedHandler,
  setSessionVersionProvider,
} from '@/api/client'

beforeEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(() => {})
  setForbiddenHandler(() => {})
  setSessionVersionProvider(() => 0)
})

describe('api client', () => {
  it.each([401, 403])(
    'does not redirect a new session for a late %i from the previous one',
    async (status) => {
      let version = 1
      setSessionVersionProvider(() => version)
      let complete!: (value: Response) => void
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation(
          () =>
            new Promise<Response>((resolve) => {
              complete = resolve
            }),
        ),
      )
      const unauthorized = vi.fn(),
        forbidden = vi.fn()
      setUnauthorizedHandler(unauthorized)
      setForbiddenHandler(forbidden)
      const result = expect(request('/plans')).rejects.toMatchObject({ status })
      version = 2
      complete(new Response('{}', { status }))
      await result
      expect(unauthorized).not.toHaveBeenCalled()
      expect(forbidden).not.toHaveBeenCalled()
    },
  )
  it('sends credentials and parses structured errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: 'INVALID_REQUEST',
            message: '错误',
            request_id: 'abc',
            errors: [{ field: 'name', message: '必填' }],
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    await expect(request('/plans')).rejects.toMatchObject({
      status: 422,
      code: 'INVALID_REQUEST',
      requestId: 'abc',
      fields: [{ field: 'name' }],
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/plans',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('rejects a successful response that is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('<html>down</html>', {
          status: 200,
          headers: { 'X-Request-ID': 'req-html' },
        }),
      ),
    )

    await expect(request('/plans')).rejects.toMatchObject({
      status: 200,
      code: 'INVALID_RESPONSE',
      message: '服务器返回了无法解析的响应',
      requestId: 'req-html',
    })
  })

  it('does not parse a 204 body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request('/auth/logout', { method: 'POST' })).resolves.toBeNull()
  })

  it('invokes authentication handlers before rejecting', async () => {
    const unauthorized = vi.fn()
    const forbidden = vi.fn()
    setUnauthorizedHandler(unauthorized)
    setForbiddenHandler(forbidden)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID', message: '会话失效' }), {
            status: 401,
          }),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ code: 'PERMISSION_DENIED', message: '无权访问' }), {
            status: 403,
          }),
        ),
    )

    await expect(request('/auth/me')).rejects.toMatchObject({ status: 401 })
    await expect(request('/admin/users')).rejects.toMatchObject({ status: 403 })
    expect(unauthorized).toHaveBeenCalledWith(
      expect.objectContaining({ status: 401 }),
      '/api/v1/auth/me',
    )
    expect(forbidden).toHaveBeenCalledWith(
      expect.objectContaining({ status: 403 }),
      '/api/v1/admin/users',
    )
  })

  it('normalizes network and non-json errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('offline')))
    await expect(request('/plans')).rejects.toMatchObject({
      status: 0,
      message: '无法连接服务器，请检查网络或服务状态。',
    })

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(
        new Response('<html>failed</html>', {
          status: 500,
          headers: { 'X-Request-ID': 'req-500' },
        }),
      ),
    )
    await expect(request('/plans')).rejects.toMatchObject({
      status: 500,
      code: 'INTERNAL_ERROR',
      requestId: 'req-500',
    })
  })

  it('extracts utf-8 download filenames', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('log', {
          headers: { 'Content-Disposition': "attachment; filename*=UTF-8''user%20logs.zip" },
        }),
      ),
    )

    await expect(download('/me/logs/download')).resolves.toMatchObject({
      filename: 'user logs.zip',
    })
  })
})

describe('request deadlines and cancellation', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    setUnauthorizedHandler(undefined as never)
    setForbiddenHandler(undefined as never)
  })

  it('times out while reading a response body, not only waiting for headers', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url, init) =>
        Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers(),
          text: () =>
            new Promise((_resolve, reject) => {
              init.signal.addEventListener('abort', () =>
                reject(new DOMException('Aborted', 'AbortError')),
              )
            }),
        }),
      ),
    )
    const { request } = await import('@/api/client')
    const result = expect(request('/slow', { timeoutMs: 20 })).rejects.toMatchObject({
      code: 'REQUEST_TIMEOUT',
    })
    await vi.advanceTimersByTimeAsync(21)
    await result
    expect(vi.getTimerCount()).toBe(0)
  })

  it('marks write timeout as uncertain and sends only once', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        }),
    )
    vi.stubGlobal('fetch', fetch)
    const result = expect(
      request('/plans', { method: 'POST', body: '{}', timeoutMs: 20 }),
    ).rejects.toMatchObject({
      code: 'REQUEST_TIMEOUT',
      message: expect.stringContaining('结果待确认'),
    })
    await vi.advanceTimersByTimeAsync(21)
    await result
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('suppresses an old 401 body after a caller cancels the request', async () => {
    const unauthorized = vi.fn()
    setUnauthorizedHandler(unauthorized)
    let complete!: (value: string) => void
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers(),
        text: () =>
          new Promise<string>((resolve) => {
            complete = resolve
          }),
      }),
    )
    const controller = new AbortController()
    const result = expect(request('/plans', { signal: controller.signal })).rejects.toMatchObject({
      code: 'REQUEST_CANCELLED',
    })
    await Promise.resolve()
    await Promise.resolve()
    controller.abort()
    complete('{}')
    await result
    expect(unauthorized).not.toHaveBeenCalled()
  })

  it('times out downloads while consuming the blob', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url, init) =>
        Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers(),
          blob: () =>
            new Promise((_resolve, reject) => {
              init.signal.addEventListener('abort', () =>
                reject(new DOMException('Aborted', 'AbortError')),
              )
            }),
        }),
      ),
    )
    const result = expect(download('/logs', { timeoutMs: 20 })).rejects.toMatchObject({
      code: 'REQUEST_TIMEOUT',
    })
    await vi.advanceTimersByTimeAsync(21)
    await result
  })
})

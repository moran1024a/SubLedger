import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  download,
  request,
  setForbiddenHandler,
  setUnauthorizedHandler,
} from '@/api/client'

beforeEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(() => {})
  setForbiddenHandler(() => {})
})

describe('api client', () => {
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
    expect(unauthorized).toHaveBeenCalledWith(expect.objectContaining({ status: 401 }), '/api/v1/auth/me')
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

    await expect(download('/me/logs/download')).resolves.toMatchObject({ filename: 'user logs.zip' })
  })
})

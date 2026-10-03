import { afterEach, describe, expect, it, vi } from 'vitest'
import { saveBlob } from '@/api/logs'

const original = { createObjectURL: URL.createObjectURL, revokeObjectURL: URL.revokeObjectURL }
afterEach(() => {
  Object.assign(URL, original)
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('saveBlob', () => {
  it('clicks an attached anchor and revokes the object URL after a delay', () => {
    vi.useFakeTimers()
    const createObjectURL = vi.fn(() => 'blob:log')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    let attached = false
    let downloadName = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      attached = document.body.contains(this)
      downloadName = this.download
    })

    saveBlob(new Blob(['log']), '2026-09-30.log')

    expect(attached).toBe(true)
    expect(downloadName).toBe('2026-09-30.log')
    expect(document.body.querySelector('a')).toBeNull()
    expect(revokeObjectURL).not.toHaveBeenCalled()
    vi.advanceTimersByTime(999)
    expect(revokeObjectURL).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:log')
  })
})

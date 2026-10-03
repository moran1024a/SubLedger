import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { useCountUp } from '@/composables/useCountUp'

afterEach(() => {
  vi.unstubAllGlobals()
})

function run(value: ReturnType<typeof ref<string | null>>) {
  const scope = effectScope()
  const display = scope.run(() => useCountUp(value))!
  return { display, stop: () => scope.stop() }
}

describe('useCountUp', () => {
  it('shows the target immediately when reduced motion is preferred', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    const frame = vi.fn()
    vi.stubGlobal('requestAnimationFrame', frame)
    const value = ref<string | null>(null)
    const { display, stop } = run(value)

    expect(display.value).toBe('')
    value.value = '1234.56'
    await nextTick()

    expect(display.value).toBe('1234.56')
    expect(frame).not.toHaveBeenCalled()
    stop()
  })

  it('counts the integer part up to the first value and keeps the fraction', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
      frames.push(callback),
    )
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    const value = ref<string | null>(null)
    const { display, stop } = run(value)

    value.value = '100.50'
    await nextTick()
    frames.shift()!(0)
    expect(display.value).toBe('0.50')
    frames.shift()!(200)
    expect(Number(display.value)).toBeGreaterThan(50)
    expect(Number(display.value)).toBeLessThan(100)
    frames.shift()!(400)
    expect(display.value).toBe('100.50')
    expect(frames).toHaveLength(0)
    stop()
  })

  it('replaces a value that was already loaded without animating', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    const frame = vi.fn()
    vi.stubGlobal('requestAnimationFrame', frame)
    const value = ref<string | null>('10.00')
    const { display, stop } = run(value)

    expect(display.value).toBe('10.00')
    value.value = '20.00'
    await nextTick()

    expect(display.value).toBe('20.00')
    expect(frame).not.toHaveBeenCalled()
    stop()
  })
})

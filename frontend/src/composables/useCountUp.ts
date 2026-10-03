import { onScopeDispose, ref, watch, type Ref } from 'vue'

function canAnimate(): boolean {
  if (typeof window === 'undefined') return false
  if (typeof window.requestAnimationFrame !== 'function') return false
  if (typeof window.matchMedia !== 'function') return false
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Counts the integer part of a numeric string up to its target the first time it arrives. */
export function useCountUp(value: Ref<string | null | undefined>, durationMs = 400): Ref<string> {
  const display = ref(value.value ?? '')
  let frame = 0

  function stop() {
    if (frame) window.cancelAnimationFrame(frame)
    frame = 0
  }

  function animate(target: string) {
    const match = /^(-?)(\d+)(\.\d+)?$/.exec(target)
    const end = match ? Number(match[2]) : Number.NaN
    if (!match || !Number.isFinite(end)) {
      display.value = target
      return
    }
    const sign = match[1]
    const fraction = match[3] ?? ''
    let startTime: number | null = null
    const step = (now: number) => {
      if (startTime === null) startTime = now
      const progress = durationMs > 0 ? Math.min(1, (now - startTime) / durationMs) : 1
      if (progress >= 1) {
        display.value = target
        frame = 0
        return
      }
      const eased = 1 - Math.pow(1 - progress, 3)
      display.value = `${sign}${Math.round(end * eased)}${fraction}`
      frame = window.requestAnimationFrame(step)
    }
    frame = window.requestAnimationFrame(step)
  }

  watch(value, (next, previous) => {
    stop()
    if (next === null || next === undefined) {
      display.value = ''
      return
    }
    // Only the first load counts up; later refreshes replace the number directly.
    if (previous !== null && previous !== undefined) {
      display.value = next
      return
    }
    if (!canAnimate()) {
      display.value = next
      return
    }
    animate(next)
  })

  onScopeDispose(stop)
  return display
}

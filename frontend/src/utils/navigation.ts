import { nextTick } from 'vue'
import type { LocationQueryValue } from 'vue-router'
const positions = new Map<string, number>()
export function rememberPosition(path: string) {
  if (positions.size >= 50) positions.delete(positions.keys().next().value!)
  positions.set(path, window.scrollY)
}
export async function restorePosition(path: string) {
  const top = positions.get(path)
  if (top !== undefined) {
    await nextTick()
    window.scrollTo({ top })
  }
}
export function clearPositions() {
  positions.clear()
}
export function returnPath(
  value: LocationQueryValue | LocationQueryValue[] | undefined,
  fallback = '/plans',
) {
  if (
    typeof value !== 'string' ||
    value.length > 2048 ||
    !value.startsWith('/') ||
    value.startsWith('//')
  )
    return fallback
  const url = new URL(value, 'https://subledger.invalid')
  return url.origin === 'https://subledger.invalid' &&
    /^(\/|\/plans(?:\/\d+)?|\/bills)$/.test(url.pathname)
    ? url.pathname + url.search
    : fallback
}

import { onBeforeUnmount, watch } from 'vue'

// Cancelling fetch cannot undo a write. Discard UI effects when its view or
// resource is no longer current, without automatically resubmitting it.
export function useViewScope(identity?: () => unknown) {
  let generation = 0
  let disposed = false
  if (identity)
    watch(
      identity,
      () => {
        generation += 1
      },
      { flush: 'sync' },
    )
  onBeforeUnmount(() => {
    disposed = true
    generation += 1
  })
  function capture() {
    const version = generation
    return () => !disposed && version === generation
  }
  return { capture }
}

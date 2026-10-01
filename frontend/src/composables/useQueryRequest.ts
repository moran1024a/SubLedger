import { onBeforeUnmount } from 'vue'

// A query belongs to its view. Authentication initialization belongs to the
// auth store and deliberately does not use this controller.
export function useQueryRequest() {
  let disposed = false
  let controller: AbortController | undefined
  function cancel() {
    controller?.abort()
  }
  function next() {
    cancel()
    controller = new AbortController()
    if (disposed) controller.abort()
    return controller.signal
  }
  onBeforeUnmount(() => {
    disposed = true
    cancel()
  })
  return { next, cancel }
}

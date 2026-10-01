import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'

const changes = new Set<Ref<boolean>>()
export function clearUnsavedChanges() {
  changes.forEach((dirty) => {
    dirty.value = false
  })
}
export function confirmDiscardChanges() {
  if (![...changes].some((dirty) => dirty.value)) return true
  if (!window.confirm('有未保存的修改，确定放弃并离开吗？')) return false
  clearUnsavedChanges()
  return true
}
export function useUnsavedChanges() {
  const dirty = ref(false)
  changes.add(dirty)
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (dirty.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => {
    changes.delete(dirty)
    window.removeEventListener('beforeunload', beforeUnload)
  })
  onBeforeRouteLeave(confirmDiscardChanges)
  onBeforeRouteUpdate((to, from) => to.path === from.path || confirmDiscardChanges())
  return { dirty, confirmDiscard: confirmDiscardChanges }
}

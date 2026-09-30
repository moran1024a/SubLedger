import { onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

export function useUnsavedChanges() {
  const dirty = ref(false)
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (dirty.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
  onBeforeRouteLeave(() =>
    dirty.value ? window.confirm('页面有未保存的修改，确定离开吗？') : true,
  )
  return { dirty }
}

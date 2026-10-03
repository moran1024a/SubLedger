import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'
import { useRouter, type Router } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'

type Draft = { dirty: Ref<boolean>; router?: Router }
const drafts = new Set<Draft>()
const guardedRouters = new WeakSet<Router>()
let pendingConfirmation: Promise<boolean> | null = null

export function clearUnsavedChanges() {
  drafts.forEach(({ dirty }) => {
    dirty.value = false
  })
}

async function confirmDrafts(items: Draft[], message?: string): Promise<boolean> {
  if (!items.some(({ dirty }) => dirty.value)) return true
  // Agreement never marks a draft saved: navigation can still be cancelled.
  if (pendingConfirmation) return pendingConfirmation
  pendingConfirmation = ElMessageBox.confirm(
    message ?? '有未保存的修改，确定放弃并离开吗？',
    '确认放弃修改',
    { type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' },
  ).then(
    () => true,
    () => false,
  )
  try {
    return await pendingConfirmation
  } finally {
    pendingConfirmation = null
  }
}

export function confirmDiscardChanges(message?: string): Promise<boolean> {
  return confirmDrafts([...drafts], message)
}

export function useUnsavedChanges() {
  const dirty = ref(false)
  const router = useRouter()
  const draft = { dirty, router }
  drafts.add(draft)
  // One guard per router prevents repeated dialogs for independent forms.
  // Query-only navigation leaves the mounted draft intact.
  if (router && !guardedRouters.has(router)) {
    guardedRouters.add(router)
    router.beforeResolve((to, from) =>
      to.path === from.path
        ? true
        : confirmDrafts([...drafts].filter((item) => item.router === router)),
    )
  }
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (dirty.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => {
    drafts.delete(draft)
    window.removeEventListener('beforeunload', beforeUnload)
  })
  return { dirty, confirmDiscard: (message?: string) => confirmDrafts([draft], message) }
}

import { computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useBillDrawer() {
  const route = useRoute(),
    router = useRouter()
  let trigger: HTMLElement | null = null
  const billId = computed(() => {
    const value = Number(route.query.bill_id)
    return Number.isSafeInteger(value) && value > 0 ? value : null
  })
  async function openBill(id: number, event?: Event) {
    trigger = (event?.currentTarget as HTMLElement) ?? (document.activeElement as HTMLElement)
    const target = { query: { ...route.query, bill_id: String(id) } }
    if (billId.value) await router.replace(target)
    else await router.push(target)
  }
  async function closeBill() {
    const query = { ...route.query }
    delete query.bill_id
    const target = { path: route.path, query }
    if (window.history.state?.back === router.resolve(target).fullPath) router.back()
    else await router.replace(target)
    await nextTick()
    if (trigger?.isConnected) trigger.focus()
    else document.querySelector<HTMLElement>('h1')?.focus()
  }
  return { billId, openBill, closeBill }
}

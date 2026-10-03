import { computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { positiveId } from '@/utils/billFilters'
import { useViewScope } from '@/composables/useViewScope'

export function useBillDrawer() {
  const route = useRoute(),
    router = useRouter()
  let trigger: HTMLElement | null = null
  const scope = useViewScope(() => route.path)
  const billId = computed(() => positiveId(route.query.bill_id))
  const invalidBillId = computed(() => route.query.bill_id !== undefined && billId.value === null)
  async function openBill(id: number, event?: Event) {
    if (!Number.isSafeInteger(id) || id <= 0) return
    trigger = (event?.currentTarget as HTMLElement) ?? (document.activeElement as HTMLElement)
    const target = { query: { ...route.query, bill_id: String(id) } }
    if (billId.value) await router.replace(target)
    else await router.push(target)
  }
  async function closeBill() {
    const current = scope.capture()
    const query = { ...route.query }
    delete query.bill_id
    const target = { path: route.path, query }
    if (window.history.state?.back === router.resolve(target).fullPath) router.back()
    else await router.replace(target)
    await nextTick()
    if (!current()) return
    if (trigger?.isConnected) trigger.focus()
    else document.querySelector<HTMLElement>('h1')?.focus()
  }
  return { billId, invalidBillId, openBill, closeBill }
}
